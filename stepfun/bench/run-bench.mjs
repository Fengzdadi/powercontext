// Drives web/bench.html in the locally installed Google Chrome (Playwright, `channel: "chrome"`).
//   node bench/run-bench.mjs <plan> [--headed] [--only <regex>] [--url http://127.0.0.1:5280]
// Plans: full (everything below), load, quality, batch, import, query, fallback.
// "No WebGPU" runs launch Chrome with --disable-gpu, which makes requestAdapter() return null, i.e. a
// genuine WebGPU-unavailable environment (not just the app's ?backend=wasm switch).
import { chromium } from "playwright-core";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { ROOT } from "../server/config.mjs";

const args = process.argv.slice(2);
const plan = args.find((a) => !a.startsWith("--")) ?? "full";
const flag = (n) => args.includes(n);
const opt = (n, d) => (args.includes(n) ? args[args.indexOf(n) + 1] : d);
const BASE = opt("--url", "http://127.0.0.1:5280");
const only = opt("--only") ? new RegExp(opt("--only")) : null;
const headless = !flag("--headed");
const stamp = opt("--stamp", new Date().toISOString().slice(0, 10));

const GPU_ARGS = ["--enable-unsafe-webgpu", "--enable-features=Vulkan", "--ignore-gpu-blocklist"];
const NO_GPU_ARGS = ["--disable-gpu"];

// [name, query string, { gpu, profile }]. profile "fresh" = new empty profile (cold caches);
// "shared" = one persistent profile reused across runs (model already in Cache Storage).
const RUNS = {
  load: [
    ...[1, 2, 3].map((i) => [`load-cold-webgpu-fp16-${i}`, "suite=load&backend=webgpu&dtype=fp16", { gpu: true, profile: "fresh", reload: true }]),
    ...[1, 2, 3].map((i) => [`load-cold-wasm-int8-${i}`, "suite=load&backend=wasm&dtype=int8", { gpu: false, profile: "fresh", reload: true }]),
    ...[1, 2, 3].map((i) => [`load-cold-webgpu-fp32-${i}`, "suite=load&backend=webgpu&dtype=fp32", { gpu: true, profile: "fresh", reload: true }]),
  ],
  quality: [
    ["quality-webgpu-fp32", "suite=quality&backend=webgpu&dtype=fp32", { gpu: true }],
    ["quality-webgpu-fp16", "suite=quality&backend=webgpu&dtype=fp16", { gpu: true }],
    ["quality-webgpu-int8", "suite=quality&backend=webgpu&dtype=int8", { gpu: true }],
    ["quality-wasm-fp32", "suite=quality&backend=auto&dtype=fp32", { gpu: false }],
    ["quality-wasm-int8", "suite=quality&backend=auto&dtype=int8", { gpu: false }],
    ["quality-wasm-fp16", "suite=quality&backend=auto&dtype=fp16", { gpu: false }],
    // the variants written by scripts/quantize.py (npm run quantize)
    ["quality-webgpu-fp16-local", "suite=quality&backend=webgpu&dtype=fp16&source=local", { gpu: true }],
    ["quality-wasm-int8-local", "suite=quality&backend=auto&dtype=int8&source=local", { gpu: false }],
  ],
  batch: [
    ["batch-webgpu-fp16", "suite=batch&backend=webgpu&dtype=fp16", { gpu: true }],
    ["batch-wasm-int8", "suite=batch&backend=auto&dtype=int8&texts=128", { gpu: false }],
    ["batch-wasm-int8-1thread", "suite=batch&backend=auto&dtype=int8&threads=1&texts=64&quick=1", { gpu: false }],
  ],
  import: [
    ["import-webgpu-fp16", "suite=import&backend=webgpu&dtype=fp16", { gpu: true }],
    ["import-webgpu-fp16-sequential", "suite=import&backend=webgpu&dtype=fp16&pipelined=0", { gpu: true }],
  ],
  // two more pipelined/sequential pairs in the opposite order first (ABBA, so position effects cancel);
  // report.mjs takes the median of the three
  "import-repeat": [
    ["import-webgpu-fp16-sequential-2", "suite=import&backend=webgpu&dtype=fp16&pipelined=0", { gpu: true }],
    ["import-webgpu-fp16-2", "suite=import&backend=webgpu&dtype=fp16", { gpu: true }],
    ["import-webgpu-fp16-3", "suite=import&backend=webgpu&dtype=fp16", { gpu: true }],
    ["import-webgpu-fp16-sequential-3", "suite=import&backend=webgpu&dtype=fp16&pipelined=0", { gpu: true }],
  ],
  query: [
    ["query-prep-webgpu-fp16", "suite=quality&backend=webgpu&dtype=fp16&keep=1&kb=bench_query&repeats=1", { gpu: true }],
    ["query-webgpu-fp16", "suite=query&backend=webgpu&dtype=fp16&kb=bench_query", { gpu: true }],
    ["query-wasm-int8", "suite=query&backend=auto&dtype=int8&kb=bench_query", { gpu: false }],
  ],
  fallback: [
    // auto backend selection in both environments: must pick WebGPU when available, WASM otherwise
    ["fallback-auto-gpu", "suite=load&backend=auto&dtype=auto", { gpu: true }],
    ["fallback-auto-nogpu", "suite=load&backend=auto&dtype=auto", { gpu: false }],
  ],
};
RUNS.full = [...RUNS.fallback, ...RUNS.load, ...RUNS.batch, ...RUNS.quality, ...RUNS.import, ...RUNS["import-repeat"], ...RUNS.query];

const runLogFile = path.join(ROOT, "bench", "results", `${stamp}__runs-${plan}.json`);
const runLog = [];
const hostInfo = { os: `${os.type()} ${os.release()} ${os.arch()}`, cpu: os.cpus()[0]?.model, cores: os.cpus().length, memGB: Math.round(os.totalmem() / 2 ** 30) };
const profilesDir = path.join(ROOT, "bench", "results", "tmp");
fs.mkdirSync(profilesDir, { recursive: true });
const browserVersion = { gpu: null, nogpu: null };

async function launch(gpu, profile) {
  const dir = profile === "fresh" ? fs.mkdtempSync(path.join(profilesDir, "profile-")) : path.join(profilesDir, gpu ? "shared-gpu" : "shared-nogpu");
  const ctx = await chromium.launchPersistentContext(dir, {
    channel: "chrome",
    headless,
    args: gpu ? GPU_ARGS : NO_GPU_ARGS,
    viewport: { width: 1280, height: 900 },
  });
  return { ctx, dir, fresh: profile === "fresh" };
}

async function runOne(name, qs, { gpu, profile = "shared", reload = false }) {
  const { ctx, dir, fresh } = await launch(gpu, profile);
  const results = [];
  try {
    const page = ctx.pages()[0] ?? (await ctx.newPage());
    page.on("console", (m) => {
      if (m.type() === "error") console.log(`  [console.${m.type()}] ${m.text().slice(0, 300)}`);
    });
    const loads = reload ? [`${name}-cold`, `${name}-warm`] : [name];
    for (const label of loads) {
      const t0 = Date.now();
      const loadBefore = os.loadavg();
      await page.goto(`${BASE}/bench.html?${qs}&label=${stamp}__${label}`, { waitUntil: "load" });
      await page.waitForFunction(() => window.__benchDone === true, null, { timeout: 60 * 60 * 1000, polling: 500 });
      const r = await page.evaluate(() => window.__benchResult);
      const gpuInfo = await page.evaluate(async () => {
        const a = navigator.gpu ? await navigator.gpu.requestAdapter() : null;
        return a ? { vendor: a.info?.vendor, architecture: a.info?.architecture } : null;
      });
      browserVersion[gpu ? "gpu" : "nogpu"] = ctx.browser()?.version() ?? r.env?.brands?.join(", ");
      console.log(`${r.ok ? "ok  " : "FAIL"} ${label} (${((Date.now() - t0) / 1000).toFixed(1)} s) backend=${r.init?.backend} dtype=${r.init?.dtype} adapter=${JSON.stringify(gpuInfo)}${r.ok ? "" : "\n" + r.error}`);
      results.push(r);
      // the page saves its own measurements; this log adds what only the runner knows
      runLog.push({
        label: `${stamp}__${label}`,
        ok: r.ok,
        wallSec: (Date.now() - t0) / 1000,
        chrome: browserVersion[gpu ? "gpu" : "nogpu"],
        chromeArgs: gpu ? GPU_ARGS : NO_GPU_ARGS,
        profile: fresh ? "fresh" : "shared",
        adapter: gpuInfo,
        loadavgBefore: loadBefore.map((x) => Math.round(x * 10) / 10),
        loadavgAfter: os.loadavg().map((x) => Math.round(x * 10) / 10),
      });
      fs.writeFileSync(runLogFile, JSON.stringify({ host: hostInfo, runs: runLog }, null, 2));
    }
  } finally {
    await ctx.close();
    if (fresh) fs.rmSync(dir, { recursive: true, force: true });
  }
  return results;
}

const runs = RUNS[plan];
if (!runs) {
  console.error(`unknown plan ${plan}; one of ${Object.keys(RUNS).join(", ")}`);
  process.exit(2);
}
let failed = 0;
for (const [name, qs, o] of runs) {
  if (only && !only.test(name)) continue;
  try {
    const rs = await runOne(name, qs, o);
    failed += rs.filter((r) => !r.ok).length;
  } catch (e) {
    failed++;
    console.log(`FAIL ${name}: ${e.message}`);
  }
}
console.log(`done: ${failed} failed`);
process.exit(failed ? 1 : 0);
