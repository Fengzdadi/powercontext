// End-to-end UI test in Google Chrome, run once with WebGPU available and once with the GPU disabled
// (WebGPU unavailable -> the app must fall back to WASM by itself and say so).
//   node bench/e2e.mjs [--headed] [--only gpu|nogpu] [--url http://127.0.0.1:5280]
// Writes screenshots and a JSON log to bench/results/e2e/.
import { chromium } from "playwright-core";
import fs from "node:fs";
import path from "node:path";
import assert from "node:assert/strict";
import { ROOT } from "../server/config.mjs";

const args = process.argv.slice(2);
const opt = (n, d) => (args.includes(n) ? args[args.indexOf(n) + 1] : d);
const BASE = opt("--url", "http://127.0.0.1:5280");
const only = opt("--only");
const outDir = path.join(ROOT, "bench", "results", "e2e");
fs.mkdirSync(outDir, { recursive: true });

const ENVS = [
  { name: "gpu", args: [], expect: "WebGPU" },
  { name: "nogpu", args: ["--disable-gpu"], expect: "WASM" },
];

async function run(envDef) {
  const log = [];
  const step = (name, data = {}) => {
    log.push({ step: name, ...data });
    console.log(`  [${envDef.name}] ${name}`, Object.keys(data).length ? JSON.stringify(data) : "");
  };
  const browser = await chromium.launch({ channel: "chrome", headless: !args.includes("--headed"), args: envDef.args });
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  page.on("dialog", (d) => d.accept());
  for (const f of fs.readdirSync(outDir)) if (f.startsWith(`${envDef.name}-`) && /\.(png|jpg)$/.test(f)) fs.rmSync(path.join(outDir, f));
  const shot = (n) => page.screenshot({ path: path.join(outDir, `${envDef.name}-${n}.jpg`), fullPage: true, type: "jpeg", quality: 70 });
  const kb = `e2e_${envDef.name}`;
  const text = (sel) => page.textContent(sel).then((t) => t.replace(/\s+/g, " ").trim());
  const waitImport = async () => {
    await page.waitForFunction(
      () => document.getElementById("import-progress").hidden && (document.getElementById("import-summary").textContent.includes("导入完成") || !document.getElementById("error-banner").hidden),
      null,
      { timeout: 300000 }
    );
    const err = await page.$eval("#error-banner", (e) => (e.hidden ? "" : e.textContent));
    assert.equal(err, "", err);
    return text("#import-summary");
  };
  const clickImport = async (sel) => {
    await page.evaluate(() => document.getElementById("import-summary").replaceChildren());
    await page.click(sel);
  };
  const search = async (q, mode = "hybrid") => {
    await page.selectOption("#mode", mode);
    await page.fill("#q", q);
    await page.evaluate(() => (document.getElementById("results").innerHTML = ""));
    await page.click("#search-btn");
    await page.waitForSelector("#results li", { timeout: 30000 });
    await page.waitForFunction(() => !document.getElementById("timing").hidden);
    return {
      titles: await page.$$eval("#results .doc-title", (els) => els.map((e) => e.textContent)),
      keys: await page.$$eval("#results .meta", (els) => els.map((e) => e.textContent.split(" · ")[0])),
      timing: await text("#timing"),
    };
  };

  try {
    await page.goto(BASE);
    await page.waitForFunction(() => /\b(ok|warn|err)\b/.test(document.getElementById("backend-badge").className) && document.getElementById("search-btn").textContent === "检索", null, { timeout: 120000 });
    const badge = await text("#backend-badge");
    const banner = await page.$eval("#fallback-banner", (e) => (e.hidden ? "" : e.textContent.trim()));
    const detail = (sel) => page.$eval(sel, (e) => e.title);
    step("backend selected", {
      badge,
      adapter: await detail("#backend-badge"),
      banner,
      model: await text("#model-badge"),
      modelLoad: await detail("#model-badge"),
      db: await text("#db-badge"),
      userAgent: await page.evaluate(() => navigator.userAgent),
    });
    assert.ok(badge.includes(envDef.expect), `expected ${envDef.expect} in "${badge}"`);
    if (envDef.expect === "WASM") assert.ok(banner.includes("降级"), "fallback banner must explain the downgrade");
    else assert.equal(banner, "");

    // fresh KBs for this run: `kb` is the one under test, `kbOther` only ever holds the demo documents
    const freshKb = async (name) => {
      if (await page.$(`#kb-select option[value="${name}"]`)) {
        await page.selectOption("#kb-select", name);
        await page.waitForFunction(() => document.getElementById("kb-stats").textContent.length > 0);
        await page.click("#kb-delete");
        await page.waitForFunction((n) => !document.querySelector(`#kb-select option[value="${n}"]`), name);
      }
      await page.fill("#kb-new-name", name);
      await page.click("#kb-create-form button");
      await page.waitForFunction((n) => document.getElementById("kb-select").value === n, name);
    };
    const kbOther = `${kb}_other`;
    await freshKb(kbOther);
    await clickImport('[data-sample="demo"]');
    step("other kb import", { summary: await waitImport() });
    await freshKb(kb);
    step("kb created", { stats: await text("#kb-stats") });

    await clickImport('[data-sample="demo"]');
    const s1 = await waitImport();
    step("demo import", { summary: s1 });
    assert.match(s1, /9 \/ 0 \/ 0/);
    assert.match(s1, /已可检索/);

    const r1 = await search("什么是混合检索？");
    step("search zh", r1);
    assert.equal(r1.titles[0], "混合检索与 RRF 融合");
    await shot("1-search");
    const r2 = await search("How does HNSW trade recall for latency?");
    step("search en", r2);
    assert.equal(r2.titles[0], "HNSW vector index");
    const r3 = await search("断桥 雷峰塔", "fulltext");
    step("search fulltext", r3);
    assert.equal(r3.titles[0], "杭州西湖");
    // weighted-sum fusion: seekdb returns per-route scores instead of ranks
    await page.selectOption("#fusion", "weighted");
    const rw = await search("什么是混合检索？");
    rw.chips = await page.$$eval("#results li:first-child .chip", (els) => els.map((e) => e.textContent));
    step("search weighted", rw);
    assert.ok(rw.titles.slice(0, 3).includes("混合检索与 RRF 融合"), rw.titles.join(" | "));
    assert.ok(rw.chips.some((c) => /^(全文|向量) \d/.test(c)), rw.chips.join(" | "));
    await page.selectOption("#fusion", "rrf");

    // incremental: a pasted document is searchable right after its import commits
    await page.click(".paste summary");
    await page.fill("#paste-title", "端侧增量测试");
    await page.fill("#paste-text", "增量导入验证：这篇关于“量子咖啡烘焙机”的说明是刚刚粘贴的新文档，提交后应立即可以被检索到。");
    await clickImport("#paste-import");
    const s2 = await waitImport();
    step("paste import", { summary: s2 });
    const r4 = await search("量子咖啡烘焙机");
    step("search new doc", r4);
    assert.equal(r4.titles[0], "端侧增量测试");

    // unchanged re-import skips all embedding work
    await clickImport('[data-sample="demo"]');
    const s3 = await waitImport();
    step("demo re-import", { summary: s3 });
    assert.match(s3, /0 \/ 0 \/ 9/);

    // switching KBs keeps results consistent with the selected KB: the pasted document lives only in `kb`
    await page.selectOption("#kb-select", kbOther);
    await page.waitForFunction(() => document.getElementById("results").children.length === 0);
    const rOther = await search("量子咖啡烘焙机");
    step("other kb search", { kb: kbOther, titles: rOther.titles.slice(0, 3), kbVersion: rOther.timing.match(/v\d+/)?.[0] });
    assert.ok(rOther.titles.length > 0, "the other KB should return its own documents");
    assert.ok(!rOther.titles.includes("端侧增量测试"), "a document of another KB leaked into results");
    await page.selectOption("#kb-select", kb);
    await page.waitForSelector('#doc-list li:has-text("端侧增量测试") button');

    // delete the pasted document: it must disappear from results immediately
    const delBtn = await page.$('#doc-list li:has-text("端侧增量测试") button');
    await delBtn.click();
    await page.waitForFunction(() => document.getElementById("import-summary").textContent.includes("已删除"));
    const r5 = await search("量子咖啡烘焙机");
    step("search after delete", { titles: r5.titles.slice(0, 3) });
    assert.ok(!r5.titles.includes("端侧增量测试"));
    step("kb stats", { stats: await text("#kb-stats"), history: await text("#history") });
    await shot("2-final");
    assert.deepEqual(errors, []);
    step("PASS");
    // a passing run leaves no knowledge bases behind (a failing one keeps them for inspection)
    for (const name of [kb, kbOther]) await fetch(`${BASE}/api/kbs/${name}`, { method: "DELETE" });
    return { env: envDef.name, ok: true, log };
  } catch (e) {
    await shot("error").catch(() => {});
    step("FAIL", { error: e.message });
    return { env: envDef.name, ok: false, log, error: e.message };
  } finally {
    await browser.close();
  }
}

const results = [];
for (const e of ENVS) if (!only || only === e.name) results.push(await run(e));
fs.writeFileSync(path.join(outDir, "e2e-log.json"), JSON.stringify({ at: new Date().toISOString(), results }, null, 2));
const failed = results.filter((r) => !r.ok).length;
console.log(failed ? `${failed} environment(s) FAILED` : "all environments passed");
process.exit(failed ? 1 : 0);
