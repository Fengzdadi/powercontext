// Downloads the embedding model into models/<repo>/ so the app serves it locally (no CDN at runtime).
//   node scripts/fetch-model.mjs [--repo Xenova/multilingual-e5-small] [--revision <sha>] [--fp32-only]
// HF_ENDPOINT=https://hf-mirror.com selects a mirror. Existing files with the expected size are skipped.
import fs from "node:fs";
import fsp from "node:fs/promises";
import path from "node:path";
import { Readable } from "node:stream";
import { pipeline } from "node:stream/promises";
import { ROOT } from "../server/config.mjs";
import { MODEL } from "../web/model-config.js";

const args = process.argv.slice(2);
const opt = (name, dflt) => {
  const i = args.indexOf(name);
  return i >= 0 ? args[i + 1] : dflt;
};
const repo = opt("--repo", MODEL.repo);
const revision = opt("--revision", MODEL.revision);
const fp32Only = args.includes("--fp32-only");
const endpoint = (process.env.HF_ENDPOINT || "https://huggingface.co").replace(/\/$/, "");

const files = [
  "config.json",
  "tokenizer.json",
  "tokenizer_config.json",
  "special_tokens_map.json",
  "onnx/model.onnx", // fp32 baseline, the input of scripts/quantize.py
  ...(fp32Only ? [] : ["onnx/model_fp16.onnx", "onnx/model_int8.onnx"]), // prebuilt variants (same recipe)
];

const outDir = path.join(ROOT, "models", repo);
const listing = await fetch(`${endpoint}/api/models/${repo}/tree/${revision}?recursive=1`).then((r) => {
  if (!r.ok) throw new Error(`listing ${repo}@${revision} failed: HTTP ${r.status}`);
  return r.json();
});
const sizes = Object.fromEntries(listing.filter((f) => f.type === "file").map((f) => [f.path, f.size]));

for (const f of files) {
  const dest = path.join(outDir, f);
  const expected = sizes[f];
  if (expected === undefined) throw new Error(`${repo} has no ${f}`);
  const have = fs.existsSync(dest) ? fs.statSync(dest).size : -1;
  if (have === expected) {
    console.log(`ok    ${f} (${(expected / 1e6).toFixed(1)} MB, cached)`);
    continue;
  }
  await fsp.mkdir(path.dirname(dest), { recursive: true });
  const url = `${endpoint}/${repo}/resolve/${revision}/${f}`;
  const t0 = performance.now();
  const res = await fetch(url, { redirect: "follow" });
  if (!res.ok) throw new Error(`GET ${url}: HTTP ${res.status}`);
  let done = 0;
  let lastLog = 0;
  const progress = new TransformStream({
    transform(chunk, ctrl) {
      done += chunk.byteLength;
      if (expected > 20e6 && performance.now() - lastLog > 2000) {
        lastLog = performance.now();
        process.stdout.write(`      ${f} ${((done / expected) * 100).toFixed(0)}%\n`);
      }
      ctrl.enqueue(chunk);
    },
  });
  await pipeline(Readable.fromWeb(res.body.pipeThrough(progress)), fs.createWriteStream(dest + ".part"));
  await fsp.rename(dest + ".part", dest);
  const secs = (performance.now() - t0) / 1000;
  console.log(`fetch ${f} (${(expected / 1e6).toFixed(1)} MB in ${secs.toFixed(1)} s)`);
}
console.log(`model files in ${path.relative(process.cwd(), outDir) || outDir}`);
