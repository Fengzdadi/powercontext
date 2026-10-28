// App UI: knowledge-base management, imports, search. Embeddings come from the in-browser worker;
// storage and hybrid retrieval go to seekdb through the local server.
import { Embedder } from "./embedder.js";
import { api } from "./api.js";
import { importDocuments, runSearch } from "./pipeline.js";
import { parseFiles } from "./chunker.js";
import { MODEL } from "./model-config.js";

const $ = (id) => document.getElementById(id);
const LS_SETTINGS = "edgekb.settings.v1";
const LS_KB = "edgekb.kb";
const DEFAULT_KB = "demo";
const EXAMPLES = [
  "什么是混合检索？",
  "WebGPU 不可用时怎么办",
  "INT8 量化能把模型缩小多少",
  "阶跃星辰开源了哪些模型",
  "西湖十景有哪些",
  "How does HNSW trade recall for latency?",
  "pour over coffee ratio",
];

const readLs = (k, d) => {
  try {
    return JSON.parse(localStorage.getItem(k)) ?? d;
  } catch {
    return d;
  }
};
const urlParams = new URLSearchParams(location.search);
const settings = { backend: "auto", dtype: "auto", source: "hf", batchSize: 16, refresh: "probe", impl: "search", ...readLs(LS_SETTINGS, {}) };
for (const key of ["backend", "dtype", "source"]) if (urlParams.has(key)) settings[key] = urlParams.get(key);

const state = { kb: null, kbInfo: null, docs: [], busy: false, searchSeq: 0 };
const embedder = new Embedder();

const fmtMs = (x) => (x == null ? "–" : x >= 1000 ? `${(x / 1000).toFixed(2)} s` : `${x.toFixed(x < 10 ? 1 : 0)} ms`);
const fmtMB = (b) => `${(b / 1e6).toFixed(0)} MB`;
const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
const nextFrame = () => new Promise((r) => requestAnimationFrame(() => r()));

function setBadge(id, kind, text, title = "") {
  const el = $(id);
  el.className = `badge ${kind}`;
  el.textContent = text;
  el.title = title;
}

function showError(err) {
  const el = $("error-banner");
  if (!err) return (el.hidden = true);
  el.textContent = `出错了：${err.message ?? err}`;
  el.hidden = false;
}

// ------------------------------------------------------------------ model / backend

async function startModel() {
  setBadge("backend-badge", "pending", "推理后端：检测中…");
  setBadge("model-badge", "pending", "模型：加载中…");
  $("fallback-banner").hidden = true;
  const files = new Map();
  embedder.onEvent = (e) => {
    if (e.type === "progress" && e.total) {
      files.set(e.file, e);
      const loaded = [...files.values()].reduce((s, f) => s + f.loaded, 0);
      const total = [...files.values()].reduce((s, f) => s + f.total, 0);
      setBadge("model-badge", "pending", `模型：下载/读取 ${fmtMB(loaded)} / ${fmtMB(total)}`);
    } else if (e.type === "status" && e.phase === "loading") {
      setBadge("backend-badge", "pending", `推理后端：初始化 ${e.backend === "webgpu" ? "WebGPU" : "WASM"} · ${e.dtype.toUpperCase()}…`);
      if (e.fallbackReason) showFallback(e.fallbackReason);
    }
  };
  try {
    const info = await embedder.start({ backend: settings.backend, dtype: settings.dtype, source: settings.source });
    renderBackend(info);
  } catch (err) {
    setBadge("backend-badge", "err", "推理后端：初始化失败");
    setBadge("model-badge", "err", "模型：未加载");
    showError(err);
  }
  updateSearchEnabled();
}

function showFallback(reason) {
  const el = $("fallback-banner");
  el.innerHTML = `当前环境无法使用 WebGPU，已自动降级到 <b>WASM</b> 后端（${esc(reason)}）。导入、向量化与检索流程不受影响；批量向量化会比 GPU 慢。`;
  el.hidden = false;
}

function renderBackend(info) {
  const precision = info.dtype.toUpperCase();
  if (info.backend === "webgpu") {
    const a = info.webgpu?.adapter ?? {};
    setBadge("backend-badge", "ok", `推理后端：WebGPU · ${precision}`, `GPU: ${[a.vendor, a.architecture, a.description].filter(Boolean).join(" ")}; shader-f16: ${info.webgpu?.shaderF16}`);
    $("fallback-banner").hidden = true;
  } else {
    const how = info.fallbackReason ? "自动降级" : "手动指定";
    setBadge("backend-badge", "warn", `推理后端：WASM · ${precision} · ${info.threads} 线程（${how}）`, info.fallbackReason ?? "");
    if (info.fallbackReason && settings.backend !== "wasm") showFallback(info.fallbackReason);
  }
  const t = info.timings;
  setBadge(
    "model-badge",
    "info",
    `模型：${MODEL.repo.split("/")[1]} · ${fmtMB(info.bytes)} · 加载 ${fmtMs(t.totalMs)}${info.cacheHit ? "（缓存）" : ""}${info.model.source === "huggingface" ? "" : "（本地量化文件）"}`,
    `下载/读取 ${fmtMs(t.modelFetchMs)}，创建会话 ${fmtMs(t.sessionCreateMs)}，预热推理 ${fmtMs(t.firstInferMs)}；文件 ${info.model.source === "huggingface" ? MODEL.repo : info.model.source}/${info.model.file}`
  );
  $("foot-model").textContent = `${MODEL.repo}@${MODEL.revision.slice(0, 7)}，${info.backend === "webgpu" ? "WebGPU" : "WASM"} ${precision}`;
}

// ------------------------------------------------------------------ knowledge bases

async function refreshKbList(prefer) {
  let { kbs } = await api.listKbs();
  if (!kbs.length) {
    await api.createKb({ name: DEFAULT_KB, modelId: MODEL.repo, dim: MODEL.dim });
    ({ kbs } = await api.listKbs());
  }
  const sel = $("kb-select");
  sel.replaceChildren(...kbs.map((k) => new Option(`${k.name}（${k.docs} 篇）`, k.name)));
  const want = [prefer, localStorage.getItem(LS_KB), DEFAULT_KB].find((n) => n && kbs.some((k) => k.name === n)) ?? kbs[0].name;
  sel.value = want;
  if (want !== state.kb) await switchKb(want);
  else await refreshKbInfo();
}

async function switchKb(name) {
  state.kb = name;
  state.searchSeq++; // results still in flight for the previous KB are dropped
  localStorage.setItem(LS_KB, name);
  $("results").replaceChildren();
  $("timing").hidden = true;
  $("params-box").hidden = true;
  $("import-summary").replaceChildren();
  await Promise.all([refreshKbInfo(), refreshDocs(), refreshHistory()]);
}

async function refreshKbInfo() {
  const kb = await api.getKb(state.kb);
  state.kbInfo = kb;
  const mismatch = kb.modelId !== MODEL.repo || kb.dim !== MODEL.dim;
  $("kb-stats").innerHTML = `
    <dt>文档</dt><dd>${kb.docs}</dd>
    <dt>分块</dt><dd>${kb.chunks}</dd>
    <dt>版本</dt><dd>v${kb.version}<span class="muted">（每次导入/删除 +1）</span></dd>
    <dt>向量</dt><dd>${esc(kb.modelId)} · ${kb.dim} 维${mismatch ? ' <b style="color:var(--err)">与当前模型不一致</b>' : ""}</dd>`;
  const opt = [...$("kb-select").options].find((o) => o.value === kb.name);
  if (opt) opt.textContent = `${kb.name}（${kb.docs} 篇）`;
  state.kbCompatible = !mismatch;
  setBusy(state.busy);
  updateSearchEnabled();
}

async function refreshDocs() {
  const { docs } = await api.listDocs(state.kb);
  state.docs = docs;
  renderDocs();
}

function renderDocs() {
  const f = $("doc-filter").value.trim().toLowerCase();
  const list = state.docs.filter((d) => !f || `${d.title} ${d.key}`.toLowerCase().includes(f));
  $("doc-count").textContent = `${state.docs.length} 篇`;
  $("doc-list").replaceChildren(
    ...list.slice(0, 300).map((d) => {
      const li = document.createElement("li");
      li.innerHTML = `<div class="title" title="${esc(d.key)}">${esc(d.title || d.key)}<br><small>${esc(d.key)} · ${d.chunks} 块 · ${d.chars} 字</small></div>`;
      const del = document.createElement("button");
      del.className = "ghost danger";
      del.textContent = "删除";
      del.onclick = () => deleteDoc(d.key);
      li.append(del);
      return li;
    })
  );
  if (list.length > 300) $("doc-list").append(Object.assign(document.createElement("li"), { textContent: `……另有 ${list.length - 300} 篇，可用筛选查找` }));
}

async function refreshHistory() {
  const { imports } = await api.listImports(state.kb);
  $("history").innerHTML = imports
    .map((i) => {
      const c = i.client ?? {};
      const t = i.timings ?? {};
      const when = new Date(i.finishedAt ?? i.startedAt).toLocaleString();
      return `<tr><td>${esc(when)}</td><td>${i.docsNew}/${i.docsChanged}/${i.docsUnchanged}</td><td>${i.chunks}</td>
        <td>${esc(c.backend ?? "–")} ${esc(c.dtype ?? "")}</td><td>${i.status === "committed" ? `${fmtMs(t.refreshMs)} ${esc(t.refreshMode ?? "")}` : esc(i.status)}</td></tr>`;
    })
    .join("");
}

async function deleteDoc(key) {
  if (!confirm(`从知识库 ${state.kb} 删除文档「${key}」及其全部分块？`)) return;
  try {
    const r = await api.deleteDoc(state.kb, key);
    $("import-summary").innerHTML = `已删除 <b>${esc(key)}</b>，知识库版本 v${r.version}（seekdb ${fmtMs(r.dbMs)}）`;
    await Promise.all([refreshKbInfo(), refreshDocs()]);
  } catch (e) {
    showError(e);
  }
}

// ------------------------------------------------------------------ import

function setBusy(b) {
  state.busy = b;
  for (const el of document.querySelectorAll("#kb-select, #kb-delete, #kb-create-form button, #apply-settings")) el.disabled = b;
  // Vectors from a different model would not be comparable with this KB's, so no imports into it.
  const noImport = b || state.kbCompatible === false;
  for (const el of document.querySelectorAll("#paste-import, .samples button")) el.disabled = noImport;
  $("dropzone").style.pointerEvents = noImport ? "none" : "";
  $("dropzone").style.opacity = noImport ? 0.5 : 1;
}

const PHASES = { plan: "比对已有文档…", embed: "本地向量化", write: "写入 seekdb", commit: "提交并等待索引刷新…" };

async function runImport(docs, what) {
  if (state.busy || !docs.length) return;
  showError(null);
  if (!embedder.info) {
    try {
      await embedder.ready;
    } catch {
      return showError(new Error("模型未加载，无法向量化"));
    }
  }
  setBusy(true);
  $("import-progress").hidden = false;
  $("import-summary").replaceChildren();
  const bar = $("import-bar");
  let embedded = 0;
  let written = 0;
  let total = 0;
  const t0 = performance.now();
  const kb = state.kb;
  try {
    const r = await importDocuments({
      kb,
      docs,
      embedder,
      options: { batchSize: Number(settings.batchSize), refresh: settings.refresh },
      client: { source: what, ua: navigator.userAgent },
      onProgress: (p) => {
        if (p.phase === "plan") $("import-phase").textContent = `${what}：新增 ${p.counts.new}，变更 ${p.counts.changed}，未变跳过 ${p.counts.unchanged}`;
        if (p.phase === "embed") ((embedded = p.done), (total = p.total));
        if (p.phase === "write") written = p.written;
        if (p.phase === "embed" || p.phase === "write") {
          const secs = (performance.now() - t0) / 1000;
          $("import-phase").textContent = `${PHASES.embed} ${embedded}/${total} 块 · ${PHASES.write} ${written}/${total} · ${(embedded / secs).toFixed(1)} 块/秒`;
          bar.max = Math.max(1, total * 2);
          bar.value = embedded + written;
        }
        if (p.phase === "commit") $("import-phase").textContent = PHASES.commit;
      },
    });
    renderImportSummary(r, what);
    await Promise.all([refreshKbInfo(), refreshDocs(), refreshHistory()]);
  } catch (e) {
    showError(e);
  } finally {
    $("import-progress").hidden = true;
    setBusy(false);
  }
}

function renderImportSummary(r, what) {
  const t = r.timings;
  const c = r.commitTimings ?? {};
  const rows = [
    ["文档（新增/变更/跳过）", `${r.counts.new} / ${r.counts.changed} / ${r.counts.unchanged}`],
    ["分块（已向量化）", `${r.chunks}`],
    ["本地向量化", `${fmtMs(t.embedMs)}${r.throughput.chunksPerSec ? ` · ${r.throughput.chunksPerSec} 块/秒` : ""}`],
    ["写入 seekdb（与向量化流水线重叠）", `${fmtMs(t.writeDbMs)} · ${t.writeRequests} 次请求`],
    ["索引刷新（" + (c.refreshMode ?? "–") + "）", fmtMs(c.refreshMs)],
    ["总耗时", fmtMs(t.totalMs)],
  ];
  $("import-summary").innerHTML = `<b>${esc(what)}</b> 导入完成，知识库版本 v${r.version}，新内容${r.visible ? "已可检索" : "<b>尚未确认可见</b>"}。
    <table>${rows.map(([k, v]) => `<tr><td>${k}</td><td>${v}</td></tr>`).join("")}</table>`;
}

async function importSample(kind) {
  if (state.busy) return;
  $("import-summary").replaceChildren();
  try {
    if (kind === "demo") {
      const { files } = await fetch("/samples/index.json").then((r) => r.json());
      const docs = await Promise.all(
        files.map(async (f) => ({ key: `samples/${f.file}`, title: f.title, text: await fetch(`/samples/${f.file}`).then((r) => r.text()), source: "samples" }))
      );
      return runImport(docs, "示例文档");
    }
    const lines = (await fetch("/eval/corpus.jsonl").then((r) => r.text())).trim().split("\n");
    const all = lines.map((l) => JSON.parse(l)).map((d) => ({ key: d.id, title: d.title, text: d.text, source: `miracl-${d.lang}` }));
    const half = Math.ceil(all.length / 2);
    return runImport(kind === "eval-a" ? all.slice(0, half) : all.slice(half), kind === "eval-a" ? "评测语料 A" : "评测语料 B");
  } catch (e) {
    showError(e);
  }
}

// ------------------------------------------------------------------ search

function updateSearchEnabled() {
  const needsModel = $("mode").value !== "fulltext";
  const compatible = state.kbCompatible !== false || !needsModel;
  const ready = state.kb && compatible && (!needsModel || embedder.info);
  $("search-btn").disabled = !ready;
  $("search-btn").textContent = !compatible ? "模型不匹配" : ready ? "检索" : "等待模型…";
}

function queryTerms(q) {
  const terms = new Set();
  for (const w of q.match(/[A-Za-z0-9][A-Za-z0-9_.+-]*/g) ?? []) if (w.length >= 2) terms.add(w);
  for (const run of q.match(/[㐀-鿿]+/g) ?? []) {
    if (run.length <= 2) terms.add(run);
    else for (let i = 0; i + 2 <= run.length; i++) terms.add(run.slice(i, i + 2));
  }
  return [...terms].sort((a, b) => b.length - a.length);
}

function highlight(text, terms) {
  const safe = esc(text);
  if (!terms.length) return safe;
  const re = new RegExp(terms.map((t) => esc(t).replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|"), "gi");
  return safe.replace(re, (m) => `<mark>${m}</mark>`);
}

async function doSearch(text) {
  text = text.trim();
  if (!text || !state.kb) return;
  showError(null);
  const seq = ++state.searchSeq;
  const kb = state.kb;
  const mode = $("mode").value;
  const t0 = performance.now();
  try {
    const r = await runSearch({ kb, text, embedder, mode, topK: Number($("topk").value), fusion: $("fusion").value, impl: settings.impl });
    if (seq !== state.searchSeq || kb !== state.kb) return; // a newer query or a KB switch won
    const tr = performance.now();
    renderResults(r.hits, text, mode);
    await nextFrame();
    const renderMs = performance.now() - tr;
    renderTiming({ ...r.timings, renderMs, e2eMs: performance.now() - t0 }, r.kbVersion, mode);
    $("params").textContent = r.params ? JSON.stringify(r.params, null, 2) : "（seekdb-js Collection.hybridSearch：SET @search_parm → DBMS_HYBRID_SEARCH.GET_SQL → 执行生成的 SQL）";
    $("params-box").hidden = false;
    if (state.kbInfo && r.kbVersion !== state.kbInfo.version) {
      // The KB changed elsewhere (another tab / import); bring the side panel up to date.
      await Promise.all([refreshKbInfo(), refreshDocs()]);
    }
  } catch (e) {
    if (seq === state.searchSeq) showError(e);
  }
}

function renderResults(hits, q, mode) {
  const terms = queryTerms(q);
  if (!hits.length) {
    $("results").innerHTML = `<li class="empty">没有结果。${state.kbInfo?.chunks ? "" : "当前知识库为空，请先导入文档。"}</li>`;
    return;
  }
  $("results").replaceChildren(
    ...hits.map((h, i) => {
      const m = h.meta ?? {};
      const li = document.createElement("li");
      const chips = [];
      // RRF reports each route's rank; a weighted sum only each route's weighted score
      if (h.keywordRank != null) chips.push(`<span class="chip kw" title="全文路名次（seekdb 计算）">全文 #${h.keywordRank}</span>`);
      else if (h.keywordScore != null) chips.push(`<span class="chip kw" title="全文路加权得分（seekdb 计算）">全文 ${Number(h.keywordScore).toFixed(3)}</span>`);
      if (h.semanticRank != null) chips.push(`<span class="chip sem" title="向量路名次（seekdb 计算）">向量 #${h.semanticRank}</span>`);
      else if (h.semanticScore != null) chips.push(`<span class="chip sem" title="向量路加权得分（seekdb 计算）">向量 ${Number(h.semanticScore).toFixed(3)}</span>`);
      chips.push(`<span class="chip" title="${mode === "hybrid" ? "融合得分" : "得分"}">${Number(h.score).toFixed(4)}</span>`);
      li.innerHTML = `<div class="head"><div><span class="rank">${i + 1}.</span><span class="doc-title">${esc(m.title || m.doc_key || h.id)}</span></div>
        <div class="chips">${chips.join("")}</div></div>
        <div class="text">${highlight(h.text, terms)}</div>
        <div class="meta">${esc(m.doc_key ?? "")} · 第 ${(m.chunk_index ?? 0) + 1}/${m.chunk_count ?? 1} 块${m.backend ? ` · 向量由 ${esc(m.backend)} ${esc(m.dtype ?? "")} 生成` : ""}</div>`;
      return li;
    })
  );
}

function renderTiming(t, version, mode) {
  const parts = [];
  if (mode !== "fulltext") parts.push(`查询向量化 <b>${fmtMs(t.queryEmbedMs)}</b>${t.cacheHit ? "（缓存命中）" : ""}`);
  parts.push(`seekdb 检索 <b>${fmtMs(t.seekdbMs)}</b>`, `服务与网络 <b>${fmtMs(t.searchRoundTripMs - t.seekdbMs)}</b>`, `渲染 <b>${fmtMs(t.renderMs)}</b>`);
  parts.push(`<span class="total">端到端 <b>${fmtMs(t.e2eMs)}</b></span>`, `<span class="muted">知识库 v${version}</span>`);
  $("timing").innerHTML = parts.map((p) => `<span>${p}</span>`).join("");
  $("timing").hidden = false;
}

// ------------------------------------------------------------------ wiring

function bindUi() {
  $("kb-select").onchange = (e) => switchKb(e.target.value).catch(showError);
  $("kb-create-form").onsubmit = async (e) => {
    e.preventDefault();
    const name = $("kb-new-name").value.trim();
    try {
      await api.createKb({ name, modelId: MODEL.repo, dim: MODEL.dim });
      $("kb-new-name").value = "";
      await refreshKbList(name);
    } catch (err) {
      showError(err);
    }
  };
  $("kb-delete").onclick = async () => {
    if (!state.kb || !confirm(`删除知识库 ${state.kb}？其中的文档、向量和导入记录都会从 seekdb 删除。`)) return;
    try {
      await api.deleteKb(state.kb);
      localStorage.removeItem(LS_KB);
      state.kb = null;
      await refreshKbList();
    } catch (err) {
      showError(err);
    }
  };
  const dz = $("dropzone");
  $("file-input").onchange = async (e) => {
    const files = [...e.target.files];
    $("import-summary").replaceChildren();
    e.target.value = "";
    runImport(await parseFiles(files), `${files.length} 个文件`).catch(showError);
  };
  dz.ondragover = (e) => (e.preventDefault(), dz.classList.add("over"));
  dz.ondragleave = () => dz.classList.remove("over");
  dz.ondrop = async (e) => {
    e.preventDefault();
    dz.classList.remove("over");
    const files = [...e.dataTransfer.files];
    if (files.length) runImport(await parseFiles(files), `${files.length} 个文件`).catch(showError);
  };
  $("paste-import").onclick = async () => {
    const text = $("paste-text").value.trim();
    if (!text) return;
    const title = $("paste-title").value.trim();
    const key = title ? `paste/${title}` : `paste/${(await crypto.subtle.digest("SHA-1", new TextEncoder().encode(text)).then((b) => [...new Uint8Array(b)].slice(0, 6).map((x) => x.toString(16).padStart(2, "0")).join("")))}`;
    await runImport([{ key, title: title || text.slice(0, 20), text, source: "paste" }], "粘贴文本");
    $("paste-text").value = "";
  };
  for (const b of document.querySelectorAll("[data-sample]")) b.onclick = () => importSample(b.dataset.sample);
  $("doc-filter").oninput = renderDocs;
  $("search-form").onsubmit = (e) => {
    e.preventDefault();
    doSearch($("q").value);
  };
  $("mode").onchange = updateSearchEnabled;
  $("examples").replaceChildren(
    ...EXAMPLES.map((q) => {
      const b = document.createElement("button");
      b.type = "button";
      b.textContent = q;
      b.onclick = () => (($("q").value = q), doSearch(q));
      return b;
    })
  );
  for (const [id, key] of [["set-backend", "backend"], ["set-dtype", "dtype"], ["set-source", "source"], ["set-batch", "batchSize"], ["set-refresh", "refresh"], ["set-impl", "impl"]]) {
    $(id).value = String(settings[key]);
    $(id).onchange = (e) => {
      settings[key] = e.target.value;
      localStorage.setItem(LS_SETTINGS, JSON.stringify(settings));
    };
  }
  $("apply-settings").onclick = () => startModel();
}

async function main() {
  bindUi();
  startModel(); // loads in parallel with the seekdb/KB setup below
  try {
    const h = await api.health();
    setBadge("db-badge", "ok", `seekdb：${h.seekdb.replace(/^.*seekdb-/, "")} · ${h.mode === "embedded" ? "嵌入式" : "本地 server"}`, `database ${h.database}`);
    await refreshKbList();
  } catch (e) {
    setBadge("db-badge", "err", "seekdb：不可用");
    showError(e);
  }
}

main();
