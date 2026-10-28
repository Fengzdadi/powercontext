// Local app server: static web app + model files + JSON API over seekdb. No inference happens here;
// the browser computes every embedding and only sends vectors and text.
import http from "node:http";
import fs from "node:fs";
import fsp from "node:fs/promises";
import path from "node:path";
import { createRequire } from "node:module";
import { config, ROOT } from "./config.mjs";
import { KbStore, HttpError } from "./store.mjs";

// Package roots are looked up on the node_modules search path (their package.json is not exported).
function packageDir(name, fromFile) {
  for (const dir of createRequire(fromFile).resolve.paths(name) ?? []) {
    if (fs.existsSync(path.join(dir, name, "package.json"))) return path.join(dir, name);
  }
  throw new Error(`cannot find package ${name}; run npm install`);
}
const transformersDir = packageDir("@huggingface/transformers", import.meta.url);
const transformersDist = path.join(transformersDir, "dist");
// The ORT build that Transformers.js was bundled against (its exact dependency), not any other copy.
const ortDist = path.join(packageDir("onnxruntime-web", path.join(transformersDir, "package.json")), "dist");

const STATIC_ROOTS = [
  ["/vendor/transformers/", transformersDist, "long"],
  ["/vendor/ort/", ortDist, "long"],
  ["/models/", config.modelsDir, "long"],
  ["/eval/", path.join(ROOT, "eval", "data"), "short"],
  ["/samples/", path.join(ROOT, "samples"), "short"],
  ["/", path.join(ROOT, "web"), "short"],
];

const MIME = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".mjs": "text/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".jsonl": "application/x-ndjson; charset=utf-8",
  ".tsv": "text/tab-separated-values; charset=utf-8",
  ".txt": "text/plain; charset=utf-8",
  ".md": "text/markdown; charset=utf-8",
  ".svg": "image/svg+xml",
  ".wasm": "application/wasm",
  ".onnx": "application/octet-stream",
  ".model": "application/octet-stream",
  ".map": "application/json; charset=utf-8",
};

// Cross-origin isolation unlocks SharedArrayBuffer, which ONNX Runtime Web needs for multi-threaded WASM.
const ISOLATION_HEADERS = {
  "Cross-Origin-Opener-Policy": "same-origin",
  "Cross-Origin-Embedder-Policy": "require-corp",
  "Cross-Origin-Resource-Policy": "same-origin",
};

const store = new KbStore(config);

function send(res, status, body, headers = {}) {
  const data = typeof body === "string" || Buffer.isBuffer(body) ? body : JSON.stringify(body);
  res.writeHead(status, {
    ...ISOLATION_HEADERS,
    "Content-Type": typeof body === "string" ? "text/plain; charset=utf-8" : "application/json; charset=utf-8",
    "Cache-Control": "no-store",
    ...headers,
  });
  res.end(data);
}

async function readJson(req, limit = 64 * 1024 * 1024) {
  const chunks = [];
  let size = 0;
  for await (const c of req) {
    size += c.length;
    if (size > limit) throw new HttpError(413, "request body too large");
    chunks.push(c);
  }
  if (!size) return {};
  try {
    return JSON.parse(Buffer.concat(chunks).toString("utf8"));
  } catch {
    throw new HttpError(400, "invalid JSON body");
  }
}

async function serveStatic(req, res, url) {
  const entry = STATIC_ROOTS.find(([prefix]) => url.pathname.startsWith(prefix));
  if (!entry) return false;
  const [prefix, dir, caching] = entry;
  let rel = decodeURIComponent(url.pathname.slice(prefix.length));
  if (rel === "" || rel.endsWith("/")) rel += "index.html";
  const file = path.resolve(dir, rel);
  if (!file.startsWith(path.resolve(dir) + path.sep)) return send(res, 403, "forbidden"), true;
  let st;
  try {
    st = await fsp.stat(file);
  } catch {
    return false;
  }
  if (!st.isFile()) return false;
  const etag = `"${st.size.toString(16)}-${Math.floor(st.mtimeMs).toString(16)}"`;
  const headers = {
    ...ISOLATION_HEADERS,
    "Content-Type": MIME[path.extname(file).toLowerCase()] ?? "application/octet-stream",
    "Content-Length": st.size,
    ETag: etag,
    // Vendor bundles and model weights are immutable per version; app files revalidate every load.
    "Cache-Control": caching === "long" ? "public, max-age=604800" : "no-cache",
  };
  if (req.headers["if-none-match"] === etag) {
    res.writeHead(304, headers);
    res.end();
    return true;
  }
  res.writeHead(200, headers);
  if (req.method === "HEAD") return res.end(), true;
  fs.createReadStream(file).pipe(res);
  return true;
}

async function listLocalModels() {
  const out = [];
  async function walk(dir) {
    let entries = [];
    try {
      entries = await fsp.readdir(dir, { withFileTypes: true });
    } catch {
      return;
    }
    for (const e of entries) {
      const p = path.join(dir, e.name);
      if (e.isDirectory()) await walk(p);
      else if (e.name.endsWith(".onnx")) {
        const st = await fsp.stat(p);
        out.push({ path: path.relative(config.modelsDir, p).split(path.sep).join("/"), bytes: st.size });
      }
    }
  }
  await walk(config.modelsDir);
  return out;
}

const routes = [
  ["GET", /^\/api\/health$/, async () => ({ ok: true, seekdb: store.version, mode: config.seekdb.path ? "embedded" : "server", database: config.seekdb.database })],
  ["GET", /^\/api\/models$/, async () => ({ files: await listLocalModels() })],
  ["GET", /^\/api\/kbs$/, async () => ({ kbs: await store.listKbs() })],
  ["POST", /^\/api\/kbs$/, async (req) => store.createKb(await readJson(req))],
  ["GET", /^\/api\/kbs\/([^/]+)$/, async (req, [name]) => {
    const kb = await store.getKb(name);
    return { name: kb.name, modelId: kb.model_id, dim: Number(kb.dim), version: Number(kb.version), docs: Number(kb.doc_count), chunks: Number(kb.chunk_count) };
  }],
  ["DELETE", /^\/api\/kbs\/([^/]+)$/, async (req, [name]) => store.deleteKb(name)],
  ["GET", /^\/api\/kbs\/([^/]+)\/docs$/, async (req, [name]) => ({ docs: await store.listDocs(name) })],
  ["DELETE", /^\/api\/kbs\/([^/]+)\/docs$/, async (req, [name], url) => store.deleteDoc(name, url.searchParams.get("key") ?? "")],
  ["GET", /^\/api\/kbs\/([^/]+)\/imports$/, async (req, [name], url) => ({ imports: await store.listImports(name, url.searchParams.get("limit")) })],
  ["POST", /^\/api\/kbs\/([^/]+)\/imports$/, async (req, [name]) => store.openImport(name, await readJson(req))],
  ["POST", /^\/api\/kbs\/([^/]+)\/imports\/([^/]+)\/chunks$/, async (req, [name, batch]) => store.writeChunks(name, batch, (await readJson(req)).chunks ?? [])],
  ["POST", /^\/api\/kbs\/([^/]+)\/imports\/([^/]+)\/commit$/, async (req, [name, batch]) => store.commitImport(name, batch, await readJson(req))],
  ["DELETE", /^\/api\/kbs\/([^/]+)\/imports\/([^/]+)$/, async (req, [name, batch]) => store.abortImport(name, batch)],
  ["POST", /^\/api\/kbs\/([^/]+)\/search$/, async (req, [name]) => store.search(name, await readJson(req))],
  ["POST", /^\/api\/bench\/results$/, async (req) => {
    const body = await readJson(req);
    const label = String(body.label ?? "run").replace(/[^a-zA-Z0-9_.-]/g, "_").slice(0, 80);
    await fsp.mkdir(config.benchResultsDir, { recursive: true });
    const file = path.join(config.benchResultsDir, `${label}.json`);
    // pretty-printed, except that number arrays (embedding vectors) stay on one line
    await fsp.writeFile(file, JSON.stringify(body, null, 2).replace(/\[\s+(-?\d[^[\]{}"]*?)\s+\]/g, (m, inner) => `[${inner.replace(/\s+/g, "")}]`));
    return { saved: path.relative(ROOT, file) };
  }],
];

const server = http.createServer(async (req, res) => {
  const t0 = performance.now();
  const url = new URL(req.url, `http://${req.headers.host ?? "localhost"}`);
  try {
    if (url.pathname.startsWith("/api/")) {
      const route = routes.find(([m, re]) => m === req.method && re.test(url.pathname));
      if (!route) throw new HttpError(404, `no route for ${req.method} ${url.pathname}`);
      const params = url.pathname.match(route[1]).slice(1).map(decodeURIComponent);
      const out = await route[2](req, params, url);
      const serverMs = Math.round((performance.now() - t0) * 100) / 100;
      return send(res, 200, { ...out, serverMs }, { "Server-Timing": `app;dur=${serverMs}` });
    }
    if ((req.method === "GET" || req.method === "HEAD") && (await serveStatic(req, res, url))) return;
    send(res, 404, "not found");
  } catch (e) {
    const status = e instanceof HttpError ? e.status : 500;
    if (status >= 500) console.error(`[${req.method} ${url.pathname}]`, e);
    send(res, status, { error: e.message ?? String(e) });
  }
});

const version = await store.init().catch((e) => {
  const s = config.seekdb;
  console.error(`\nCannot reach seekdb at ${s.path ? `path ${s.path}` : `${s.host}:${s.port}`}: ${e.message}`);
  console.error("Start it with `npm run db:start` (Docker) or point SEEKDB_HOST/SEEKDB_PORT at a running seekdb.\n");
  process.exit(1);
});
server.listen(config.port, config.host, () => {
  console.log(`seekdb ${version} connected (${config.seekdb.path ? "embedded" : `${config.seekdb.host}:${config.seekdb.port}`}, database ${config.seekdb.database})`);
  console.log(`Edge KB app: http://localhost:${config.port}/`);
});

for (const sig of ["SIGINT", "SIGTERM"]) {
  process.on(sig, async () => {
    server.close();
    await store.close();
    process.exit(0);
  });
}
