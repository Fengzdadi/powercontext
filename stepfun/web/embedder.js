// Main-thread handle for the embedding worker (promise RPC + streamed batches).
export class Embedder {
  constructor() {
    this.worker = null;
    this.pending = new Map();
    this.seq = 0;
    this.info = null;
    this.onEvent = () => {};
  }

  start(options = {}) {
    this.stop();
    this.worker = new Worker(new URL("./embed-worker.js", import.meta.url), { type: "module" });
    this.worker.onmessage = ({ data }) => this.#dispatch(data);
    this.worker.onerror = (e) => {
      const err = new Error(e.message || "embedding worker crashed");
      for (const p of this.pending.values()) p.reject(err);
      this.pending.clear();
      this.onEvent({ type: "status", phase: "error", error: err.message });
    };
    this.ready = this.#call({ type: "init", options }).then((info) => (this.info = info));
    return this.ready;
  }

  stop() {
    this.worker?.terminate();
    this.worker = null;
    this.info = null;
    for (const p of this.pending.values()) p.reject(new Error("worker stopped"));
    this.pending.clear();
  }

  // Resolves with { vectors: Float32Array(n*dim) | null, dim, timings }. With onBatch, vectors arrive
  // per batch while the worker keeps going (so the caller can write them to seekdb in parallel).
  embed(texts, { kind = "passage", onBatch, ...opts } = {}) {
    return this.#call({ type: "embed", texts, kind, stream: Boolean(onBatch), ...opts }, onBatch);
  }

  async embedQuery(text, opts = {}) {
    const r = await this.embed([text], { kind: "query", ...opts });
    return { vector: Array.from(r.vectors), timings: r.timings };
  }

  clearQueryCache() {
    return this.#call({ type: "clearQueryCache" });
  }

  #call(msg, onBatch) {
    if (!this.worker) return Promise.reject(new Error("embedder not started"));
    const id = ++this.seq;
    return new Promise((resolve, reject) => {
      this.pending.set(id, { resolve, reject, onBatch });
      this.worker.postMessage({ ...msg, id });
    });
  }

  #dispatch(m) {
    if (m.type === "event" || m.id === undefined) return this.onEvent(m);
    const p = this.pending.get(m.id);
    if (!p) return;
    if (m.type === "batch") return p.onBatch?.(m);
    this.pending.delete(m.id);
    if (m.type === "error") p.reject(Object.assign(new Error(m.error), { stack: m.stack }));
    else p.resolve(m);
  }
}
