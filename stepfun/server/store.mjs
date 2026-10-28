// seekdb data layer. Every byte of KB state (chunks, vectors, text, metadata, document registry,
// import log) lives in seekdb and is accessed through seekdb-js.
//
// Layout (database `stepfun_kb` by default):
//   kb_registry          one row per knowledge base (model, dimension, version counter, counts)
//   kb_document          one row per imported document (content hash drives incremental import)
//   kb_import            one row per import batch (status, client info, stage timings)
//   c$v2$<id>            one seekdb-js collection per knowledge base: _id, document, embedding
//                        VECTOR(dim) with an HNSW index, metadata JSON, FULLTEXT index (IK parser)
//
// Retrieval is a single DBMS_HYBRID_SEARCH.SEARCH call, so seekdb runs the full-text route, the
// vector route and the fusion (RRF or weighted sum) itself.
import crypto from "node:crypto";
import { SeekdbClient, SeekdbAdminClient, Schema, FulltextIndexConfig, VectorIndexConfig } from "seekdb";

const KB_NAME_RE = /^[a-z][a-z0-9_]{0,47}$/;
const WRITE_BATCH_ROWS = 64;

export class HttpError extends Error {
  constructor(status, message) {
    super(message);
    this.status = status;
  }
}

// Serialises writers per knowledge base; readers never wait on it.
class KeyedMutex {
  #tails = new Map();
  async run(key, fn) {
    const prev = this.#tails.get(key) ?? Promise.resolve();
    let release;
    const next = new Promise((r) => (release = r));
    const tail = prev.then(() => next);
    this.#tails.set(key, tail);
    await prev;
    try {
      return await fn();
    } finally {
      release();
      if (this.#tails.get(key) === tail) this.#tails.delete(key);
    }
  }
}

const now = () => performance.now();
const ms = (t0) => Math.round((performance.now() - t0) * 100) / 100;
const sleep = (t) => new Promise((r) => setTimeout(r, t));
const parseJson = (v) => (typeof v === "string" ? JSON.parse(v) : v);
const docIdOf = (kb, key) => crypto.createHash("sha1").update(`${kb}\u0000${key}`).digest("hex").slice(0, 16);

// DBMS_HYBRID_SEARCH inlines match text into AGAINST('...') without escaping (a quote breaks the
// generated SQL), so only plain words reach it. IK tokenises whatever is left.
export function sanitizeFulltext(text) {
  return String(text)
    .replace(/[\\'"`]/g, " ")
    .replace(/[\u0000-\u001f]/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .slice(0, 512);
}

// Collection schema of every knowledge base.
export function kbSchema(dim, efSearch = 100) {
  return new Schema({
    // IK handles Chinese word segmentation and English tokens in the same column.
    fulltextIndex: new FulltextIndexConfig("ik", { ik_mode: "smart" }),
    vectorIndex: new VectorIndexConfig({
      hnsw: { dimension: dim, distance: "cosine", m: 16, ef_construction: 200, ef_search: efSearch },
      embeddingFunction: null,
    }),
  });
}

export class KbStore {
  constructor(cfg, log = console) {
    this.cfg = cfg;
    this.log = log;
    this.mutex = new KeyedMutex();
    this.kbCache = new Map(); // name -> { row, table, writer: Collection }
    this.batches = new Map(); // batchId -> { probes: [{ id, embedding }] } while an import is open
  }

  clientArgs(database) {
    const s = this.cfg.seekdb;
    if (s.path) return { path: s.path, database };
    return { host: s.host, port: s.port, user: s.user, password: s.password, database };
  }

  // cleanupStale=false lets a second process (bench/db-bench.mjs) attach without touching imports that
  // the running app may have open.
  async init({ cleanupStale = true } = {}) {
    const db = this.cfg.seekdb.database;
    const admin = new SeekdbAdminClient(this.clientArgs(undefined));
    try {
      await admin.getDatabase(db);
    } catch {
      await admin.createDatabase(db);
    }
    await admin.close();
    // Two connections: imports run on `writer`, searches on `reader`, so a long import never queues
    // in front of a user query (seekdb-js keeps one MySQL connection per client).
    this.writer = new SeekdbClient(this.clientArgs(db));
    this.reader = new SeekdbClient(this.clientArgs(db));
    const [{ v }] = await this.reader.execute("SELECT VERSION() AS v");
    this.version = String(v);
    await this.writer.execute(`CREATE TABLE IF NOT EXISTS kb_registry (
      name VARCHAR(64) PRIMARY KEY,
      collection VARCHAR(128) NOT NULL,
      model_id VARCHAR(128) NOT NULL,
      dim INT NOT NULL,
      version BIGINT NOT NULL DEFAULT 0,
      doc_count INT NOT NULL DEFAULT 0,
      chunk_count INT NOT NULL DEFAULT 0,
      created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
      updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3))`);
    await this.writer.execute(`CREATE TABLE IF NOT EXISTS kb_document (
      kb_name VARCHAR(64) NOT NULL,
      doc_key VARCHAR(512) NOT NULL,
      doc_id VARCHAR(32) NOT NULL,
      title VARCHAR(512),
      content_hash CHAR(64) NOT NULL,
      chunk_count INT NOT NULL,
      char_count INT NOT NULL,
      source VARCHAR(256),
      batch_id VARCHAR(64) NOT NULL,
      imported_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
      PRIMARY KEY (kb_name, doc_key))`);
    await this.writer.execute(`CREATE TABLE IF NOT EXISTS kb_import (
      batch_id VARCHAR(64) PRIMARY KEY,
      kb_name VARCHAR(64) NOT NULL,
      status VARCHAR(16) NOT NULL,
      docs_new INT NOT NULL DEFAULT 0,
      docs_changed INT NOT NULL DEFAULT 0,
      docs_unchanged INT NOT NULL DEFAULT 0,
      chunks INT NOT NULL DEFAULT 0,
      client JSON,
      timings JSON,
      started_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
      finished_at DATETIME(3))`);
    // Batches left open by a crashed server or a closed tab: drop their chunks.
    if (!cleanupStale) return this.version;
    const stale = await this.writer.execute("SELECT batch_id, kb_name FROM kb_import WHERE status = 'open'");
    for (const r of stale ?? []) {
      try {
        await this.abortImport(r.kb_name, r.batch_id);
      } catch (e) {
        this.log.warn(`could not clean stale batch ${r.batch_id}: ${e.message}`);
      }
    }
    return this.version;
  }

  async close() {
    await Promise.allSettled([this.writer?.close(), this.reader?.close()]);
  }

  // ---------------------------------------------------------------- knowledge bases

  async listKbs() {
    const rows = await this.reader.execute(
      "SELECT name, model_id, dim, version, doc_count, chunk_count, created_at, updated_at FROM kb_registry ORDER BY created_at"
    );
    return (rows ?? []).map(kbJson);
  }

  async getKb(name, { required = true } = {}) {
    const rows = await this.reader.execute(
      "SELECT name, collection, model_id, dim, version, doc_count, chunk_count, created_at, updated_at FROM kb_registry WHERE name = ?",
      [name]
    );
    if (!rows?.length) {
      if (required) throw new HttpError(404, `knowledge base '${name}' does not exist`);
      return null;
    }
    return rows[0];
  }

  async kbHandle(name) {
    const cached = this.kbCache.get(name);
    if (cached) return cached;
    const row = await this.getKb(name);
    const writer = await this.writer.getCollection({ name: row.collection, embeddingFunction: null });
    const handle = { row, writer, table: `c$v2$${writer.collectionId}` };
    this.kbCache.set(name, handle);
    return handle;
  }

  async createKb({ name, modelId, dim, efSearch = 100 }) {
    if (!KB_NAME_RE.test(name ?? "")) {
      throw new HttpError(400, "name must start with a letter and use only a-z, 0-9 and _ (max 48 chars)");
    }
    if (!Number.isInteger(dim) || dim < 8 || dim > 4096) throw new HttpError(400, "invalid dim");
    if (!modelId) throw new HttpError(400, "modelId is required");
    return this.mutex.run(name, async () => {
      if (await this.getKb(name, { required: false })) throw new HttpError(409, `knowledge base '${name}' already exists`);
      const collection = `kb_${name}`;
      if (await this.writer.hasCollection(collection)) await this.writer.deleteCollection(collection);
      await this.writer.createCollection({ name: collection, schema: kbSchema(dim, efSearch), embeddingFunction: null });
      await this.writer.execute("INSERT INTO kb_registry (name, collection, model_id, dim) VALUES (?, ?, ?, ?)", [
        name,
        collection,
        modelId,
        dim,
      ]);
      return kbJson(await this.getKb(name));
    });
  }

  async deleteKb(name) {
    return this.mutex.run(name, async () => {
      const row = await this.getKb(name);
      this.kbCache.delete(name);
      if (await this.writer.hasCollection(row.collection)) await this.writer.deleteCollection(row.collection);
      await this.writer.execute("DELETE FROM kb_document WHERE kb_name = ?", [name]);
      await this.writer.execute("DELETE FROM kb_import WHERE kb_name = ?", [name]);
      await this.writer.execute("DELETE FROM kb_registry WHERE name = ?", [name]);
      return { deleted: name };
    });
  }

  async listDocs(name) {
    await this.getKb(name);
    const rows = await this.reader.execute(
      `SELECT doc_key, doc_id, title, content_hash, chunk_count, char_count, source, batch_id, imported_at
       FROM kb_document WHERE kb_name = ? ORDER BY imported_at DESC, doc_key LIMIT 5000`,
      [name]
    );
    return (rows ?? []).map((r) => ({
      key: r.doc_key,
      docId: r.doc_id,
      title: r.title,
      hash: r.content_hash,
      chunks: r.chunk_count,
      chars: r.char_count,
      source: r.source,
      batchId: r.batch_id,
      importedAt: r.imported_at,
    }));
  }

  async listImports(name, limit = 20) {
    const rows = await this.reader.execute(
      `SELECT batch_id, status, docs_new, docs_changed, docs_unchanged, chunks, client, timings, started_at, finished_at
       FROM kb_import WHERE kb_name = ? ORDER BY started_at DESC LIMIT ${Math.min(200, Number(limit) || 20)}`,
      [name]
    );
    return (rows ?? []).map((r) => ({
      batchId: r.batch_id,
      status: r.status,
      docsNew: r.docs_new,
      docsChanged: r.docs_changed,
      docsUnchanged: r.docs_unchanged,
      chunks: r.chunks,
      client: parseJson(r.client),
      timings: parseJson(r.timings),
      startedAt: r.started_at,
      finishedAt: r.finished_at,
    }));
  }

  // ---------------------------------------------------------------- incremental import

  // Step 1: classify documents against the registry so unchanged ones skip embedding entirely.
  async openImport(name, { docs = [], client = {} }) {
    const kb = await this.getKb(name);
    const existing = new Map();
    const keys = docs.map((d) => String(d.key));
    for (let i = 0; i < keys.length; i += 500) {
      const part = keys.slice(i, i + 500);
      if (!part.length) continue;
      const rows = await this.reader.execute(
        `SELECT doc_key, content_hash FROM kb_document WHERE kb_name = ? AND doc_key IN (${part.map(() => "?").join(",")})`,
        [name, ...part]
      );
      for (const r of rows ?? []) existing.set(r.doc_key, r.content_hash);
    }
    const plan = {};
    const counts = { new: 0, changed: 0, unchanged: 0 };
    for (const d of docs) {
      const prev = existing.get(String(d.key));
      const status = prev === undefined ? "new" : prev === d.hash ? "unchanged" : "changed";
      plan[d.key] = status;
      counts[status]++;
    }
    const batchId = `b${Date.now().toString(36)}${crypto.randomBytes(4).toString("hex")}`;
    await this.writer.execute(
      "INSERT INTO kb_import (batch_id, kb_name, status, docs_new, docs_changed, docs_unchanged, client) VALUES (?, ?, 'open', ?, ?, ?, ?)",
      [batchId, name, counts.new, counts.changed, counts.unchanged, JSON.stringify(client)]
    );
    this.batches.set(batchId, { probes: [] });
    return { batchId, plan, counts, kbVersion: Number(kb.version), modelId: kb.model_id, dim: kb.dim };
  }

  // Step 2 (repeatable): write embedded chunks as multi-row INSERTs through the collection API.
  // Rows are tagged with the batch id and stay invisible to the registry until commit.
  async writeChunks(name, batchId, chunks) {
    const t0 = now();
    const kb = await this.kbHandle(name);
    await this.assertOpen(name, batchId);
    for (const c of chunks) {
      if (!Array.isArray(c.embedding) || c.embedding.length !== kb.row.dim) {
        throw new HttpError(400, `chunk ${c.docKey}#${c.index}: embedding must have ${kb.row.dim} dimensions`);
      }
    }
    const rows = chunks.map((c) => {
      const docId = docIdOf(name, c.docKey);
      return {
        id: `${docId}-${c.hash.slice(0, 8)}-${c.index}`,
        document: c.text,
        embedding: c.embedding,
        metadata: {
          doc_id: docId,
          doc_key: String(c.docKey),
          title: c.title ?? "",
          chunk_index: c.index,
          chunk_count: c.count,
          batch_id: batchId,
          ...(c.meta ?? {}),
        },
      };
    });
    for (let i = 0; i < rows.length; i += WRITE_BATCH_ROWS) {
      const part = rows.slice(i, i + WRITE_BATCH_ROWS);
      await kb.writer.add({
        ids: part.map((r) => r.id),
        documents: part.map((r) => r.document),
        embeddings: part.map((r) => r.embedding),
        metadatas: part.map((r) => r.metadata),
      });
    }
    // Remember the last row of each call; commit waits until the vector index returns them.
    if (rows.length) this.batches.get(batchId)?.probes.push({ id: rows.at(-1).id, embedding: rows.at(-1).embedding });
    return { written: rows.length, dbMs: ms(t0) };
  }

  // Step 3: retire replaced chunks, update the registry, and wait until the new chunks are visible to
  // both indexes before reporting success.
  async commitImport(name, batchId, { docs = [], refresh = "probe" }) {
    return this.mutex.run(name, async () => {
      const kb = await this.kbHandle(name);
      await this.assertOpen(name, batchId);
      const timings = {};
      const batch = this.batches.get(batchId) ?? { probes: [] };
      if (!docs.length) {
        // Nothing new or changed: the KB content (and therefore its version) stays as it was.
        await this.writer.execute("UPDATE kb_import SET status = 'committed', finished_at = CURRENT_TIMESTAMP(3) WHERE batch_id = ?", [batchId]);
        this.batches.delete(batchId);
        return { batchId, version: Number(kb.row.version), visible: true, timings: { refreshMode: "none" }, kb: kbJson(await this.getKb(name)) };
      }
      let t0 = now();
      // Documents already in the registry have chunks from an older batch to retire: the ones planned
      // as "changed", and any that a concurrent import (another tab) committed after this one opened.
      // Chunks of imports that are still open stay: they are retired by whichever import commits last
      // (an import open for over an hour counts as abandoned). Deciding here, under the KB mutex, keeps
      // exactly one version of each document.
      const openRows = await this.writer.execute(
        "SELECT batch_id FROM kb_import WHERE kb_name = ? AND status = 'open' AND started_at > DATE_SUB(NOW(3), INTERVAL 1 HOUR)",
        [name]
      );
      const keep = [...new Set([batchId, ...(openRows ?? []).map((r) => String(r.batch_id))])];
      const keys = docs.map((d) => String(d.key));
      const registered = [];
      for (let i = 0; i < keys.length; i += 500) {
        const part = keys.slice(i, i + 500);
        const rows = await this.writer.execute(
          `SELECT doc_key FROM kb_document WHERE kb_name = ? AND doc_key IN (${part.map(() => "?").join(",")})`,
          [name, ...part]
        );
        for (const r of rows ?? []) registered.push(docIdOf(name, r.doc_key));
      }
      for (let i = 0; i < registered.length; i += 200) {
        const part = registered.slice(i, i + 200);
        await this.writer.execute(
          `DELETE FROM \`${kb.table}\` WHERE JSON_UNQUOTE(JSON_EXTRACT(metadata, '$.doc_id')) IN (${part.map(() => "?").join(",")})
           AND JSON_UNQUOTE(JSON_EXTRACT(metadata, '$.batch_id')) NOT IN (${keep.map(() => "?").join(",")})`,
          [...part, ...keep]
        );
      }
      const chunkTotal = docs.reduce((n, d) => n + d.chunkCount, 0);
      timings.retireMs = ms(t0);
      t0 = now();
      for (let i = 0; i < docs.length; i += 200) {
        const part = docs.slice(i, i + 200);
        if (!part.length) continue;
        await this.writer.execute(
          `REPLACE INTO kb_document (kb_name, doc_key, doc_id, title, content_hash, chunk_count, char_count, source, batch_id)
           VALUES ${part.map(() => "(?, ?, ?, ?, ?, ?, ?, ?, ?)").join(", ")}`,
          part.flatMap((d) => [
            name,
            String(d.key),
            docIdOf(name, d.key),
            (d.title ?? "").slice(0, 512),
            d.hash,
            d.chunkCount,
            d.charCount ?? 0,
            (d.source ?? "").slice(0, 256),
            batchId,
          ])
        );
      }
      timings.registryMs = ms(t0);
      t0 = now();
      const vis = await this.waitVisible(kb, batch.probes, refresh);
      timings.refreshMs = ms(t0);
      timings.refreshMode = vis.mode;
      timings.probes = vis.probes;
      const version = await this.bumpVersion(name);
      await this.writer.execute(
        "UPDATE kb_import SET status = 'committed', chunks = ?, timings = ?, finished_at = CURRENT_TIMESTAMP(3) WHERE batch_id = ?",
        [chunkTotal, JSON.stringify(timings), batchId]
      );
      this.batches.delete(batchId);
      const stats = kbJson(await this.getKb(name));
      return { batchId, version, visible: vis.visible, timings, kb: stats };
    });
  }

  async abortImport(name, batchId) {
    const kb = await this.kbHandle(name);
    await this.writer.execute(
      `DELETE FROM \`${kb.table}\` WHERE JSON_UNQUOTE(JSON_EXTRACT(metadata, '$.batch_id')) = ?`,
      [batchId]
    );
    await this.writer.execute("UPDATE kb_import SET status = 'aborted', finished_at = CURRENT_TIMESTAMP(3) WHERE batch_id = ?", [
      batchId,
    ]);
    this.batches.delete(batchId);
    return { aborted: batchId };
  }

  async assertOpen(name, batchId) {
    const rows = await this.writer.execute("SELECT status, kb_name FROM kb_import WHERE batch_id = ?", [batchId]);
    if (!rows?.length || rows[0].kb_name !== name) throw new HttpError(404, `import ${batchId} not found`);
    if (rows[0].status !== "open") throw new HttpError(409, `import ${batchId} is ${rows[0].status}`);
  }

  // The HNSW index is maintained asynchronously (SYNC_MODE=ASYNC). Two ways to make writes searchable:
  //   explicit: CALL dbms_index_manager.refresh(), which blocks until the change stream catches up
  //   probe:    ANN-query the newest chunks by their own vectors until seekdb returns them, and fall
  //             back to the explicit refresh if that takes longer than visibilityTimeoutMs
  // The full-text index is updated synchronously, so it needs neither.
  async waitVisible(kb, probes, mode) {
    if (mode === "none" || !probes.length) return { mode: "none", visible: !probes.length, probes: 0 };
    if (mode === "explicit") {
      await this.writer.execute("CALL dbms_index_manager.refresh()");
      return { mode: "explicit", visible: await this.allVisible(kb, probes), probes: probes.length };
    }
    const deadline = Date.now() + this.cfg.visibilityTimeoutMs;
    let rounds = 0;
    while (Date.now() < deadline) {
      rounds++;
      if (await this.allVisible(kb, probes)) return { mode: "probe", visible: true, probes: probes.length, rounds };
      await sleep(25);
    }
    await this.writer.execute("CALL dbms_index_manager.refresh()");
    return { mode: "probe+explicit", visible: await this.allVisible(kb, probes), probes: probes.length, rounds };
  }

  async allVisible(kb, probes) {
    // The change stream applies commits in order, so the last row of each write call is enough.
    for (const p of probes.slice(-4)) {
      const rows = await this.writer.execute(
        `SELECT _id FROM \`${kb.table}\` ORDER BY cosine_distance(embedding, ?) APPROXIMATE LIMIT 1`,
        [JSON.stringify(p.embedding)]
      );
      if (rows?.[0]?._id?.toString() !== p.id) return false;
    }
    return true;
  }

  async bumpVersion(name) {
    const kb = await this.kbHandle(name);
    const [{ n }] = await this.writer.execute(`SELECT COUNT(*) AS n FROM \`${kb.table}\``);
    const [{ d }] = await this.writer.execute("SELECT COUNT(*) AS d FROM kb_document WHERE kb_name = ?", [name]);
    await this.writer.execute(
      "UPDATE kb_registry SET version = version + 1, chunk_count = ?, doc_count = ?, updated_at = CURRENT_TIMESTAMP(3) WHERE name = ?",
      [Number(n), Number(d), name]
    );
    const [row] = await this.writer.execute(
      "SELECT name, collection, model_id, dim, version, doc_count, chunk_count, created_at, updated_at FROM kb_registry WHERE name = ?",
      [name]
    );
    // All writes go through this process, so the cached registry row stays authoritative.
    kb.row = row;
    return Number(row.version);
  }

  async deleteDoc(name, key) {
    return this.mutex.run(name, async () => {
      const kb = await this.kbHandle(name);
      const t0 = now();
      await this.writer.execute(
        `DELETE FROM \`${kb.table}\` WHERE JSON_UNQUOTE(JSON_EXTRACT(metadata, '$.doc_id')) = ?`,
        [docIdOf(name, key)]
      );
      await this.writer.execute("DELETE FROM kb_document WHERE kb_name = ? AND doc_key = ?", [name, key]);
      const version = await this.bumpVersion(name);
      return { deleted: key, version, dbMs: ms(t0), kb: kbJson(await this.getKb(name)) };
    });
  }

  // ---------------------------------------------------------------- retrieval

  // mode: hybrid | vector | fulltext; fusion: rrf | weighted; impl: search (one DBMS_HYBRID_SEARCH.SEARCH
  // round trip, embeddings left out of the payload) | sdk (seekdb-js Collection.hybridSearch, which
  // runs SET + GET_SQL + the generated SQL and returns embeddings too). Both fuse inside seekdb.
  async search(name, opts) {
    const {
      text = "",
      vector,
      mode = "hybrid",
      topK = 10,
      window = 50,
      fusion = "rrf",
      rankConstant = 60,
      vectorWeight = 0.7,
      impl = "search",
    } = opts;
    const kb = await this.kbHandle(name);
    const k = Math.max(1, Math.min(100, Number(topK) || 10));
    const win = Math.max(k, Math.min(200, Number(window) || 50));
    const ftText = sanitizeFulltext(text);
    const useText = mode !== "vector" && ftText.length > 0;
    const useVector = mode !== "fulltext";
    if (useVector && (!Array.isArray(vector) || vector.length !== kb.row.dim)) {
      throw new HttpError(400, `query vector must have ${kb.row.dim} dimensions`);
    }
    if (!useText && !useVector) return { hits: [], dbMs: 0, kbVersion: Number(kb.row.version), impl, params: null };

    const t0 = now();
    if (impl === "sdk") {
      const col = await this.readerCollection(name, kb);
      const res = await col.hybridSearch({
        query: useText ? { whereDocument: { $contains: ftText } } : undefined,
        knn: useVector ? { queryEmbeddings: [vector], nResults: win } : undefined,
        rank: useText && useVector && fusion === "rrf" ? { rrf: { rankWindowSize: win, rankConstant } } : undefined,
        nResults: k,
      });
      const dbMs = ms(t0);
      const hits = res.ids[0].map((id, i) => ({
        id,
        score: res.distances[0][i],
        text: res.documents?.[0]?.[i] ?? "",
        meta: res.metadatas?.[0]?.[i] ?? {},
      }));
      return { hits, dbMs, kbVersion: Number(kb.row.version), impl };
    }

    const params = { size: k, _source: ["_id", "document", "metadata"] };
    if (useText) params.query = { match: { document: ftText } };
    if (useVector) params.knn = { field: "embedding", k: win, query_vector: vector };
    if (useText && useVector) {
      // Per-route scores exist under both fusions; per-route ranks only under RRF (seekdb 1.4.0 answers
      // "Unknown column '_keyword_rank'" for a weighted sum).
      params._source.push("_keyword_score", "_semantic_score");
      if (fusion === "rrf") {
        params._source.push("_keyword_rank", "_semantic_rank");
        params.rank = { rrf: { rank_window_size: win, rank_constant: rankConstant } };
      } else {
        // Weighted sum of the raw route scores (BM25-style relevance and 1 - cosine/2), done by seekdb.
        params.query = { match: { document: { query: ftText, boost: 1 - vectorWeight } } };
        params.knn.boost = vectorWeight;
      }
    }
    const rows = await this.reader.execute("SELECT DBMS_HYBRID_SEARCH.SEARCH(?, ?) AS r", [kb.table, JSON.stringify(params)]);
    const dbMs = ms(t0);
    const raw = parseJson(rows?.[0]?.r) ?? [];
    const hits = raw.map((r) => ({
      id: String(r._id),
      score: r._score,
      text: r.document ?? "",
      meta: parseJson(r.metadata) ?? {},
      keywordRank: r._keyword_rank ?? null,
      semanticRank: r._semantic_rank ?? null,
      keywordScore: r._keyword_score ?? null,
      semanticScore: r._semantic_score ?? null,
    }));
    const shown = { ...params, knn: params.knn && { ...params.knn, query_vector: `[${kb.row.dim} floats]` } };
    return { hits, dbMs, kbVersion: Number(kb.row.version), impl, params: shown };
  }

  async readerCollection(name, kb) {
    if (!kb.reader) kb.reader = await this.reader.getCollection({ name: kb.row.collection, embeddingFunction: null });
    return kb.reader;
  }
}

function kbJson(r) {
  return {
    name: r.name,
    modelId: r.model_id,
    dim: Number(r.dim),
    version: Number(r.version),
    docs: Number(r.doc_count),
    chunks: Number(r.chunk_count),
    createdAt: r.created_at,
    updatedAt: r.updated_at,
  };
}
