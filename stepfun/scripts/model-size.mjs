// Model size before/after quantisation, measured on the files the app actually serves.
//   node scripts/model-size.mjs        -> table on stdout + bench/results/model-size.json
// Covers the pinned Hugging Face files (npm run fetch-model) and, when present, the files written by
// scripts/quantize.py (npm run quantize). The ratio is FP32 bytes / variant bytes.
import fs from "node:fs";
import path from "node:path";
import crypto from "node:crypto";
import { MODEL } from "../web/model-config.js";
import { ROOT } from "../server/config.mjs";

const sources = [
  ["huggingface", path.join(ROOT, "models", MODEL.repo)],
  ["local", path.join(ROOT, "models", MODEL.localRepo)],
];
const sha256 = (file) =>
  new Promise((resolve, reject) => {
    const h = crypto.createHash("sha256");
    fs.createReadStream(file).on("data", (d) => h.update(d)).on("end", () => resolve(h.digest("hex"))).on("error", reject);
  });

const fp32File = path.join(ROOT, "models", MODEL.repo, MODEL.files.fp32);
if (!fs.existsSync(fp32File)) {
  console.error(`missing ${path.relative(ROOT, fp32File)}: run npm run fetch-model first`);
  process.exit(1);
}
const fp32Bytes = fs.statSync(fp32File).size;
// What the browser downloads besides the ONNX file (Transformers.js fetches these three; the load
// benchmark's init.bytes matches ONNX + these exactly). Same for every precision.
const SHARED_FILES = ["config.json", "tokenizer.json", "tokenizer_config.json"];
const sharedBytes = SHARED_FILES.reduce((s, f) => s + fs.statSync(path.join(ROOT, "models", MODEL.repo, f)).size, 0);
const rows = [];
for (const [source, dir] of sources) {
  for (const [dtype, rel] of Object.entries(MODEL.files)) {
    const file = path.join(dir, rel);
    if (!fs.existsSync(file) || (source === "local" && dtype === "fp32")) continue;
    const bytes = fs.statSync(file).size;
    rows.push({
      source,
      dtype,
      file: path.relative(ROOT, file),
      bytes,
      mib: Math.round((bytes / 2 ** 20) * 10) / 10,
      ratio: Math.round((fp32Bytes / bytes) * 1000) / 1000,
      reductionPct: Math.round((1 - bytes / fp32Bytes) * 1000) / 10,
      downloadBytes: bytes + sharedBytes,
      downloadRatio: Math.round(((fp32Bytes + sharedBytes) / (bytes + sharedBytes)) * 1000) / 1000,
      sha256: await sha256(file),
    });
  }
}
console.log("source       dtype       bytes      MiB   ratio  reduction   download  ratio");
for (const r of rows) {
  console.log(
    `${r.source.padEnd(12)} ${r.dtype.padEnd(5)} ${String(r.bytes).padStart(11)} ${r.mib.toFixed(1).padStart(8)}  x${r.ratio.toFixed(2)}  ${r.reductionPct.toFixed(1).padStart(5)}%  ${String(r.downloadBytes).padStart(11)}  x${r.downloadRatio.toFixed(2)}`
  );
}
const out = path.join(ROOT, "bench", "results", "model-size.json");
fs.mkdirSync(path.dirname(out), { recursive: true });
fs.writeFileSync(
  out,
  JSON.stringify({ model: `${MODEL.repo}@${MODEL.revision}`, upstream: MODEL.upstream, fp32Bytes, sharedFiles: SHARED_FILES, sharedBytes, rows, at: new Date().toISOString() }, null, 2)
);
console.log(`wrote ${path.relative(ROOT, out)}`);
