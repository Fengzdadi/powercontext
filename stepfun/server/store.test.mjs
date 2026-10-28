// Storage-layer checks against the configured seekdb (npm test; needs `npm run db:start`): the import
// protocol and both fusions of hybrid search. Uses its own knowledge base `test_store_import` (8-d random vectors).
import test from "node:test";
import assert from "node:assert/strict";
import { KbStore } from "./store.mjs";
import { config } from "./config.mjs";

const KB = "test_store_import";
const DIM = 8;
// leaves imports of a running app server alone
const store = new KbStore(config, { warn() {} });
await store.init({ cleanupStale: false });

const vec = () => {
  const v = Array.from({ length: DIM }, () => Math.random() - 0.5);
  const n = Math.hypot(...v);
  return v.map((x) => x / n);
};
const chunksOf = (key, hash, n = 2) =>
  Array.from({ length: n }, (_, index) => ({ docKey: key, hash, index, count: n, title: key, text: `${key} ${hash} part ${index}`, embedding: vec() }));
const docMeta = (key, hash, n = 2) => ({ key, title: key, hash, chunkCount: n, charCount: 10, source: "test" });
async function importDocs(docs, refresh = "none") {
  const open = await store.openImport(KB, { docs: docs.map((d) => ({ key: d.key, hash: d.hash })) });
  const todo = docs.filter((d) => open.plan[d.key] !== "unchanged");
  await store.writeChunks(KB, open.batchId, todo.flatMap((d) => chunksOf(d.key, d.hash)));
  const commit = await store.commitImport(KB, open.batchId, { docs: todo.map((d) => docMeta(d.key, d.hash)), refresh });
  return { open, commit };
}
async function stored(key) {
  const kb = await store.kbHandle(KB);
  const rows = await store.reader.execute(
    `SELECT document, JSON_UNQUOTE(JSON_EXTRACT(metadata, '$.batch_id')) AS batch FROM \`${kb.table}\` WHERE JSON_UNQUOTE(JSON_EXTRACT(metadata, '$.doc_key')) = ?`,
    [key]
  );
  const [reg] = (await store.reader.execute("SELECT content_hash FROM kb_document WHERE kb_name = ? AND doc_key = ?", [KB, key])) ?? [];
  return { chunks: rows.length, batches: new Set(rows.map((r) => r.batch)), texts: rows.map((r) => String(r.document)), hash: reg?.content_hash ?? null };
}

test.before(async () => {
  if (await store.getKb(KB, { required: false })) await store.deleteKb(KB);
  await store.createKb({ name: KB, modelId: "test", dim: DIM });
});
test.after(async () => {
  await store.deleteKb(KB).catch(() => {});
  await store.close();
});

test("new documents become searchable at commit and bump the version", async () => {
  const { open, commit } = await importDocs([{ key: "a", hash: "h1" }, { key: "b", hash: "h1" }], "probe");
  assert.deepEqual(open.counts, { new: 2, changed: 0, unchanged: 0 });
  assert.equal(commit.visible, true);
  assert.equal(commit.version, 1);
  assert.equal(commit.kb.docs, 2);
  assert.equal(commit.kb.chunks, 4);
});

test("unchanged documents are skipped and leave the version alone", async () => {
  const { open, commit } = await importDocs([{ key: "a", hash: "h1" }, { key: "b", hash: "h1" }]);
  assert.deepEqual(open.counts, { new: 0, changed: 0, unchanged: 2 });
  assert.equal(commit.version, 1);
});

test("a changed document replaces its old chunks", async () => {
  const { open, commit } = await importDocs([{ key: "b", hash: "h2" }]);
  assert.deepEqual(open.counts, { new: 0, changed: 1, unchanged: 0 });
  const b = await stored("b");
  assert.equal(b.chunks, 2);
  assert.ok(b.texts.every((t) => t.includes("h2")));
  assert.equal(b.hash, "h2");
  assert.equal(commit.version, 2);
});

test("abort drops the batch's chunks and registers nothing", async () => {
  const open = await store.openImport(KB, { docs: [{ key: "c", hash: "h1" }] });
  await store.writeChunks(KB, open.batchId, chunksOf("c", "h1"));
  await store.abortImport(KB, open.batchId);
  const c = await stored("c");
  assert.equal(c.chunks, 0);
  assert.equal(c.hash, null);
  await assert.rejects(store.commitImport(KB, open.batchId, { docs: [docMeta("c", "h1")] }), /aborted/);
});

test("two concurrent imports of the same new document keep exactly one version", async () => {
  const x = await store.openImport(KB, { docs: [{ key: "d", hash: "hx" }] });
  const y = await store.openImport(KB, { docs: [{ key: "d", hash: "hy" }] });
  assert.equal(x.plan.d, "new");
  assert.equal(y.plan.d, "new");
  await store.writeChunks(KB, x.batchId, chunksOf("d", "hx"));
  await store.writeChunks(KB, y.batchId, chunksOf("d", "hy"));
  await store.commitImport(KB, x.batchId, { docs: [docMeta("d", "hx")], refresh: "none" });
  const last = await store.commitImport(KB, y.batchId, { docs: [docMeta("d", "hy")], refresh: "none" });
  const d = await stored("d");
  assert.equal(d.chunks, 2, "chunks of the first commit must be retired");
  assert.deepEqual([...d.batches], [y.batchId]);
  assert.equal(d.hash, "hy");
  assert.equal(last.kb.docs, 3);
  assert.equal(last.kb.chunks, 6);
});

test("two concurrent imports of the same changed document keep exactly the last committed one", async () => {
  const x = await store.openImport(KB, { docs: [{ key: "d", hash: "hx2" }] });
  const y = await store.openImport(KB, { docs: [{ key: "d", hash: "hy2" }] });
  assert.equal(x.plan.d, "changed");
  assert.equal(y.plan.d, "changed");
  await store.writeChunks(KB, x.batchId, chunksOf("d", "hx2"));
  await store.writeChunks(KB, y.batchId, chunksOf("d", "hy2"));
  // x commits while y is still open: y's chunks must survive it
  await store.commitImport(KB, x.batchId, { docs: [docMeta("d", "hx2")], refresh: "none" });
  assert.deepEqual([...(await stored("d")).batches].sort(), [x.batchId, y.batchId].sort());
  await store.commitImport(KB, y.batchId, { docs: [docMeta("d", "hy2")], refresh: "none" });
  const d = await stored("d");
  assert.equal(d.chunks, 2);
  assert.deepEqual([...d.batches], [y.batchId]);
  assert.equal(d.hash, "hy2");
});

test("hybrid search fuses inside seekdb with RRF and with a weighted sum", async () => {
  const kb = await store.kbHandle(KB);
  const [row] = await store.reader.execute(`SELECT document, embedding FROM \`${kb.table}\` WHERE JSON_UNQUOTE(JSON_EXTRACT(metadata, '$.doc_key')) = 'b' LIMIT 1`);
  const vector = typeof row.embedding === "string" ? JSON.parse(row.embedding) : JSON.parse(String(row.embedding));
  const text = String(row.document);
  const rrf = await store.search(KB, { text, vector, fusion: "rrf" });
  assert.ok(rrf.hits.length > 0);
  assert.ok(rrf.hits.some((h) => h.keywordRank != null && h.semanticRank != null));
  const weighted = await store.search(KB, { text, vector, fusion: "weighted" });
  assert.ok(weighted.hits.length > 0);
  assert.equal(weighted.params.knn.boost, 0.7);
  assert.ok(weighted.hits.every((h) => h.keywordRank == null && (h.keywordScore != null || h.semanticScore != null)));
});

test("deleting a document removes its chunks and bumps the version", async () => {
  const before = await store.getKb(KB);
  const r = await store.deleteDoc(KB, "a");
  assert.equal(r.version, Number(before.version) + 1);
  assert.equal((await stored("a")).chunks, 0);
});
