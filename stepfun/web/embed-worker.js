// Embedding worker: every vector the app stores or queries with is computed here, on this device.
// Transformers.js 4 + ONNX Runtime Web; WebGPU when the adapter is usable, otherwise WASM.
import { env, AutoTokenizer, AutoModel } from "/vendor/transformers/transformers.min.js";
import { MODEL } from "./model-config.js";

const ORT_ASSETS = {
  mjs: new URL("/vendor/ort/ort-wasm-simd-threaded.asyncify.mjs", self.location.origin).href,
  wasm: new URL("/vendor/ort/ort-wasm-simd-threaded.asyncify.wasm", self.location.origin).href,
};

let state = null; // { tokenizer, model, backend, dtype, ... } once loaded
const queryCache = new Map(); // LRU: `${dtype}|${text}` -> Float32Array
const QUERY_CACHE_SIZE = 256;

const now = () => performance.now();
const round = (x) => Math.round(x * 100) / 100;

self.onmessage = async ({ data: msg }) => {
  try {
    if (msg.type === "init") {
      post({ id: msg.id, type: "ready", ...(await init(msg.options ?? {})) });
    } else if (msg.type === "embed") {
      const r = await embed(msg, msg.id);
      post({ id: msg.id, type: "result", ...r }, r.vectors ? [r.vectors.buffer] : []);
    } else if (msg.type === "clearQueryCache") {
      const cleared = queryCache.size;
      queryCache.clear();
      post({ id: msg.id, type: "result", cleared });
    }
  } catch (e) {
    post({ id: msg.id, type: "error", error: String(e?.message ?? e), stack: e?.stack });
  }
};

function post(m, transfer) {
  self.postMessage(m, transfer ?? []);
}

// --------------------------------------------------------------------------- backend selection

async function probeWebGPU() {
  if (!("gpu" in navigator)) return { ok: false, reason: "navigator.gpu 不存在（浏览器不支持 WebGPU 或已被禁用）" };
  let adapter;
  try {
    adapter = await navigator.gpu.requestAdapter({ powerPreference: "high-performance" });
  } catch (e) {
    return { ok: false, reason: `requestAdapter() 失败：${e.message}` };
  }
  if (!adapter) return { ok: false, reason: "requestAdapter() 返回 null（无可用 GPU 适配器）" };
  const info = adapter.info ?? {};
  return {
    ok: true,
    shaderF16: adapter.features.has("shader-f16"),
    adapter: { vendor: info.vendor, architecture: info.architecture, device: info.device, description: info.description },
    limits: { maxBufferSize: adapter.limits.maxBufferSize, maxStorageBufferBindingSize: adapter.limits.maxStorageBufferBindingSize },
  };
}

function configureEnv(o) {
  env.allowLocalModels = true;
  // A path, not an absolute URL: Transformers.js 4 skips its local existence check (get_file_metadata)
  // for URL-shaped local paths, which breaks source=local and sends the default path to huggingface.co.
  env.localModelPath = "/models/";
  // falls back to huggingface.co if models/ is empty; the locally quantised files exist only on disk
  env.allowRemoteModels = o.allowRemote !== false && o.source !== "local";
  env.useBrowserCache = o.useCache !== false;
  const wasm = env.backends.onnx.wasm;
  wasm.wasmPaths = { ...ORT_ASSETS };
  // SharedArrayBuffer (cross-origin isolation, served by server/index.mjs) enables multi-threaded WASM.
  const maxThreads = self.crossOriginIsolated ? Math.min(8, navigator.hardwareConcurrency || 4) : 1;
  wasm.numThreads = Math.max(1, Math.min(maxThreads, o.numThreads ?? maxThreads));
  wasm.simd = true;
  return wasm.numThreads;
}

async function loadModel(backend, dtype, o, events) {
  const t0 = now();
  const files = new Map();
  const progress_callback = (p) => {
    if (p.status === "initiate") files.set(p.file, { start: now() });
    if (p.status === "progress" && p.file) {
      const f = files.get(p.file) ?? {};
      f.loaded = p.loaded;
      f.total = p.total;
      files.set(p.file, f);
      events({ type: "progress", phase: "download", file: p.file, loaded: p.loaded, total: p.total });
    }
    if (p.status === "done" && p.file) {
      const f = files.get(p.file) ?? {};
      f.done = now();
      files.set(p.file, f);
    }
  };
  const repo = o.source === "local" ? MODEL.localRepo : MODEL.repo;
  const cacheHit = await isCached(repo, MODEL.files[dtype]);
  const tokenizer = await AutoTokenizer.from_pretrained(repo, { revision: MODEL.revision, progress_callback });
  const tTok = now();
  const model = await AutoModel.from_pretrained(repo, {
    revision: MODEL.revision,
    device: backend,
    dtype,
    progress_callback,
    session_options: { graphOptimizationLevel: "all" },
  });
  const tEnd = now();
  const fetched = [...files.values()].filter((f) => f.done);
  const lastFetch = fetched.length ? Math.max(...fetched.map((f) => f.done)) : tTok;
  const bytes = [...files.values()].reduce((s, f) => s + (f.total ?? 0), 0);
  return {
    tokenizer,
    model,
    timings: {
      tokenizerMs: round(tTok - t0),
      // download (or Cache Storage read) of the ONNX file vs. ONNX Runtime session creation
      modelFetchMs: round(Math.max(0, lastFetch - tTok)),
      sessionCreateMs: round(tEnd - Math.max(lastFetch, tTok)),
      modelLoadMs: round(tEnd - t0),
    },
    bytes,
    cacheHit,
  };
}

async function isCached(repo, file) {
  try {
    if (!("caches" in self)) return false;
    const cache = await caches.open(env.cacheKey);
    const keys = await cache.keys();
    return keys.some((k) => k.url.endsWith(`${repo}/${file}`) || (k.url.includes(`${repo}/resolve/`) && k.url.endsWith(`/${file}`)));
  } catch {
    return false;
  }
}

async function init(o) {
  const t0 = now();
  const events = (e) => post({ type: "event", ...e });
  const threads = configureEnv(o);
  const pref = o.backend ?? "auto";
  const gpu = pref === "wasm" ? { ok: false, reason: "已手动指定 WASM" } : await probeWebGPU();
  const detectMs = round(now() - t0);
  let backend = gpu.ok ? "webgpu" : "wasm";
  let fallbackReason = gpu.ok ? null : gpu.reason;
  const pickDtype = (b) => {
    if (o.dtype && o.dtype !== "auto") return o.dtype;
    if (b === "webgpu" && !gpu.shaderF16) return "fp32"; // no shader-f16: FP16 kernels unavailable
    return MODEL.defaults[b];
  };
  let dtype = pickDtype(backend);
  events({ type: "status", phase: "loading", backend, dtype });

  let loaded;
  try {
    loaded = await loadModel(backend, dtype, o, events);
  } catch (e) {
    if (backend !== "webgpu") throw e;
    // WebGPU adapter exists but the session failed (driver, limits, lost device): degrade to WASM.
    fallbackReason = `WebGPU 初始化失败，已降级：${e.message}`;
    backend = "wasm";
    dtype = pickDtype("wasm");
    events({ type: "status", phase: "loading", backend, dtype, fallbackReason });
    loaded = await loadModel(backend, dtype, o, events);
  }
  state = { ...loaded, backend, dtype, threads, gpu };
  queryCache.clear();

  // Warm-up: the first run compiles WebGPU pipelines / initialises WASM kernels. Doing it here keeps
  // that cost out of the first user query and first import batch.
  const warmBucket = o.bucket ?? false;
  const tw = now();
  await runBatch([MODEL.queryPrefix + "warm up"], { bucket: warmBucket });
  const firstInferMs = round(now() - tw);
  const tw2 = now();
  await runBatch([MODEL.queryPrefix + "second warm up run"], { bucket: warmBucket });
  const secondInferMs = round(now() - tw2);
  return {
    backend,
    dtype,
    fallbackReason,
    webgpu: gpu,
    threads: backend === "wasm" ? threads : null,
    crossOriginIsolated: self.crossOriginIsolated,
    cacheHit: loaded.cacheHit,
    bytes: loaded.bytes,
    timings: { detectMs, ...loaded.timings, firstInferMs, secondInferMs, totalMs: round(now() - t0) },
    model: { repo: MODEL.repo, revision: MODEL.revision, file: MODEL.files[dtype], dim: MODEL.dim, source: o.source === "local" ? MODEL.localRepo : "huggingface" },
  };
}

// --------------------------------------------------------------------------- inference

// Optional: pad lengths to a few fixed buckets so WebGPU sees fewer distinct shapes. Off by default:
// on the measured GPU (Apple M5 Pro, Metal) new shapes cost little and the extra padding cut batch
// throughput by 25-40% (bench/results/final__batch-webgpu-fp16.json).
const BUCKETS = [16, 32, 64, 128, 256, 384, 512];
const bucketOf = (n) => BUCKETS.find((b) => b >= n) ?? MODEL.maxTokens;

async function runBatch(texts, { bucket = false } = {}) {
  const { tokenizer, model } = state;
  const t0 = now();
  let enc = tokenizer(texts, { padding: true, truncation: true, max_length: MODEL.maxTokens });
  let seqLen = enc.input_ids.dims[1];
  if (bucket && bucketOf(seqLen) !== seqLen) {
    seqLen = bucketOf(seqLen);
    enc = tokenizer(texts, { padding: "max_length", truncation: true, max_length: seqLen });
  }
  const t1 = now();
  const out = await model(enc);
  const t2 = now();
  const hidden = out.last_hidden_state.type === "float32" ? out.last_hidden_state : out.last_hidden_state.to("float32");
  const vecs = meanPoolNormalize(hidden.data, enc.attention_mask.data, texts.length, seqLen, MODEL.dim);
  const t3 = now();
  let realTokens = 0;
  for (const m of enc.attention_mask.data) realTokens += Number(m);
  return { vecs, tokenizeMs: t1 - t0, inferMs: t2 - t1, poolMs: t3 - t2, realTokens, paddedTokens: texts.length * seqLen };
}

function meanPoolNormalize(h, mask, batch, len, dim) {
  const out = new Float32Array(batch * dim);
  for (let b = 0; b < batch; b++) {
    const o = b * dim;
    let count = 0;
    for (let t = 0; t < len; t++) {
      if (Number(mask[b * len + t]) === 0) continue;
      count++;
      const base = (b * len + t) * dim;
      for (let k = 0; k < dim; k++) out[o + k] += h[base + k];
    }
    let norm = 0;
    for (let k = 0; k < dim; k++) {
      out[o + k] /= Math.max(count, 1);
      norm += out[o + k] * out[o + k];
    }
    norm = Math.sqrt(norm) || 1;
    for (let k = 0; k < dim; k++) out[o + k] /= norm;
  }
  return out;
}

// texts: raw strings (prefix added here). kind: "query" | "passage".
// batchSize, sortByLength, bucket and stream control the import-time optimisations.
async function embed(msg, id) {
  if (!state) throw new Error("model not loaded");
  const { texts, kind = "passage", batchSize = 16, sortByLength = true, stream = false, useCache = true } = msg;
  const bucket = msg.bucket ?? false;
  const t0 = now();
  const prefix = kind === "query" ? MODEL.queryPrefix : MODEL.passagePrefix;
  const n = texts.length;
  const dim = MODEL.dim;
  const result = new Float32Array(n * dim);
  const stats = { tokenizeMs: 0, inferMs: 0, poolMs: 0, realTokens: 0, paddedTokens: 0, batches: 0, cacheHits: 0 };

  // Query cache: repeated queries skip inference entirely.
  const todo = [];
  for (let i = 0; i < n; i++) {
    const key = `${state.dtype}|${texts[i]}`;
    const hit = kind === "query" && useCache ? queryCache.get(key) : undefined;
    if (hit) {
      result.set(hit, i * dim);
      queryCache.delete(key);
      queryCache.set(key, hit);
      stats.cacheHits++;
    } else todo.push(i);
  }

  // Length-sorted batching keeps sequences of similar length together, so little compute is spent on padding.
  let order = todo;
  if (sortByLength && todo.length > 1) {
    const ts = now();
    const lens = new Map(todo.map((i) => [i, state.tokenizer.encode(prefix + texts[i]).length]));
    stats.tokenizeMs += now() - ts;
    order = [...todo].sort((a, b) => lens.get(a) - lens.get(b));
  }
  for (let s = 0; s < order.length; s += batchSize) {
    const idx = order.slice(s, s + batchSize);
    const r = await runBatch(
      idx.map((i) => prefix + texts[i]),
      { bucket }
    );
    stats.tokenizeMs += r.tokenizeMs;
    stats.inferMs += r.inferMs;
    stats.poolMs += r.poolMs;
    stats.realTokens += r.realTokens;
    stats.paddedTokens += r.paddedTokens;
    stats.batches++;
    idx.forEach((i, j) => result.set(r.vecs.subarray(j * dim, (j + 1) * dim), i * dim));
    if (kind === "query" && useCache) {
      idx.forEach((i, j) => {
        queryCache.set(`${state.dtype}|${texts[i]}`, r.vecs.slice(j * dim, (j + 1) * dim));
        if (queryCache.size > QUERY_CACHE_SIZE) queryCache.delete(queryCache.keys().next().value);
      });
    }
    if (stream) {
      const vecs = r.vecs.slice();
      post({ id, type: "batch", indices: idx, vectors: vecs, done: Math.min(s + batchSize, order.length), total: order.length }, [vecs.buffer]);
    }
  }
  const totalMs = now() - t0;
  const timings = Object.fromEntries(Object.entries(stats).map(([k, v]) => [k, k.endsWith("Ms") ? round(v) : v]));
  return { vectors: stream ? null : result, dim, timings: { ...timings, totalMs: round(totalMs) }, backend: state.backend, dtype: state.dtype };
}
