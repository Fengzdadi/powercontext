// seekdb-side micro-benchmarks (Node, no browser): the retrieval call path, write batching, and how new
// rows become visible to the asynchronous HNSW index.
//   node bench/db-bench.mjs [--kb bench_query] [--repeats 5] [--stamp final]
// Reads the chunks of an existing knowledge base (default bench_query, which `npm run bench query`
// fills with embeddings computed in the browser), so latencies reflect real text and vectors. Scratch
// tables are created and dropped by this script; the knowledge base itself is only read.
// Writes bench/results/<stamp>__db.json.
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { execFileSync } from "node:child_process";
import { KbStore, kbSchema, sanitizeFulltext } from "../server/store.mjs";
import { config, ROOT } from "../server/config.mjs";

const args = process.argv.slice(2);
const opt = (n, d) => (args.includes(n) ? args[args.indexOf(n) + 1] : d);
const KB = opt("--kb", "bench_query");
const REPEATS = Number(opt("--repeats", 5));
const stamp = opt("--stamp", new Date().toISOString().slice(0, 10));

const now = () => performance.now();
const r2 = (x) => Math.round(x * 100) / 100;
const sleep = (t) => new Promise((r) => setTimeout(r, t));
const pct = (xs, p) => {
  const s = [...xs].sort((a, b) => a - b);
  return s[Math.min(s.length - 1, Math.max(0, Math.ceil((p / 100) * s.length) - 1))];
};
const summary = (xs) => ({ n: xs.length, median: r2(pct(xs, 50)), p90: r2(pct(xs, 90)), mean: r2(xs.reduce((a, b) => a + b, 0) / xs.length), min: r2(Math.min(...xs)) });
const parse = (v) => (Buffer.isBuffer(v) ? v.toString() : v);
const asJson = (v) => (typeof parse(v) === "string" ? JSON.parse(parse(v)) : v);
const log = (...a) => console.log(...a);

const store = new KbStore(config, { warn: console.warn });
await store.init({ cleanupStale: false });
const db = store.writer;
const result = { stamp, kb: KB, at: new Date().toISOString(), env: envInfo(), loadavgBefore: os.loadavg().map(r2) };

// ------------------------------------------------------------------ source data
const kb = await store.kbHandle(KB);
const rows = (await store.reader.execute(`SELECT _id, document, embedding, metadata FROM \`${kb.table}\``)).map((r) => ({
  id: String(parse(r._id)),
  document: String(parse(r.document)),
  embedding: asJson(r.embedding),
  metadata: asJson(r.metadata),
}));
if (!rows.length) throw new Error(`knowledge base ${KB} is empty: run \`npm run bench query\` first`);
const dim = rows[0].embedding.length;
const byDocKey = new Map();
for (const r of rows) if (!byDocKey.has(r.metadata.doc_key)) byDocKey.set(r.metadata.doc_key, r.embedding);
const readLines = (f) => fs.readFileSync(path.join(ROOT, "eval", "data", f), "utf8").trim().split("\n");
const firstRelevant = new Map();
for (const line of readLines("qrels.tsv")) {
  const [q, d, rel] = line.split("\t");
  if (rel === "1" && !firstRelevant.has(q) && byDocKey.has(d)) firstRelevant.set(q, d);
}
// Query text from the eval set; query vector = stored vector of its first relevant passage (the db
// bench has no model; vector-route latency does not depend on where the vector came from).
let queries = readLines("queries.jsonl")
  .map((l) => JSON.parse(l))
  .filter((q) => firstRelevant.has(q.qid))
  .map((q) => ({ text: q.text, vector: byDocKey.get(firstRelevant.get(q.qid)) }));
// any other knowledge base: the opening words of each chunk, with its own vector
if (!queries.length) queries = rows.slice(0, 90).map((r) => ({ text: r.document.slice(0, 24), vector: r.embedding }));
result.source = { table: kb.table, chunks: rows.length, dim, queries: queries.length };
log(`source ${KB}: ${rows.length} chunks, dim ${dim}, ${queries.length} queries; repeats ${REPEATS}`);

// ------------------------------------------------------------------ 1. retrieval call path
const K = 10;
const WIN = 50;
const searchParams = (q, { prune = true, mode = "hybrid" } = {}) => {
  const p = { size: K };
  if (prune) p._source = ["_id", "document", "metadata"];
  if (mode !== "vector") p.query = { match: { document: sanitizeFulltext(q.text) } };
  if (mode !== "fulltext") p.knn = { field: "embedding", k: WIN, query_vector: q.vector };
  if (mode === "hybrid") {
    p.rank = { rrf: { rank_window_size: WIN, rank_constant: 60 } };
    if (prune) p._source.push("_keyword_rank", "_semantic_rank", "_keyword_score", "_semantic_score");
  }
  return p;
};
const rawSearch = async (q, o) => {
  const res = await store.reader.execute("SELECT DBMS_HYBRID_SEARCH.SEARCH(?, ?) AS r", [kb.table, JSON.stringify(searchParams(q, o))]);
  return asJson(res[0].r);
};
const sdkCollection = await store.readerCollection(KB, kb);
const sdkSearch = (q) =>
  sdkCollection.hybridSearch({
    query: { whereDocument: { $contains: sanitizeFulltext(q.text) } },
    knn: { queryEmbeddings: [q.vector], nResults: WIN },
    rank: { rrf: { rankWindowSize: WIN, rankConstant: 60 } },
    nResults: K,
  });
const variants = {
  // the app's path: one round trip, embeddings left out of the JSON result
  "hybrid · SEARCH · _source pruned": (q) => rawSearch(q),
  "hybrid · SEARCH · all columns": (q) => rawSearch(q, { prune: false }),
  // seekdb-js Collection.hybridSearch: SET @param + GET_SQL + generated SQL, returns embeddings
  "hybrid · SDK hybridSearch()": (q) => sdkSearch(q),
  "vector only · SEARCH": (q) => rawSearch(q, { mode: "vector" }),
  "full-text only · SEARCH": (q) => rawSearch(q, { mode: "fulltext" }),
};
const lat = Object.fromEntries(Object.keys(variants).map((k) => [k, []]));
const payload = {};
for (const [name, fn] of Object.entries(variants)) {
  // warm-up pass (plan cache, index pages), also records the response size
  let bytes = 0;
  for (const q of queries) {
    const r = await fn(q);
    bytes += Buffer.byteLength(JSON.stringify(r));
  }
  payload[name] = Math.round(bytes / queries.length);
}
for (let rep = 0; rep < REPEATS; rep++) {
  for (const q of queries) {
    // variants interleaved per query, so load drift on a shared machine hits all of them alike
    for (const [name, fn] of Object.entries(variants)) {
      const t = now();
      await fn(q);
      lat[name].push(now() - t);
    }
  }
}
let same = 0;
for (const q of queries) {
  const a = (await rawSearch(q)).map((h) => String(h._id));
  const b = (await sdkSearch(q)).ids[0].map(String);
  same += a.filter((id) => b.includes(id)).length / Math.max(1, a.length);
}
result.search = {
  k: K,
  window: WIN,
  latencyMs: Object.fromEntries(Object.entries(lat).map(([k, v]) => [k, summary(v)])),
  avgResponseBytes: payload,
  sdkVsSearchTop10Overlap: r2(same / queries.length),
};
for (const [k, v] of Object.entries(result.search.latencyMs)) log(`search  ${k.padEnd(36)} median ${v.median} ms  p90 ${v.p90} ms  ${payload[k]} B`);

// ------------------------------------------------------------------ scratch collection (app schema)
const jitter = (v, seed) => {
  // unique vectors, so "is my own vector the nearest neighbour" identifies exactly one row
  let s = seed + 1;
  const out = v.map((x) => {
    s = (s * 16807) % 2147483647;
    return x + ((s / 2147483647) - 0.5) * 0.02;
  });
  const n = Math.hypot(...out);
  return out.map((x) => Math.round((x / n) * 1e6) / 1e6);
};
let seq = 0;
const makeRows = (n, prefix) =>
  Array.from({ length: n }, () => {
    const src = rows[seq % rows.length];
    const i = seq++;
    return { id: `${prefix}-${i}`, document: src.document, embedding: jitter(src.embedding, i), metadata: { ...src.metadata, bench: prefix } };
  });
const SCRATCH = "bench_db_scratch";
if (await db.hasCollection(SCRATCH)) await db.deleteCollection(SCRATCH);
const scratch = await db.createCollection({ name: SCRATCH, schema: kbSchema(dim), embeddingFunction: null });
const scratchTable = `c$v2$${scratch.collectionId}`;
const add = (col, rs) =>
  col.add({ ids: rs.map((r) => r.id), documents: rs.map((r) => r.document), embeddings: rs.map((r) => r.embedding), metadatas: rs.map((r) => r.metadata) });
const nearest = async (table, vec) => {
  const r = await db.execute(`SELECT _id FROM \`${table}\` ORDER BY cosine_distance(embedding, ?) APPROXIMATE LIMIT 1`, [JSON.stringify(vec)]);
  return r?.[0] ? String(parse(r[0]._id)) : null;
};

try {
  // 2. write batching: rows per INSERT (collection.add)
  result.writes = {};
  for (const group of [1, 8, 64, 256]) {
    const data = makeRows(group === 1 ? 128 : 512, `w${group}`);
    const t = now();
    for (let i = 0; i < data.length; i += group) await add(scratch, data.slice(i, i + group));
    const elapsed = now() - t;
    result.writes[`${group} rows/INSERT`] = { rows: data.length, ms: r2(elapsed), rowsPerSec: r2((data.length / elapsed) * 1000) };
    log(`write   ${group} rows/INSERT: ${r2((data.length / elapsed) * 1000)} rows/s`);
  }

  // 3. SDK upsert vs add for 64 new rows
  const ua = { add: [], upsert: [] };
  for (let rep = 0; rep < 3; rep++) {
    for (const how of ["add", "upsert"]) {
      const data = makeRows(64, `${how[0]}${rep}`);
      const t = now();
      await scratch[how]({ ids: data.map((r) => r.id), documents: data.map((r) => r.document), embeddings: data.map((r) => r.embedding), metadatas: data.map((r) => r.metadata) });
      ua[how].push(now() - t);
    }
  }
  result.upsertVsAdd = { rows: 64, addMs: summary(ua.add), upsertMs: summary(ua.upsert) };
  log(`write   64 rows: add ${result.upsertVsAdd.addMs.median} ms, upsert ${result.upsertVsAdd.upsertMs.median} ms`);

  // 4. visibility of new rows: wait for the async index (probe) vs explicit refresh; full-text route
  const vis = { probeMs: [], probeRounds: [], refreshMs: [], refreshVisible: [], visibleRightAfterInsert: [], fulltextImmediate: [] };
  for (let rep = 0; rep < 8; rep++) {
    for (const how of ["probe", "explicit"]) {
      const data = makeRows(64, `v${how[0]}${rep}`);
      const token = `zq${how[0]}${rep}x${Math.random().toString(36).slice(2, 7).replace(/\d/g, "k")}`;
      data.at(-1).document += ` ${token}`;
      await add(scratch, data);
      const t = now();
      const last = data.at(-1);
      if (how === "probe") {
        let rounds = 0;
        let ok = false;
        while (now() - t < 10000) {
          rounds++;
          if ((await nearest(scratchTable, last.embedding)) === last.id) {
            ok = true;
            break;
          }
          await sleep(10);
        }
        vis.probeMs.push(now() - t);
        vis.probeRounds.push(rounds);
        vis.visibleRightAfterInsert.push(rounds === 1 && ok);
      } else {
        await db.execute("CALL dbms_index_manager.refresh()");
        vis.refreshMs.push(now() - t);
        vis.refreshVisible.push((await nearest(scratchTable, last.embedding)) === last.id);
      }
      const ft = await db.execute("SELECT DBMS_HYBRID_SEARCH.SEARCH(?, ?) AS r", [scratchTable, JSON.stringify({ size: 1, _source: ["_id"], query: { match: { document: token } } })]);
      vis.fulltextImmediate.push(String(asJson(ft[0].r)[0]?._id) === last.id);
    }
  }
  result.visibility = {
    rowsPerWrite: 64,
    probeMs: summary(vis.probeMs),
    probeRounds: summary(vis.probeRounds),
    explicitRefreshMs: summary(vis.refreshMs),
    explicitRefreshVisible: vis.refreshVisible.every(Boolean),
    vectorVisibleRightAfterInsert: `${vis.visibleRightAfterInsert.filter(Boolean).length}/${vis.visibleRightAfterInsert.length}`,
    fulltextVisibleRightAfterInsert: `${vis.fulltextImmediate.filter(Boolean).length}/${vis.fulltextImmediate.length}`,
  };
  log(`visible probe ${result.visibility.probeMs.median} ms (${result.visibility.probeRounds.median} rounds) vs explicit refresh ${result.visibility.explicitRefreshMs.median} ms; full-text immediate ${result.visibility.fulltextVisibleRightAfterInsert}`);

  // 5. vector index SYNC_MODE: ASYNC (seekdb-js default) vs IMMEDIATE, same schema otherwise; rounds
  // alternate between the modes. untilVisible adds the wait for ANN search to return the last row.
  const sync = { ASYNC: [], IMMEDIATE: [] };
  for (let round = 0; round < 3; round++) {
    for (const mode of ["ASYNC", "IMMEDIATE"]) {
      const t = `bench_sync_${mode.toLowerCase()}`;
      await db.execute(`DROP TABLE IF EXISTS ${t}`);
      await db.execute(`CREATE TABLE ${t} (_id VARBINARY(512) PRIMARY KEY NOT NULL, document STRING, embedding VECTOR(${dim}), metadata JSON,
        FULLTEXT INDEX idx_fts (document) WITH PARSER ik PARSER_PROPERTIES=(ik_mode="smart"),
        VECTOR INDEX idx_vec (embedding) WITH (distance=cosine, type=hnsw, lib=vsag, m=16, ef_construction=200, ef_search=100, sync_mode=${mode.toLowerCase()})) ORGANIZATION = HEAP`);
      const data = makeRows(512, `s${mode[0]}${round}`);
      const last = data.at(-1);
      const t0 = now();
      for (let i = 0; i < data.length; i += 64) {
        const part = data.slice(i, i + 64);
        await db.execute(
          `INSERT INTO ${t} (_id, document, embedding, metadata) VALUES ${part.map(() => "(?, ?, ?, ?)").join(", ")}`,
          part.flatMap((r) => [r.id, r.document, JSON.stringify(r.embedding), JSON.stringify(r.metadata)])
        );
      }
      const insertMs = now() - t0;
      const rightAfter = (await nearest(t, last.embedding)) === last.id;
      let visible = rightAfter;
      while (!visible && now() - t0 < 10000) {
        await sleep(10);
        visible = (await nearest(t, last.embedding)) === last.id;
      }
      sync[mode].push({ insertMs, untilVisibleMs: now() - t0, rightAfter, visible });
      await db.execute(`DROP TABLE ${t}`);
    }
  }
  result.syncMode = Object.fromEntries(
    Object.entries(sync).map(([mode, runs]) => {
      const insertMs = summary(runs.map((r) => r.insertMs));
      return [
        mode,
        {
          rows: 512,
          rounds: runs.length,
          insertMs,
          untilVisibleMs: summary(runs.map((r) => r.untilVisibleMs)),
          rowsPerSec: r2((512 / insertMs.median) * 1000),
          lastRowVisibleRightAfterInsert: `${runs.filter((r) => r.rightAfter).length}/${runs.length}`,
          allVisible: runs.every((r) => r.visible),
        },
      ];
    })
  );
  for (const [mode, s] of Object.entries(result.syncMode)) {
    log(`sync    ${mode}: insert ${s.insertMs.median} ms, until visible ${s.untilVisibleMs.median} ms, visible right after insert ${s.lastRowVisibleRightAfterInsert}`);
  }
} finally {
  await db.deleteCollection(SCRATCH).catch(() => {});
}

result.loadavgAfter = os.loadavg().map(r2);
const out = path.join(config.benchResultsDir, `${stamp}__db.json`);
fs.writeFileSync(out, JSON.stringify(result, null, 2));
log(`wrote ${path.relative(ROOT, out)}`);
await store.close();
process.exit(0);

function envInfo() {
  const docker = (() => {
    try {
      // CPU_COUNT / MEMORY_LIMIT are seekdb's own resource settings (scripts/seekdb-docker.sh)
      const fmt = '{{.Config.Image}} (image {{.Image}}){{range .Config.Env}}{{if or (eq (index (split . "=") 0) "CPU_COUNT") (eq (index (split . "=") 0) "MEMORY_LIMIT")}} {{.}}{{end}}{{end}}';
      return execFileSync("docker", ["inspect", process.env.SEEKDB_CONTAINER || "stepfun-seekdb", "--format", fmt], { encoding: "utf8" }).trim();
    } catch {
      return null;
    }
  })();
  return {
    node: process.version,
    os: `${os.type()} ${os.release()} ${os.arch()}`,
    cpu: os.cpus()[0]?.model,
    cores: os.cpus().length,
    memGB: Math.round(os.totalmem() / 2 ** 30),
    seekdb: store.version,
    seekdbContainer: docker,
  };
}
