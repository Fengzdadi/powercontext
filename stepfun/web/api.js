// Thin client for the local server's JSON API. Each call returns the parsed body plus `clientMs`
// (round trip measured in the browser) so callers can separate network time from seekdb time.
async function call(method, path, body) {
  const t0 = performance.now();
  const res = await fetch(path, {
    method,
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  const data = await res.json().catch(() => ({ error: `HTTP ${res.status}` }));
  const clientMs = performance.now() - t0;
  if (!res.ok) throw Object.assign(new Error(data.error || `HTTP ${res.status}`), { status: res.status });
  return { ...data, clientMs };
}

const kb = (name) => `/api/kbs/${encodeURIComponent(name)}`;

export const api = {
  health: () => call("GET", "/api/health"),
  models: () => call("GET", "/api/models"),
  listKbs: () => call("GET", "/api/kbs"),
  createKb: (body) => call("POST", "/api/kbs", body),
  getKb: (name) => call("GET", kb(name)),
  deleteKb: (name) => call("DELETE", kb(name)),
  listDocs: (name) => call("GET", `${kb(name)}/docs`),
  deleteDoc: (name, key) => call("DELETE", `${kb(name)}/docs?key=${encodeURIComponent(key)}`),
  listImports: (name) => call("GET", `${kb(name)}/imports`),
  openImport: (name, body) => call("POST", `${kb(name)}/imports`, body),
  writeChunks: (name, batchId, chunks) => call("POST", `${kb(name)}/imports/${batchId}/chunks`, { chunks }),
  commitImport: (name, batchId, body) => call("POST", `${kb(name)}/imports/${batchId}/commit`, body),
  abortImport: (name, batchId) => call("DELETE", `${kb(name)}/imports/${batchId}`),
  search: (name, body) => call("POST", `${kb(name)}/search`, body),
  saveBench: (body) => call("POST", "/api/bench/results", body),
};
