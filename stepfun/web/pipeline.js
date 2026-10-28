// Import and search pipelines shared by the app UI and the benchmark page.
import { api } from "./api.js";
import { chunkDocument, sha256Hex, estimateTokens } from "./chunker.js";

const round = (x) => Math.round(x * 100) / 100;
// 1e-6 absolute rounding keeps the JSON payload small; it is ~1000x below FP16/INT8 error.
const toWire = (vec) => Array.from(vec, (x) => Math.round(x * 1e6) / 1e6);

export const IMPORT_DEFAULTS = {
  batchSize: 16, // chunks per inference call
  sortByLength: true, // length-sorted batching
  pipelined: true, // write batch i to seekdb while batch i+1 is being embedded
  writeGroup: 64, // chunks per write request
  refresh: "probe", // probe | explicit
  maxTokens: 300, // chunk size
};

// docs: [{ key, title, text, source }]. Unchanged documents (same key + same content hash) are skipped
// before any embedding work; changed ones replace their old chunks atomically at commit.
export async function importDocuments({ kb, docs, embedder, options = {}, client = {}, onProgress = () => {} }) {
  const o = { ...IMPORT_DEFAULTS, ...options };
  const t = {};
  const T0 = performance.now();
  let s = performance.now();
  for (const d of docs) d.hash = await sha256Hex(`${d.title ?? ""}\n${d.text}`);
  t.hashMs = performance.now() - s;

  s = performance.now();
  const open = await api.openImport(kb, {
    docs: docs.map((d) => ({ key: d.key, hash: d.hash })),
    client: { ...client, ...o, backend: embedder.info?.backend, dtype: embedder.info?.dtype },
  });
  t.planMs = performance.now() - s;
  const batchId = open.batchId;
  onProgress({ phase: "plan", counts: open.counts });

  try {
    s = performance.now();
    const toEmbed = docs.filter((d) => open.plan[d.key] !== "unchanged");
    const chunks = [];
    for (const d of toEmbed) {
      const parts = chunkDocument(d, { maxTokens: o.maxTokens });
      d.chunkCount = parts.length;
      parts.forEach((text, index) =>
        chunks.push({ docKey: d.key, hash: d.hash, index, count: parts.length, title: d.title ?? "", text })
      );
    }
    t.chunkMs = performance.now() - s;
    const estTokens = chunks.reduce((n, c) => n + estimateTokens(c.text), 0);
    onProgress({ phase: "embed", done: 0, total: chunks.length });

    const writes = [];
    const w = { dbMs: 0, netMs: 0, written: 0, requests: 0 };
    const send = (group) => {
      const p = api.writeChunks(kb, batchId, group).then((r) => {
        w.dbMs += r.dbMs;
        w.netMs += r.clientMs;
        w.written += r.written;
        w.requests++;
        onProgress({ phase: "write", written: w.written, total: chunks.length });
      });
      writes.push(p);
      return p;
    };
    const meta = { backend: embedder.info?.backend, dtype: embedder.info?.dtype };
    const withVec = (c, vec) => ({ ...c, embedding: toWire(vec), meta });

    s = performance.now();
    let embedTimings = null;
    let embedWallMs = 0;
    if (chunks.length) {
      if (o.pipelined) {
        let group = [];
        const r = await embedder.embed(
          chunks.map((c) => c.text),
          {
            kind: "passage",
            batchSize: o.batchSize,
            sortByLength: o.sortByLength,
            bucket: o.bucket,
            onBatch: (m) => {
              const dim = m.vectors.length / m.indices.length;
              m.indices.forEach((ci, j) => group.push(withVec(chunks[ci], m.vectors.subarray(j * dim, (j + 1) * dim))));
              if (group.length >= o.writeGroup) send(group.splice(0));
              onProgress({ phase: "embed", done: m.done, total: m.total });
            },
          }
        );
        embedWallMs = performance.now() - s;
        if (group.length) send(group.splice(0));
        embedTimings = r.timings;
        await Promise.all(writes);
      } else {
        const r = await embedder.embed(
          chunks.map((c) => c.text),
          { kind: "passage", batchSize: o.batchSize, sortByLength: o.sortByLength, bucket: o.bucket }
        );
        embedWallMs = performance.now() - s;
        embedTimings = r.timings;
        const dim = r.dim;
        for (let i = 0; i < chunks.length; i += o.writeGroup) {
          await send(chunks.slice(i, i + o.writeGroup).map((c, j) => withVec(c, r.vectors.subarray((i + j) * dim, (i + j + 1) * dim))));
        }
      }
    }
    t.embedMs = embedWallMs;
    t.embedAndWriteMs = performance.now() - s;
    t.writeTailMs = t.embedAndWriteMs - embedWallMs; // write time not hidden behind embedding
    t.writeDbMs = w.dbMs;
    t.writeRequests = w.requests;

    s = performance.now();
    onProgress({ phase: "commit" });
    const commit = await api.commitImport(kb, batchId, {
      docs: toEmbed.map((d) => ({
        key: d.key,
        title: d.title ?? "",
        hash: d.hash,
        chunkCount: d.chunkCount,
        charCount: d.text.length,
        source: d.source ?? "",
      })),
      refresh: o.refresh,
    });
    t.commitMs = performance.now() - s;
    t.totalMs = performance.now() - T0;
    const timings = Object.fromEntries(Object.entries(t).map(([k, v]) => [k, typeof v === "number" ? round(v) : v]));
    const result = {
      batchId,
      counts: open.counts,
      docs: docs.length,
      chunks: chunks.length,
      estTokens,
      version: commit.version,
      visible: commit.visible,
      kb: commit.kb,
      timings,
      commitTimings: commit.timings,
      embedTimings,
      throughput: {
        chunksPerSec: embedWallMs ? round((chunks.length / embedWallMs) * 1000) : null,
        tokensPerSec: embedWallMs && embedTimings ? round((embedTimings.realTokens / embedWallMs) * 1000) : null,
      },
      options: o,
    };
    onProgress({ phase: "done", result });
    return result;
  } catch (e) {
    await api.abortImport(kb, batchId).catch(() => {});
    throw e;
  }
}

// One user query: local query embedding + seekdb retrieval. Returns hits and the stage breakdown.
export async function runSearch({ kb, text, embedder, mode = "hybrid", topK = 10, fusion = "rrf", impl = "search", useCache = true, window = 50 }) {
  const t0 = performance.now();
  let vector;
  let embedMs = 0;
  let embedTimings = null;
  if (mode !== "fulltext") {
    const e = await embedder.embedQuery(text, { useCache });
    vector = e.vector;
    embedTimings = e.timings;
    embedMs = performance.now() - t0;
  }
  const r = await api.search(kb, { text, vector, mode, topK, fusion, impl, window });
  const searchMs = performance.now() - t0 - embedMs;
  return {
    hits: r.hits,
    params: r.params,
    kbVersion: r.kbVersion,
    timings: {
      queryEmbedMs: round(embedMs),
      queryInferMs: embedTimings ? embedTimings.inferMs : 0,
      cacheHit: embedTimings ? embedTimings.cacheHits > 0 : false,
      seekdbMs: r.dbMs,
      serverMs: r.serverMs,
      networkMs: round(searchMs - r.serverMs),
      searchRoundTripMs: round(searchMs),
      // until results are in hand; the caller adds render time for the user-visible end-to-end figure
      totalMs: round(performance.now() - t0),
    },
  };
}
