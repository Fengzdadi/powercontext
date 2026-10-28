// Benchmark page. One page load runs one suite for one configuration, chosen by URL parameters, and
// posts the raw measurements to /api/bench/results (bench/run-bench.mjs drives it with Chrome).
//   suite=quality  model load, full eval-corpus import, retrieval quality (vector/hybrid/full-text),
//                  query latency (repeats x all queries), vectors for cross-precision fidelity
//   suite=batch    embedding throughput for batch size / length sorting / shape bucketing variants
//                  (texts=N passages, default 256; quick=1 runs only the default batch configuration)
//   suite=load     model load only (run in a fresh profile for cold, after reload for warm)
//   suite=import   incremental import scenario: halves, unchanged re-import, edited docs, refresh modes
//   suite=query    query-path variants on an existing KB (kb=...): bucketing, cache, SDK vs SEARCH,
//                  RRF vs weighted fusion quality
import { Embedder } from "./embedder.js";
import { api } from "./api.js";
import { importDocuments, runSearch } from "./pipeline.js";
import { dedupeDocs, scoreQuery, mean, median, percentile } from "./metrics.js";
import { MODEL } from "./model-config.js";

const P = new URLSearchParams(location.search);
const num = (k, d) => (P.has(k) ? Number(P.get(k)) : d);
const bool = (k, d) => (P.has(k) ? P.get(k) === "1" || P.get(k) === "true" : d);
const cfg = {
  suite: P.get("suite") ?? "quality",
  backend: P.get("backend") ?? "auto",
  dtype: P.get("dtype") ?? "auto",
  source: P.get("source") ?? "hf",
  threads: P.has("threads") ? num("threads") : undefined,
  repeats: num("repeats", 5),
  batchSize: num("batch", 16),
  sortByLength: bool("sort", true),
  bucket: P.has("bucket") ? bool("bucket") : undefined,
  pipelined: bool("pipelined", true),
  refresh: P.get("refresh") ?? "probe",
  impl: P.get("impl") ?? "search",
  topK: num("k", 10),
  keep: bool("keep", false),
  kb: P.get("kb"),
  label: P.get("label") ?? `bench-${Date.now()}`,
};

const logEl = document.getElementById("log");
function log(...a) {
  const line = a.map((x) => (typeof x === "string" ? x : JSON.stringify(x))).join(" ");
  logEl.textContent += line + "\n";
  console.log(line);
}
const r2 = (x) => (x == null ? x : Math.round(x * 100) / 100);
const summary = (xs) => ({ n: xs.length, median: r2(median(xs)), p90: r2(percentile(xs, 90)), mean: r2(mean(xs)), min: r2(Math.min(...xs)), max: r2(Math.max(...xs)) });

async function loadEval() {
  const [corpus, queries, qrels] = await Promise.all([
    fetch("/eval/corpus.jsonl").then((r) => r.text()),
    fetch("/eval/queries.jsonl").then((r) => r.text()),
    fetch("/eval/qrels.tsv").then((r) => r.text()),
  ]);
  const docs = corpus.trim().split("\n").map((l) => JSON.parse(l)).map((d) => ({ key: d.id, title: d.title, text: d.text, source: `miracl-${d.lang}`, lang: d.lang }));
  const qs = queries.trim().split("\n").map((l) => JSON.parse(l));
  const rel = new Map();
  for (const line of qrels.trim().split("\n")) {
    const [q, d, r] = line.split("\t");
    if (!rel.has(q)) rel.set(q, new Map());
    rel.get(q).set(d, Number(r));
  }
  return { docs, queries: qs, qrels: rel };
}

function environment() {
  const ua = navigator.userAgentData;
  return {
    userAgent: navigator.userAgent,
    brands: ua?.brands?.map((b) => `${b.brand} ${b.version}`),
    platform: ua?.platform ?? navigator.platform,
    hardwareConcurrency: navigator.hardwareConcurrency,
    deviceMemory: navigator.deviceMemory,
    crossOriginIsolated,
  };
}

async function startEmbedder() {
  const e = new Embedder();
  const t0 = performance.now();
  const info = await e.start({ backend: cfg.backend, dtype: cfg.dtype, source: cfg.source, numThreads: cfg.threads, bucket: cfg.bucket });
  info.wallMs = r2(performance.now() - t0);
  log("embedder", { backend: info.backend, dtype: info.dtype, fallback: info.fallbackReason, cacheHit: info.cacheHit, timings: info.timings });
  return { e, info };
}

async function freshKb(name) {
  const { kbs } = await api.listKbs();
  if (kbs.some((k) => k.name === name)) await api.deleteKb(name);
  return api.createKb({ name, modelId: MODEL.repo, dim: MODEL.dim });
}

async function renderHits(hits) {
  // Mirror what the app does with results so the end-to-end figure includes DOM work.
  const box = document.getElementById("render");
  const t0 = performance.now();
  box.replaceChildren(
    ...hits.map((h) => {
      const li = document.createElement("li");
      li.textContent = `${h.meta?.title ?? ""} ${h.text.slice(0, 200)}`;
      return li;
    })
  );
  await new Promise((r) => requestAnimationFrame(() => r()));
  return performance.now() - t0;
}

async function qualityAndLatency(e, kb, data, out) {
  const modes = ["vector", "hybrid", "fulltext"];
  const per = {};
  for (const mode of modes) per[mode] = [];
  const firstQuery = [];
  for (const q of data.queries) {
    for (const mode of modes) {
      const r = await runSearch({ kb, text: q.text, embedder: e, mode, topK: 30, impl: cfg.impl, useCache: true });
      const ranked = dedupeDocs(r.hits, cfg.topK);
      const s = scoreQuery(ranked, data.qrels.get(q.qid) ?? new Map(), cfg.topK);
      per[mode].push({ qid: q.qid, lang: q.lang, ...s, top: ranked.slice(0, 3) });
      if (!firstQuery.length && mode === "hybrid") firstQuery.push(r.timings);
    }
  }
  const agg = (rows) => ({ n: rows.length, recall: r4(mean(rows.map((x) => x.recall))), ndcg: r4(mean(rows.map((x) => x.ndcg))), mrr: r4(mean(rows.map((x) => x.mrr))) });
  out.quality = {};
  for (const mode of modes) {
    out.quality[mode] = { all: agg(per[mode]), zh: agg(per[mode].filter((x) => x.lang === "zh")), en: agg(per[mode].filter((x) => x.lang === "en")) };
  }
  out.qualityPerQuery = per;
  log("quality@" + cfg.topK, out.quality);

  // Latency: query cache off, every query is embedded and searched for real. Pass 0 is the first
  // time each query text is seen by this page; later passes are warm.
  await e.clearQueryCache();
  const passes = [];
  for (let rep = 0; rep < cfg.repeats; rep++) {
    const rows = [];
    for (const q of data.queries) {
      const t0 = performance.now();
      const r = await runSearch({ kb, text: q.text, embedder: e, mode: "hybrid", topK: cfg.topK, impl: cfg.impl, useCache: false });
      const renderMs = await renderHits(r.hits);
      rows.push({ ...r.timings, renderMs: r2(renderMs), e2eMs: r2(performance.now() - t0) });
    }
    passes.push(rows);
  }
  const all = passes.flat();
  const warm = passes.slice(1).flat();
  const pick = (rows, k) => summary(rows.map((x) => x[k]));
  out.latency = {
    repeats: cfg.repeats,
    queries: data.queries.length,
    firstQueryAfterImport: firstQuery[0],
    pass0: { e2eMs: pick(passes[0], "e2eMs"), queryEmbedMs: pick(passes[0], "queryEmbedMs"), seekdbMs: pick(passes[0], "seekdbMs") },
    warm: warm.length
      ? {
          e2eMs: pick(warm, "e2eMs"),
          queryEmbedMs: pick(warm, "queryEmbedMs"),
          queryInferMs: pick(warm, "queryInferMs"),
          seekdbMs: pick(warm, "seekdbMs"),
          serverMs: pick(warm, "serverMs"),
          networkMs: pick(warm, "networkMs"),
          renderMs: pick(warm, "renderMs"),
        }
      : null,
    all: { e2eMs: pick(all, "e2eMs") },
  };
  out.latencyRaw = passes;
  log("latency(warm)", out.latency.warm);
}

const r4 = (x) => Math.round(x * 10000) / 10000;

async function fidelityVectors(e, data, out) {
  // Same inputs for every configuration: all queries and the first 128 passages by id.
  const qv = await e.embed(data.queries.map((q) => q.text), { kind: "query", batchSize: 16, useCache: false });
  const sample = [...data.docs].sort((a, b) => (a.key < b.key ? -1 : 1)).slice(0, 128);
  const pv = await e.embed(sample.map((d) => `${d.title}\n${d.text}`.slice(0, 2000)), { kind: "passage", batchSize: 16 });
  const pack = (f32, n) => Array.from({ length: n }, (_, i) => Array.from(f32.subarray(i * MODEL.dim, (i + 1) * MODEL.dim), (x) => Math.round(x * 1e6) / 1e6));
  out.vectors = { queryIds: data.queries.map((q) => q.qid), queries: pack(qv.vectors, data.queries.length), passageIds: sample.map((d) => d.key), passages: pack(pv.vectors, sample.length) };
}

async function suiteQuality(out) {
  const { e, info } = await startEmbedder();
  out.init = info;
  const data = await loadEval();
  const kb = cfg.kb ?? `bench_${info.backend}_${info.dtype}`;
  await freshKb(kb);
  out.kb = kb;
  const imp = await importDocuments({
    kb,
    docs: data.docs,
    embedder: e,
    options: { batchSize: cfg.batchSize, sortByLength: cfg.sortByLength, pipelined: cfg.pipelined, refresh: cfg.refresh, bucket: cfg.bucket },
    client: { bench: cfg.label },
  });
  out.import = imp;
  log("import", { chunks: imp.chunks, timings: imp.timings, commit: imp.commitTimings, throughput: imp.throughput });
  await qualityAndLatency(e, kb, data, out);
  await fidelityVectors(e, data, out);
  if (!cfg.keep) await api.deleteKb(kb);
  e.stop();
}

async function suiteBatch(out) {
  const { e, info } = await startEmbedder();
  out.init = info;
  const data = await loadEval();
  const texts = data.docs.slice(0, num("texts", 256)).map((d) => `${d.title}\n${d.text}`.slice(0, 1200));
  let variants = [
    { batchSize: 1, sortByLength: false },
    { batchSize: 8, sortByLength: false },
    { batchSize: 8, sortByLength: true },
    { batchSize: 16, sortByLength: false },
    { batchSize: 16, sortByLength: true },
    { batchSize: 32, sortByLength: true },
    { batchSize: 64, sortByLength: true },
  ];
  if (info.backend === "webgpu") variants.push({ batchSize: 16, sortByLength: true, bucket: false }, { batchSize: 16, sortByLength: true, bucket: true });
  if (bool("quick", false)) variants = [{ batchSize: 16, sortByLength: true }];
  out.batch = [];
  for (const v of variants) {
    const runs = [];
    for (let i = 0; i < 3; i++) {
      const t0 = performance.now();
      const r = await e.embed(texts, { kind: "passage", ...v });
      const wall = performance.now() - t0;
      runs.push({ wallMs: wall, chunksPerSec: (texts.length / wall) * 1000, tokensPerSec: (r.timings.realTokens / wall) * 1000, padRatio: r.timings.paddedTokens / r.timings.realTokens, inferMs: r.timings.inferMs });
    }
    const row = { ...v, texts: texts.length, wallMs: r2(median(runs.map((x) => x.wallMs))), chunksPerSec: r2(median(runs.map((x) => x.chunksPerSec))), tokensPerSec: r2(median(runs.map((x) => x.tokensPerSec))), padRatio: r2(median(runs.map((x) => x.padRatio))), runs };
    out.batch.push(row);
    log("batch", { ...row, runs: undefined });
  }
  e.stop();
}

async function suiteLoad(out) {
  const { e, info } = await startEmbedder();
  out.init = info;
  const t0 = performance.now();
  await e.embedQuery("第一次查询的向量化延迟", { useCache: false });
  out.firstQueryEmbedMs = r2(performance.now() - t0);
  e.stop();
}

async function suiteImport(out) {
  const { e, info } = await startEmbedder();
  out.init = info;
  const data = await loadEval();
  const kb = `bench_import_${info.backend}`;
  await freshKb(kb);
  const half = Math.floor(data.docs.length / 2);
  const opts = { batchSize: cfg.batchSize, sortByLength: true, pipelined: cfg.pipelined, refresh: cfg.refresh };
  const steps = [];
  const probeVisible = async (doc) => {
    // A query built from the new document's own text must return that document right after commit.
    const r = await runSearch({ kb, text: doc.text.slice(0, 60), embedder: e, mode: "hybrid", topK: 10, useCache: false });
    return dedupeDocs(r.hits, 10).includes(doc.key);
  };
  const step = async (name, docs, extra = {}) => {
    const r = await importDocuments({ kb, docs: docs.map((d) => ({ ...d })), embedder: e, options: { ...opts, ...extra } });
    // Every step's first document is new or edited, so it must be retrievable straight after commit.
    const visible = r.chunks ? await probeVisible(docs[0]) : null;
    steps.push({ name, counts: r.counts, chunks: r.chunks, timings: r.timings, commit: r.commitTimings, version: r.version, kbDocs: r.kb.docs, kbChunks: r.kb.chunks, newDocVisible: visible });
    log(name, steps.at(-1));
  };
  await step("first half (probe refresh)", data.docs.slice(0, half), { refresh: "probe" });
  await step("second half (explicit refresh)", data.docs.slice(half), { refresh: "explicit" });
  await step("re-import all, unchanged", data.docs);
  const edited = data.docs.slice(0, 10).map((d) => ({ ...d, text: d.text + " (修订版)" }));
  await step("10 edited docs (probe)", edited, { refresh: "probe" });
  const fresh = [{ key: "bench-new-doc", title: "增量写入测试", text: "这是一篇刚刚导入的新文档，用来验证刷新后立即可检索。seekdb incremental import visibility check." }];
  await step("1 new doc (probe)", fresh, { refresh: "probe" });
  const fresh2 = [{ key: "bench-new-doc-2", title: "增量写入测试二", text: "第二篇新文档，使用显式 dbms_index_manager.refresh 刷新。explicit refresh visibility check." }];
  await step("1 new doc (explicit)", fresh2, { refresh: "explicit" });
  // Deletion is visible immediately: the deleted document must not come back.
  const del = await api.deleteDoc(kb, "bench-new-doc");
  const r = await runSearch({ kb, text: fresh[0].text.slice(0, 40), embedder: e, mode: "hybrid", topK: 10, useCache: false });
  steps.push({ name: "delete doc", version: del.version, kbDocs: del.kb.docs, deletedStillReturned: dedupeDocs(r.hits, 10).includes("bench-new-doc") });
  log("delete", steps.at(-1));
  out.steps = steps;
  const docs = await api.listDocs(kb);
  out.finalDocs = docs.docs.length;
  if (!cfg.keep) await api.deleteKb(kb);
  e.stop();
}

async function suiteQuery(out) {
  const { e, info } = await startEmbedder();
  out.init = info;
  const data = await loadEval();
  const kb = cfg.kb;
  if (!kb) throw new Error("suite=query needs kb=<existing kb>");
  const variants = [
    { name: "SEARCH single call", impl: "search", useCache: false },
    { name: "SDK hybridSearch", impl: "sdk", useCache: false },
    { name: "SEARCH + query cache", impl: "search", useCache: true },
  ];
  out.variants = [];
  for (const v of variants) {
    const rows = [];
    for (let rep = 0; rep < cfg.repeats; rep++) {
      for (const q of data.queries) {
        const t0 = performance.now();
        const r = await runSearch({ kb, text: q.text, embedder: e, mode: "hybrid", topK: cfg.topK, impl: v.impl, useCache: v.useCache });
        rows.push({ ...r.timings, e2eMs: performance.now() - t0 });
      }
    }
    const warm = rows.slice(data.queries.length);
    const row = { ...v, e2eMs: summary(warm.map((x) => x.e2eMs)), seekdbMs: summary(warm.map((x) => x.seekdbMs)), queryEmbedMs: summary(warm.map((x) => x.queryEmbedMs)) };
    out.variants.push(row);
    log(v.name, row);
  }
  // Fusion inside seekdb on the same queries (vectors from the query cache): RRF vs weighted sum.
  out.fusion = [];
  for (const fusion of ["rrf", "weighted"]) {
    const rows = [];
    for (const q of data.queries) {
      const r = await runSearch({ kb, text: q.text, embedder: e, mode: "hybrid", topK: 30, fusion, impl: "search", useCache: true });
      rows.push({ lang: q.lang, ...scoreQuery(dedupeDocs(r.hits, cfg.topK), data.qrels.get(q.qid) ?? new Map(), cfg.topK) });
    }
    const agg = (xs) => ({ n: xs.length, recall: r4(mean(xs.map((x) => x.recall))), ndcg: r4(mean(xs.map((x) => x.ndcg))), mrr: r4(mean(xs.map((x) => x.mrr))) });
    out.fusion.push({ fusion, all: agg(rows), zh: agg(rows.filter((x) => x.lang === "zh")), en: agg(rows.filter((x) => x.lang === "en")) });
    log("fusion", out.fusion.at(-1));
  }

  // Query embedding with and without shape bucketing (off by default; only plausible on WebGPU).
  out.bucket = [];
  for (const bucket of [false, true]) {
    const xs = [];
    for (let rep = 0; rep < cfg.repeats; rep++) {
      for (const q of data.queries) {
        const r = await e.embed([q.text], { kind: "query", useCache: false, bucket });
        xs.push(r.timings.totalMs);
      }
    }
    out.bucket.push({ bucket, queryEmbedMs: summary(xs.slice(data.queries.length)), firstPassMs: summary(xs.slice(0, data.queries.length)) });
    log("bucket", out.bucket.at(-1));
  }
  e.stop();
}

const SUITES = { quality: suiteQuality, batch: suiteBatch, load: suiteLoad, import: suiteImport, query: suiteQuery };

(async () => {
  const out = { label: cfg.label, config: cfg, env: environment(), startedAt: new Date().toISOString(), health: await api.health() };
  try {
    log("bench", cfg);
    await SUITES[cfg.suite](out);
    out.ok = true;
  } catch (err) {
    out.ok = false;
    out.error = String(err?.stack ?? err);
    log("ERROR", out.error);
  }
  out.finishedAt = new Date().toISOString();
  if (P.get("save") !== "0") {
    const s = await api.saveBench(out).catch((e) => ({ error: e.message }));
    log("saved", s);
  }
  window.__benchResult = out;
  window.__benchDone = true;
  document.title = out.ok ? "done" : "failed";
})();
