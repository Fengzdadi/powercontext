// Turns the raw benchmark JSON in bench/results/ into Markdown tables.
//   node bench/report.mjs [--stamp final]   -> bench/results/<stamp>__report.md (also printed)
// Inputs: <stamp>__*.json written by bench.html (via run-bench.mjs), <stamp>__runs-*.json (runner log),
// <stamp>__db.json (db-bench.mjs), model-size.json, quantize.json, e2e/e2e-log.json.
import fs from "node:fs";
import path from "node:path";
import { ROOT } from "../server/config.mjs";

const args = process.argv.slice(2);
const stamp = args.includes("--stamp") ? args[args.indexOf("--stamp") + 1] : "final";
const dir = path.join(ROOT, "bench", "results");
const read = (f) => {
  const p = path.join(dir, f);
  return fs.existsSync(p) ? JSON.parse(fs.readFileSync(p, "utf8")) : null;
};
const R = (name) => read(`${stamp}__${name}.json`);
const all = fs.readdirSync(dir).filter((f) => f.startsWith(`${stamp}__`) && f.endsWith(".json"));

const median = (xs) => {
  const s = xs.filter((x) => x != null && !Number.isNaN(x)).sort((a, b) => a - b);
  if (!s.length) return null;
  const m = Math.floor(s.length / 2);
  return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
};
const fmtMs = (x) => (x == null ? "–" : x >= 1000 ? `${(x / 1000).toFixed(2)} s` : x >= 100 ? `${x.toFixed(0)} ms` : `${x.toFixed(1)} ms`);
const fmtMB = (b) => (b == null ? "–" : `${(b / 1e6).toFixed(1)} MB`);
const f3 = (x) => (x == null ? "–" : x.toFixed(3));
const f1 = (x) => (x == null ? "–" : x.toFixed(1));
const signed = (x, d = 3) => (x == null ? "–" : `${x >= 0 ? "+" : ""}${x.toFixed(d)}`);
const table = (head, rows) => [`| ${head.join(" | ")} |`, `|${head.map(() => "---").join("|")}|`, ...rows.map((r) => `| ${r.join(" | ")} |`)].join("\n");
const out = [];
// one section: blocks (heading, paragraph, table) separated by blank lines
const P = (...blocks) => out.push(blocks.filter((b) => b !== "").join("\n\n"), "");

// ------------------------------------------------------------------ environment
const runLogs = all.filter((f) => f.startsWith(`${stamp}__runs-`)).map((f) => read(f));
const runs = runLogs.flatMap((l) => l.runs);
const host = runLogs[0]?.host;
const anyResult = all.map((f) => read(f)).find((r) => r?.env?.userAgent && r?.init);
const gpuRun = all.map((f) => read(f)).find((r) => r?.init?.backend === "webgpu");
const db = R("db");
const chrome = [...new Set(runs.map((r) => r.chrome).filter(Boolean))].join(", ");
const loads = runs.flatMap((r) => [...(r.loadavgBefore ?? []).slice(0, 1), ...(r.loadavgAfter ?? []).slice(0, 1)]);
P(`# 端侧推理与 seekdb 检索测量报告（${stamp}）`);
P(
  "## 测试环境",
  table(
    ["项目", "值"],
    [
      ["设备", host ? `${host.cpu}，${host.cores} 核，${host.memGB} GB 内存` : "–"],
      ["系统", host?.os ?? "–"],
      ["浏览器", chrome ? `Google Chrome ${chrome}（Playwright 驱动，headless）` : anyResult?.env?.brands?.join(", ") ?? "–"],
      ["WebGPU 适配器", gpuRun ? `${gpuRun.init.webgpu?.adapter?.vendor} / ${gpuRun.init.webgpu?.adapter?.architecture}，shader-f16: ${gpuRun.init.webgpu?.shaderF16}` : "–"],
      ["无 WebGPU 环境", "Chrome `--disable-gpu`：`navigator.gpu.requestAdapter()` 返回 null"],
      ["WASM", `ONNX Runtime Web（asyncify 构建），crossOriginIsolated=${anyResult?.env?.crossOriginIsolated}，多线程 SIMD`],
      ["模型", `${anyResult?.init?.model?.repo ?? "Xenova/multilingual-e5-small"}@${anyResult?.init?.model?.revision ?? ""}（384 维）`],
      ["分块与批处理", "按句子打包 ≤300 token；文档向量化批大小 16，按长度排序，与写入流水线并行；查询逐条向量化"],
      ["seekdb", db ? `${db.env.seekdb}；容器 ${db.env.seekdbContainer ?? ""}` : anyResult?.health?.seekdb ?? "–"],
      ["seekdb 索引与检索参数", "HNSW cosine m=16 / ef_construction=200 / ef_search=100（SYNC_MODE=ASYNC）；FULLTEXT IK smart；SEARCH：knn k=50，RRF rank_window_size=50 / rank_constant=60，size=10"],
      ["Node.js", db?.env?.node ?? "–"],
      ["机器负载", loads.length ? `测量期间 1 分钟 load average ${Math.min(...loads).toFixed(0)}–${Math.max(...loads).toFixed(0)}（共享机器，其他任务同时运行）` : "–"],
    ]
  )
);

// ------------------------------------------------------------------ main table (spec 3.2)
const sizes = read("model-size.json");
const sizeOf = (source, dtype) => sizes?.rows.find((r) => r.source === source && r.dtype === dtype);
const QUALITY = [
  ["量化前基线 FP32 + WebGPU", "quality-webgpu-fp32", "huggingface", "fp32"],
  ["量化前基线 FP32 + WASM", "quality-wasm-fp32", "huggingface", "fp32"],
  ["**FP16 + WebGPU**（GPU 默认）", "quality-webgpu-fp16", "huggingface", "fp16"],
  ["INT8 + WebGPU", "quality-webgpu-int8", "huggingface", "int8"],
  ["**INT8 + WASM**（降级默认）", "quality-wasm-int8", "huggingface", "int8"],
  ["FP16 + WASM", "quality-wasm-fp16", "huggingface", "fp16"],
  ["FP16 + WebGPU（本地脚本量化）", "quality-webgpu-fp16-local", "local", "fp16"],
  ["INT8 + WASM（本地脚本量化）", "quality-wasm-int8-local", "local", "int8"],
];
const q = Object.fromEntries(QUALITY.map(([, n]) => [n, R(n)]).filter(([, v]) => v?.ok));
const baseFor = (r) => (r.init.backend === "webgpu" ? q["quality-webgpu-fp32"] : q["quality-wasm-fp32"]) ?? q["quality-wasm-fp32"];
const mainRows = [];
for (const [label, name, source, dtype] of QUALITY) {
  const r = q[name];
  if (!r) continue;
  const s = sizeOf(source, dtype);
  const hy = r.quality.hybrid.all;
  const vec = r.quality.vector.all;
  const base = baseFor(r);
  const lw = r.latency.warm;
  mainRows.push([
    label,
    s ? `${fmtMB(s.bytes)}（×${s.ratio.toFixed(2)}）；总下载 ${fmtMB(s.downloadBytes)}（×${s.downloadRatio.toFixed(2)}）` : fmtMB(r.init.bytes),
    `${f1(r.import.throughput.chunksPerSec)} 块/s · ${(r.import.throughput.tokensPerSec ?? 0).toFixed(0)} token/s`,
    `${fmtMs(lw.seekdbMs.median)}（p90 ${fmtMs(lw.seekdbMs.p90)}）`,
    `${fmtMs(lw.e2eMs.median)}（p90 ${fmtMs(lw.e2eMs.p90)}；首轮 ${fmtMs(r.latency.pass0.e2eMs.median)}）`,
    `${f3(hy.recall)} / ${f3(hy.ndcg)}` + (base && base !== r ? `（Δ ${signed(hy.recall - base.quality.hybrid.all.recall)} / ${signed(hy.ndcg - base.quality.hybrid.all.ndcg)}）` : ""),
    `${f3(vec.recall)} / ${f3(vec.ndcg)}`,
  ]);
}
P(
  "## 主表：量化前后 × 推理后端（规范 3.2）",
  "评测集：MIRACL dev 抽样 90 条查询（60 中文 + 30 英文），语料为这些查询的全部标注段落 908 段（含 706 段困难负例）；指标在文档级去重后计算，K=10。" +
    "向量化吞吐 = 导入全部 908 段的端侧向量化（批大小 16、按长度排序、与写入流水线并行）；延迟为每个配置 90 条查询 × 5 轮，除首轮外各轮的中位数（混合检索，查询缓存关闭）。Δ 为相对同后端 FP32 基线的变化。",
  table(["配置", "模型体积（压缩比）", "向量化吞吐", "seekdb 检索延迟", "端到端查询延迟", "混合检索 Recall@10 / nDCG@10", "纯向量 Recall@10 / nDCG@10"], mainRows)
);

const stageRows = [];
for (const [label, name] of QUALITY) {
  const r = q[name];
  if (!r) continue;
  const it = r.import.timings;
  const lw = r.latency.warm;
  stageRows.push([
    label.replace(/\*\*/g, ""),
    `${fmtMs(r.init.timings.totalMs)}${r.init.cacheHit ? "（缓存）" : ""}`,
    `${fmtMs(it.embedMs)}（${r.import.chunks} 块）`,
    `${fmtMs(it.writeTailMs)}（${it.writeRequests} 次请求）`,
    `${fmtMs(it.commitMs)}（${r.import.commitTimings?.refreshMode} ${fmtMs(r.import.commitTimings?.refreshMs)}）`,
    fmtMs(lw.queryEmbedMs.median),
    fmtMs(lw.seekdbMs.median),
    fmtMs(lw.networkMs.median),
    fmtMs(lw.renderMs.median),
    fmtMs(lw.e2eMs.median),
    fmtMs(r.latency.firstQueryAfterImport?.seekdbMs),
  ]);
}
if (stageRows.length) {
  P(
    "## 分阶段计时（与主表同一次运行）",
    "写入列为向量化结束后仍在等待的写入时间（其余写入与向量化重叠，被掩盖）；串行写入的实际耗时见“增量导入场景”。提交包含替换旧分块、登记文档和等待新分块可见。查询各列为热中位数；最后一列为导入完成后第一次混合检索在 seekdb 内的耗时（索引刚建好、缓存冷）。",
    table(["配置", "模型加载", "文档向量化", "写入 seekdb", "提交与索引刷新", "查询向量化", "seekdb 检索", "服务与网络", "渲染", "端到端", "导入后首次检索 seekdb"], stageRows)
  );
}

// ------------------------------------------------------------------ before/after summary
const optRows = optimisationRows();
if (optRows.length) {
  P(
    "## 优化前后对比（汇总）",
    "每行只改变一个条件，其余同默认配置；数值取自本报告各节的同一批原始数据（中位数）。变化 = (后 − 前) / 前。",
    table(["优化", "比较范围", "前", "后", "变化", "数据"], optRows)
  );
}

// ------------------------------------------------------------------ size & fidelity
const qz = read("quantize.json");
if (sizes) {
  P(
    "## 模型体积",
    table(
      ["来源", "精度", "ONNX 文件", "字节", "压缩比", "体积减少", "总下载（含分词器与配置）", "总下载压缩比"],
      sizes.rows.map((r) => [r.source === "huggingface" ? "Xenova 预构建" : "本地脚本", r.dtype.toUpperCase(), `\`${r.file}\``, r.bytes.toLocaleString("en-US"), `×${r.ratio.toFixed(2)}`, `${r.reductionPct.toFixed(1)}%`, r.downloadBytes.toLocaleString("en-US"), `×${r.downloadRatio.toFixed(2)}`])
    ),
    `浏览器实际下载 ONNX 文件加上 ${sizes.sharedFiles.map((f) => `\`${f}\``).join("、")}（共 ${sizes.sharedBytes.toLocaleString("en-US")} 字节，各精度相同），与加载测量中记录的下载字节数一致。`
  );
}
const cosRows = [];
const vecOf = (r) => r?.vectors && [...r.vectors.queries, ...r.vectors.passages];
const cos = (a, b) => a.reduce((s, x, i) => s + x * b[i], 0);
const ref = vecOf(q["quality-wasm-fp32"]) ?? vecOf(q["quality-webgpu-fp32"]);
for (const [label, name] of QUALITY) {
  const v = vecOf(q[name]);
  if (!v || !ref) continue;
  const cs = v.map((x, i) => cos(x, ref[i]));
  cosRows.push([label.replace(/\*\*/g, ""), (cs.reduce((a, b) => a + b, 0) / cs.length).toFixed(5), Math.min(...cs).toFixed(5)]);
}
if (cosRows.length) {
  P(
    "## 输出保真度（浏览器内实测）",
    "每个配置对同一组输入（90 条查询 + 128 段文本）计算向量，与 WASM FP32 的向量逐条求余弦相似度。",
    table(["配置", "平均余弦", "最小余弦"], cosRows)
  );
}
if (qz) {
  P(
    "## 量化脚本与 CPU 侧保真度（scripts/quantize.py，ONNX Runtime CPU）",
    `INT8：\`${qz.recipe.int8}\``,
    `FP16：\`${qz.recipe.fp16}\``,
    table(
      ["变体", "字节", "压缩比", "与 FP32 平均余弦", "最小余弦"],
      Object.entries(qz.sizes).map(([k, s]) => [k, s.bytes.toLocaleString("en-US"), `×${s.ratio.toFixed(2)}`, qz.fidelity[k]?.cos_mean?.toFixed(5) ?? qz.fidelity[k]?.error ?? "–", qz.fidelity[k]?.cos_min?.toFixed(5) ?? "–"])
    ),
    Object.entries(qz.fidelity)
      .filter(([k]) => k.includes(" vs "))
      .map(([k, v]) => `- ${k}：平均余弦 ${v.cos_mean}，最小 ${v.cos_min}`)
      .join("\n")
  );
}

// ------------------------------------------------------------------ quality detail
const qRows = [];
for (const [label, name] of QUALITY) {
  const r = q[name];
  if (!r) continue;
  for (const mode of ["vector", "hybrid", "fulltext"]) {
    const m = r.quality[mode];
    qRows.push([label.replace(/\*\*/g, ""), { vector: "纯向量", hybrid: "混合（RRF）", fulltext: "纯全文" }[mode], f3(m.all.recall), f3(m.all.ndcg), f3(m.all.mrr), `${f3(m.zh.recall)} / ${f3(m.zh.ndcg)}`, `${f3(m.en.recall)} / ${f3(m.en.ndcg)}`]);
  }
}
if (qRows.length) P("## 检索质量明细（K=10）", table(["配置", "检索方式", "Recall@10", "nDCG@10", "MRR@10", "中文 R/nDCG", "英文 R/nDCG"], qRows));

// ------------------------------------------------------------------ model load
const loadCfgs = [
  ["WebGPU · FP16", "load-cold-webgpu-fp16"],
  ["WebGPU · FP32", "load-cold-webgpu-fp32"],
  ["WASM · INT8", "load-cold-wasm-int8"],
];
const loadRows = [];
for (const [label, prefix] of loadCfgs) {
  for (const phase of ["cold", "warm"]) {
    const rs = [1, 2, 3].map((i) => R(`${prefix}-${i}-${phase}`)).filter((r) => r?.ok);
    if (!rs.length) continue;
    const t = (k) => median(rs.map((r) => r.init.timings[k]));
    loadRows.push([
      label,
      phase === "cold" ? "首次（空缓存，从本地服务下载）" : "再次（Cache Storage 命中）",
      rs.length,
      fmtMs(t("modelFetchMs")),
      fmtMs(t("sessionCreateMs")),
      fmtMs(t("firstInferMs")),
      fmtMs(t("secondInferMs")),
      fmtMs(t("totalMs")),
      fmtMs(median(rs.map((r) => r.firstQueryEmbedMs))),
    ]);
  }
}
if (loadRows.length) {
  P(
    "## 模型加载：首次 vs 再次（3 次中位数）",
    "首次 = 全新浏览器配置目录；再次 = 同一配置目录刷新页面。模型文件由本机服务（localhost）提供，测到的首次加载不代表经公网下载的时间；经网络下载时，下载时间与“浏览器总下载”大致成正比。首次推理包含 WebGPU 管线编译 / WASM 内核初始化，加载阶段用预热把它挪出用户的第一次查询。",
    table(["后端 · 精度", "场景", "次数", "下载/读取", "创建会话", "首次推理（预热）", "第二次推理", "加载总计", "随后第一条查询向量化"], loadRows)
  );
}

// ------------------------------------------------------------------ batching
const batchRows = [];
for (const [label, name] of [
  ["WebGPU · FP16", "batch-webgpu-fp16"],
  ["WASM · INT8 · 多线程", "batch-wasm-int8"],
  ["WASM · INT8 · 单线程", "batch-wasm-int8-1thread"],
]) {
  const r = R(name);
  if (!r?.ok) continue;
  for (const b of r.batch) {
    batchRows.push([label + (r.init.threads ? `（${r.init.threads} 线程）` : ""), b.batchSize, b.sortByLength ? "是" : "否", b.bucket == null ? "关（默认）" : b.bucket ? "开" : "关", b.texts, f1(b.chunksPerSec), b.tokensPerSec.toFixed(0), b.padRatio.toFixed(2), fmtMs(b.wallMs)]);
  }
}
if (batchRows.length) P("## 批量向量化：批大小 / 按长度排序 / 形状分桶（3 次中位数）", table(["后端", "批大小", "按长度排序", "形状分桶", "文本数", "块/s", "token/s", "填充率", "总耗时"], batchRows));

// ------------------------------------------------------------------ import scenario
for (const name of ["import-webgpu-fp16", "import-webgpu-fp16-sequential"]) {
  const r = R(name);
  if (!r?.ok) continue;
  P(
    `## 增量导入场景（${name.endsWith("sequential") ? "WebGPU · FP16，向量化与写入串行" : "WebGPU · FP16，向量化与写入流水线并行"}）`,
    table(
      ["步骤", "新增/变更/跳过", "分块", "向量化", "写入尾部（未被掩盖）", "写入 seekdb 累计", "提交（替换+登记+刷新）", "刷新方式与耗时", "总耗时", "版本", "新文档立即可检索"],
      r.steps.map((s) =>
        s.counts
          ? [s.name, `${s.counts.new}/${s.counts.changed}/${s.counts.unchanged}`, s.chunks, fmtMs(s.timings.embedMs), fmtMs(s.timings.writeTailMs), fmtMs(s.timings.writeDbMs), fmtMs(s.timings.commitMs), `${s.commit?.refreshMode ?? "–"} ${fmtMs(s.commit?.refreshMs)}`, fmtMs(s.timings.totalMs), `v${s.version}`, s.newDocVisible == null ? "–" : s.newDocVisible ? "是" : "否"]
          : [s.name, "–", "–", "–", "–", "–", "–", "–", "–", `v${s.version}`, s.deletedStillReturned ? "删除后仍返回（错误）" : "删除后不再返回"]
      )
    )
  );
}

// pipelined vs sequential over every repeat (import-repeat plan): medians per step
const importRuns = (base) => [base, `${base}-2`, `${base}-3`].map((n) => R(n)).filter((r) => r?.ok);
const pipeRuns = importRuns("import-webgpu-fp16");
const seqRuns = importRuns("import-webgpu-fp16-sequential");
if (pipeRuns.length && seqRuns.length) {
  const stepMedian = (runs, i, k) => median(runs.map((r) => r.steps[i]?.timings?.[k]));
  const rows = pipeRuns[0].steps
    .map((s, i) => [s, i])
    .filter(([s]) => s.counts)
    .flatMap(([s, i]) => {
      const out = [[s.name, "总耗时", fmtMs(stepMedian(pipeRuns, i, "totalMs")), fmtMs(stepMedian(seqRuns, i, "totalMs"))]];
      if (s.chunks > 100) out.push([s.name, "其中 向量化 + 写入", fmtMs(stepMedian(pipeRuns, i, "embedAndWriteMs")), fmtMs(stepMedian(seqRuns, i, "embedAndWriteMs"))]);
      return out;
    });
  P(
    `## 向量化与写入：流水线 vs 串行（WebGPU · FP16，按 ABBA 顺序交替运行，中位数：流水线 ${pipeRuns.length} 次、串行 ${seqRuns.length} 次）`,
    table(["步骤", "计时", "流水线并行", "串行"], rows)
  );
}

// ------------------------------------------------------------------ query path
for (const [label, name] of [
  ["WebGPU · FP16", "query-webgpu-fp16"],
  ["WASM · INT8", "query-wasm-int8"],
]) {
  const r = R(name);
  if (!r?.ok) continue;
  P(
    `## 查询链路（${label}，bench_query 知识库，${r.config.repeats} 轮 × 90 条，去掉首轮后的中位数）`,
    table(
      ["变体", "查询向量化", "seekdb 检索", "端到端（不含渲染）"],
      r.variants.map((v) => [v.name, fmtMs(v.queryEmbedMs.median), `${fmtMs(v.seekdbMs.median)}（p90 ${fmtMs(v.seekdbMs.p90)}）`, `${fmtMs(v.e2eMs.median)}（p90 ${fmtMs(v.e2eMs.p90)}）`])
    ),
    table(["查询向量化形状分桶", "首轮中位数", "热中位数"], r.bucket.map((b) => [b.bucket ? "开" : "关", fmtMs(b.firstPassMs.median), fmtMs(b.queryEmbedMs.median)])),
    r.fusion
      ? table(
          ["seekdb 内融合方式", "Recall@10", "nDCG@10", "MRR@10", "中文 R/nDCG", "英文 R/nDCG"],
          r.fusion.map((f) => [f.fusion === "rrf" ? "RRF（rank_constant=60，窗口 50）" : "加权求和（向量 0.7 / 全文 0.3，原始得分）", f3(f.all.recall), f3(f.all.ndcg), f3(f.all.mrr), `${f3(f.zh.recall)} / ${f3(f.zh.ndcg)}`, `${f3(f.en.recall)} / ${f3(f.en.ndcg)}`])
        )
      : ""
  );
}

// ------------------------------------------------------------------ seekdb micro-benchmarks
if (db) {
  P(
    `## seekdb 侧（bench/db-bench.mjs，知识库 ${db.kb}：${db.source.chunks} 块，${db.source.queries} 条查询 × ${db.search.latencyMs[Object.keys(db.search.latencyMs)[0]].n / db.source.queries} 轮）`,
    table(
      ["检索调用", "中位数", "p90", "平均响应 JSON"],
      Object.entries(db.search.latencyMs).map(([k, v]) => [k, fmtMs(v.median), fmtMs(v.p90), `${(db.search.avgResponseBytes[k] / 1024).toFixed(1)} KB`])
    ),
    `SDK 与单次 SEARCH 的前 10 结果重合率：${db.search.sdkVsSearchTop10Overlap}`,
    "",
    table(["写入方式", "行数", "耗时", "行/秒"], Object.entries(db.writes).map(([k, v]) => [`collection.add，${k}`, v.rows, fmtMs(v.ms), f1(v.rowsPerSec)])),
    "",
    table(
      ["64 行写入", "中位数"],
      [
        ["collection.add()（一条多行 INSERT）", fmtMs(db.upsertVsAdd.addMs.median)],
        ["collection.upsert()（逐行查询后更新/插入）", fmtMs(db.upsertVsAdd.upsertMs.median)],
      ]
    ),
    "",
    table(
      ["新写入的可见性（每次 64 行）", "结果"],
      [
        ["写入后立即被向量检索返回", db.visibility.vectorVisibleRightAfterInsert],
        ["探测等待异步索引追上（中位数 / p90）", `${fmtMs(db.visibility.probeMs.median)} / ${fmtMs(db.visibility.probeMs.p90)}（${db.visibility.probeRounds.median} 轮探测）`],
        ["显式 CALL dbms_index_manager.refresh()（中位数 / p90）", `${fmtMs(db.visibility.explicitRefreshMs.median)} / ${fmtMs(db.visibility.explicitRefreshMs.p90)}`],
        ["全文索引写入后立即可检索", db.visibility.fulltextVisibleRightAfterInsert],
      ]
    ),
    "",
    table(
      [`向量索引 SYNC_MODE（${Object.values(db.syncMode)[0].rounds} 轮交替，中位数）`, "写入 512 行（64 行/INSERT）", "行/秒", "写入到最后一行可被向量检索", "最后一行写入后立即可检索"],
      Object.entries(db.syncMode).map(([k, v]) => [k === "ASYNC" ? "ASYNC（seekdb-js 默认，应用使用）" : k, fmtMs(v.insertMs.median), f1(v.rowsPerSec), fmtMs(v.untilVisibleMs.median), v.lastRowVisibleRightAfterInsert])
    )
  );
}

// ------------------------------------------------------------------ fallback & e2e
const fb = ["fallback-auto-gpu", "fallback-auto-nogpu"].map((n) => [n, R(n)]).filter(([, r]) => r);
if (fb.length) {
  P(
    "## 后端自动选择（backend=auto, dtype=auto）",
    table(
      ["环境", "选中后端", "精度", "降级原因", "加载总计"],
      fb.map(([n, r]) => [n.endsWith("nogpu") ? "Chrome --disable-gpu" : "Chrome（GPU 可用）", r.init?.backend, r.init?.dtype, r.init?.fallbackReason ?? "–", fmtMs(r.init?.timings?.totalMs)])
    )
  );
}
const e2e = read("e2e/e2e-log.json");
if (e2e) {
  P(
    "## 界面端到端测试（bench/e2e.mjs）",
    table(
      ["环境", "结果", "后端标识"],
      e2e.results.map((r) => [r.env === "gpu" ? "Chrome（GPU 可用）" : "Chrome --disable-gpu", r.ok ? "通过" : `失败：${r.error}`, r.log.find((s) => s.step === "backend selected")?.badge ?? "–"])
    ),
    `运行时间：${e2e.at}`
  );
}

const md = out.join("\n");
const file = path.join(dir, `${stamp}__report.md`);
fs.writeFileSync(file, md);
console.log(md);
console.error(`wrote ${path.relative(ROOT, file)}`);

// Rows for the before/after summary: [optimisation, scope, before, after, change, source].
function optimisationRows() {
  const rows = [];
  const pct = (a, b) => (a == null || b == null ? "–" : `${b >= a ? "+" : "−"}${Math.abs(((b - a) / a) * 100).toFixed(0)}%`);
  const pts = (a, b) => (a == null || b == null ? "–" : `${b >= a ? "+" : "−"}${Math.abs(b - a).toFixed(4)}`);
  const add = (name, scope, a, b, fmt, src, change = pct) => {
    if (a != null && b != null) rows.push([name, scope, fmt(a), fmt(b), change(a, b), src]);
  };
  const cps = (x) => `${f1(x)} 块/s`;
  const s = (x) => fmtMs(x);
  const mb = (x) => fmtMB(x);
  const n4 = (x) => x.toFixed(4);
  const qr = (name) => q[name];
  const tput = (name) => qr(name)?.import.throughput.chunksPerSec;
  const warm = (name, k) => qr(name)?.latency.warm[k].median;
  const vecNdcg = (name) => qr(name)?.quality.vector.all.ndcg;
  const loadMed = (prefix, phase, k) => median([1, 2, 3].map((i) => R(`${prefix}-${i}-${phase}`)).filter((r) => r?.ok).map((r) => r.init.timings[k]));
  const batchRow = (name, pred) => (R(name)?.ok ? R(name).batch.find(pred) : undefined);
  const isDefault = (b) => b.batchSize === 16 && b.sortByLength && b.bucket == null;

  // precision
  add("FP16（WebGPU）", "导入 908 段的端侧向量化", tput("quality-webgpu-fp32"), tput("quality-webgpu-fp16"), cps, "主表");
  add("FP16（WebGPU）", "浏览器总下载", sizeOf("huggingface", "fp32")?.downloadBytes, sizeOf("huggingface", "fp16")?.downloadBytes, mb, "模型体积");
  // stage timings rather than end-to-end: seekdb latency is the same work in every row and only adds load noise
  add("FP16（WebGPU）", "查询向量化（热）", warm("quality-webgpu-fp32", "queryEmbedMs"), warm("quality-webgpu-fp16", "queryEmbedMs"), s, "分阶段计时");
  add("FP16（WebGPU）", "纯向量 nDCG@10", vecNdcg("quality-webgpu-fp32"), vecNdcg("quality-webgpu-fp16"), n4, "检索质量", pts);
  add("INT8（WASM）", "导入 908 段的端侧向量化", tput("quality-wasm-fp32"), tput("quality-wasm-int8"), cps, "主表");
  add("INT8（WASM）", "浏览器总下载", sizeOf("huggingface", "fp32")?.downloadBytes, sizeOf("huggingface", "int8")?.downloadBytes, mb, "模型体积");
  add("INT8（WASM）", "查询向量化（热）", warm("quality-wasm-fp32", "queryEmbedMs"), warm("quality-wasm-int8", "queryEmbedMs"), s, "分阶段计时");
  add("INT8（WASM）", "纯向量 nDCG@10", vecNdcg("quality-wasm-fp32"), vecNdcg("quality-wasm-int8"), n4, "检索质量", pts);

  // batching
  const one = batchRow("batch-wasm-int8-1thread", isDefault);
  const multi = batchRow("batch-wasm-int8", isDefault);
  add("WASM 多线程（跨源隔离）", `INT8 批量向量化，1 → ${R("batch-wasm-int8")?.init?.threads ?? 8} 线程`, one?.chunksPerSec, multi?.chunksPerSec, cps, "批量向量化");
  for (const [label, name] of [["WebGPU · FP16", "batch-webgpu-fp16"], ["WASM · INT8", "batch-wasm-int8"]]) {
    add("批处理", `${label}，批大小 1 → 16（排序）`, batchRow(name, (b) => b.batchSize === 1)?.chunksPerSec, batchRow(name, isDefault)?.chunksPerSec, cps, "批量向量化");
    add("按长度排序后分批", `${label}，批大小 16`, batchRow(name, (b) => b.batchSize === 16 && !b.sortByLength)?.chunksPerSec, batchRow(name, isDefault)?.chunksPerSec, cps, "批量向量化");
  }
  add("形状分桶（未采用）", "WebGPU · FP16，批大小 16，关 → 开", batchRow("batch-webgpu-fp16", (b) => b.bucket === false)?.chunksPerSec, batchRow("batch-webgpu-fp16", (b) => b.bucket === true)?.chunksPerSec, cps, "批量向量化");

  // load
  for (const [label, prefix] of [["WebGPU · FP16", "load-cold-webgpu-fp16"], ["WASM · INT8", "load-cold-wasm-int8"]]) {
    add("加载阶段预热", `${label}，首次推理 → 预热后单次推理`, loadMed(prefix, "cold", "firstInferMs"), loadMed(prefix, "cold", "secondInferMs"), s, "模型加载");
    add("Cache Storage 缓存模型", `${label}，首次加载 → 再次加载`, loadMed(prefix, "cold", "totalMs"), loadMed(prefix, "warm", "totalMs"), s, "模型加载");
  }

  // import
  const imp = (base) => [base, `${base}-2`, `${base}-3`].map((n) => R(n)).filter((r) => r?.ok);
  const pipe = imp("import-webgpu-fp16");
  const seq = imp("import-webgpu-fp16-sequential");
  const fullEW = (runs) => median(runs.map((r) => r.steps.filter((x) => x.chunks > 100).reduce((t, x) => t + x.timings.embedAndWriteMs, 0)));
  const fullTotal = (runs) => median(runs.map((r) => r.steps.filter((x) => x.chunks > 100).reduce((t, x) => t + x.timings.totalMs, 0)));
  const reimport = (runs) => median(runs.map((r) => r.steps.find((x) => x.counts && x.counts.unchanged > 0 && !x.counts.new && !x.counts.changed)?.timings.totalMs));
  add("向量化与写入流水线", `WebGPU · FP16，908 篇的向量化 + 写入，串行 → 流水线（各 ${Math.min(pipe.length, seq.length)} 次）`, fullEW(seq), fullEW(pipe), s, "流水线 vs 串行");
  add("跳过未改动文档", "WebGPU · FP16，908 篇：首次导入 → 内容未变时重导", fullTotal(pipe), reimport(pipe), s, "增量导入场景");

  // query path
  for (const [label, name] of [["WebGPU · FP16", "query-webgpu-fp16"], ["WASM · INT8", "query-wasm-int8"]]) {
    const v = (n) => (R(name)?.ok ? R(name).variants.find((x) => x.name === n) : undefined);
    add("查询向量缓存", `${label}，重复查询的查询向量化`, v("SEARCH single call")?.queryEmbedMs.median, v("SEARCH + query cache")?.queryEmbedMs.median, s, "查询链路");
  }
  if (db) {
    const L = db.search.latencyMs;
    add("一次 SEARCH 调用", "seekdb 混合检索，SDK hybridSearch() → 单次 SEARCH", L["hybrid · SDK hybridSearch()"]?.median, L["hybrid · SEARCH · _source pruned"]?.median, s, "seekdb 侧");
    add("`_source` 只取所需列", "seekdb 混合检索延迟", L["hybrid · SEARCH · all columns"]?.median, L["hybrid · SEARCH · _source pruned"]?.median, s, "seekdb 侧");
    add("`_source` 只取所需列", "响应 JSON 大小", db.search.avgResponseBytes["hybrid · SEARCH · all columns"], db.search.avgResponseBytes["hybrid · SEARCH · _source pruned"], (x) => `${(x / 1024).toFixed(1)} KB`, "seekdb 侧");
    add("多行 INSERT", "collection.add，1 → 64 行/INSERT", db.writes["1 rows/INSERT"]?.rowsPerSec, db.writes["64 rows/INSERT"]?.rowsPerSec, (x) => `${f1(x)} 行/s`, "seekdb 侧");
    add("add 代替 upsert", "写入 64 行新数据", db.upsertVsAdd.upsertMs.median, db.upsertVsAdd.addMs.median, s, "seekdb 侧");
    add("探测等待代替显式刷新", "64 行写入后到可被向量检索", db.visibility.explicitRefreshMs.median, db.visibility.probeMs.median, s, "seekdb 侧");
    if (db.syncMode?.ASYNC?.untilVisibleMs) {
      add("向量索引 IMMEDIATE（未采用）", "写入 512 行到最后一行可检索，ASYNC → IMMEDIATE", db.syncMode.ASYNC.untilVisibleMs.median, db.syncMode.IMMEDIATE.untilVisibleMs.median, s, "seekdb 侧");
    }
  }
  return rows;
}
