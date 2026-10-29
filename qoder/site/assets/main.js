/* ExamRadar site — all data is read from site/data/*.json, nothing is hardcoded. */
(function () {
  "use strict";

  var COVERAGE_URL = "data/sample-coverage.json";
  var SESSIONS_URL = "data/qoder-sessions.json";
  var USAGE_URL = "data/usage-summary.json";

  var LEVEL_LABEL = { covered: "已覆盖", thin: "薄弱", missing: "缺失" };
  var QUESTION_SNIPPET = 60;

  function esc(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }

  function fmtNum(v, digits) {
    if (v == null || isNaN(v)) return "—";
    return Number(v).toFixed(digits == null ? 2 : digits);
  }

  function renderMarkdown(text) {
    if (typeof marked === "undefined") return "<p>" + esc(text) + "</p>";
    try {
      return marked.parse(esc(text));
    } catch (e) {
      return "<p>" + esc(text) + "</p>";
    }
  }

  /* paired backticks -> inline code; escape HTML first so the code span itself stays safe */
  function inlineCode(s) {
    return esc(s).replace(/`([^`]+)`/g, "<code>$1</code>");
  }

  function levelBadge(level) {
    return level && LEVEL_LABEL[level]
      ? '<span class="badge ' + level + '">' + LEVEL_LABEL[level] + "</span>"
      : '<span class="badge unknown">未知</span>';
  }

  /* ---------- screenshot placeholders: imgFallback lives in index.html <head> ---------- */

  /* ---------- coverage snapshot ---------- */
  function loadCoverage() {
    return fetch(COVERAGE_URL)
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (data) {
        var empty = !data || !Array.isArray(data.items) || data.items.length === 0;
        document.getElementById("radar-empty").hidden = !empty;
        document.getElementById("radar-chart").style.display = empty ? "none" : "";
        document.getElementById("blind-empty").hidden = !empty;
        if (empty) return;
        renderRadarMeta(data);
        renderRadarChart(data);
        renderBlindList(data);
      })
      .catch(function () {
        document.getElementById("radar-empty").hidden = false;
        document.getElementById("blind-empty").hidden = false;
      });
  }

  function fmtLocalTime(iso) {
    var d = new Date(iso);
    if (isNaN(d.getTime())) return "";
    var pad = function (n) { return (n < 10 ? "0" : "") + n; };
    var local = d.getFullYear() + "-" + pad(d.getMonth() + 1) + "-" + pad(d.getDate()) +
      " " + pad(d.getHours()) + ":" + pad(d.getMinutes());
    var off = -d.getTimezoneOffset();
    var sign = off >= 0 ? "+" : "-";
    var abs = Math.abs(off);
    var tz = "UTC" + sign + Math.floor(abs / 60) + (abs % 60 ? ":" + pad(abs % 60) : "");
    return local + "（访问者本地时间，" + tz + "）";
  }

  function methodText(config) {
    if (!config) return "";
    if (config.term_ratio_covered != null || config.support_chars_covered != null ||
        config.min_body_chars != null) {
      var parts = [];
      if (config.term_ratio_covered != null)
        parts.push("考点词找到比例阈值 " + config.term_ratio_covered);
      if (config.support_chars_covered != null)
        parts.push("支撑正文字数阈值 " + config.support_chars_covered + " 字");
      if (config.min_body_chars != null)
        parts.push("计入支撑的最小段字数 " + config.min_body_chars + " 字");
      return "判定规则：一个考点词（含别名）都没找到 → 缺失；找到比例与支撑字数都达到阈值 → 已覆盖；其余 → 薄弱。" +
        "（" + parts.join("；") + "）";
    }
    var legacy = [];
    if (config.t_covered != null) legacy.push("covered ≥ " + config.t_covered);
    if (config.t_thin != null) legacy.push("thin ≥ " + config.t_thin);
    return legacy.length ? "判定阈值：" + legacy.join("，") : "";
  }

  function renderRadarMeta(data) {
    var meta = document.getElementById("radar-meta");
    var bits = [];
    if (data.course_id) bits.push("课程 " + esc(data.course_id));
    if (Array.isArray(data.topics)) bits.push(data.topics.length + " 个知识点");
    if (data.created_at) bits.push("导出时间 " + esc(fmtLocalTime(data.created_at)));
    meta.textContent = bits.join(" · ");
    var th = document.getElementById("radar-method");
    if (th) th.textContent = methodText(data.config);
  }

  function topicNames(data) {
    var names = {};
    (data.topics || []).forEach(function (t) { names[t.id] = t.name; });
    return names;
  }

  /* axis labels wrap only at ：、与、（ and spaces — ASCII words (WAL / MVCC /
     3NF …) are never split. ： and （ are hard breaks; a line that would still
     overflow backtracks to the last soft break (after 与 or a space). */
  function wrapAxisLabel(name, maxLine) {
    var s = String(name == null ? "" : name);
    if (!s) return "";
    var tokens = s.match(/[A-Za-z0-9]+|[^A-Za-z0-9]/g) || [];
    var widthOf = function (t) {
      var w = 0;
      for (var i = 0; i < t.length; i++)
        w += t.charAt(i) === " " ? 0.3 : (t.charCodeAt(i) < 128 ? 0.55 : 1);
      return w;
    };
    var lines = [];
    var cur = "";
    var curW = 0;
    var mark = -1; /* index in cur where a soft break is allowed */
    var prevTok = "";
    tokens.forEach(function (tok) {
      if (tok === " ") {
        if (cur !== "") { cur += " "; curW += 0.3; mark = cur.length - 1; }
        return;
      }
      var w = widthOf(tok);
      if (cur !== "" && (tok === "（" || prevTok === "：")) {
        lines.push(cur);
        cur = ""; curW = 0; mark = -1;
      } else if (cur !== "" && curW + w > maxLine) {
        if (mark > 0) {
          lines.push(cur.slice(0, mark));
          cur = cur.slice(mark).replace(/^ /, "");
          curW = widthOf(cur);
          mark = -1;
        } /* else: no allowed break point — the container measurement is the real limit */
      }
      cur += tok;
      curW += w;
      if (tok === "：" || tok === "与") mark = cur.length;
      prevTok = tok;
    });
    if (cur !== "" || lines.length === 0) lines.push(cur);
    return lines.join("\n");
  }

  function renderRadarChart(data) {
    if (typeof echarts === "undefined") return;
    var el = document.getElementById("radar-chart");
    var narrow = el.clientWidth < 420;
    var maxLine = narrow ? 8 : 11;
    var names = topicNames(data);
    var items = data.items;
    var indicators = items.map(function (it) {
      return { name: wrapAxisLabel(it.topic_name || names[it.topic_id] || it.topic_id || "", maxLine), max: 1 };
    });
    var coverage = items.map(function (it) {
      return it.coverage_score == null ? 0 : Math.max(0, Math.min(1, it.coverage_score));
    });
    var maxWeight = 0;
    items.forEach(function (it) {
      if (typeof it.exam_weight === "number" && it.exam_weight > maxWeight) maxWeight = it.exam_weight;
    });
    var weight = items.map(function (it) {
      if (maxWeight <= 0 || it.exam_weight == null) return 0;
      return Math.max(0, Math.min(1, it.exam_weight / maxWeight));
    });
    var chart = echarts.init(el, null, { renderer: "svg" });
    chart.setOption({
      tooltip: {
        trigger: "item",
        confine: true,
        formatter: function (p) {
          var i = p.dataIndex;
          var it = items[i];
          var lv = LEVEL_LABEL[it.coverage_level] || it.coverage_level || "未知";
          return esc(it.topic_name || names[it.topic_id] || it.topic_id) + "<br/>" +
            "覆盖度：" + fmtNum(it.coverage_score, 4) + "（" + lv + "）<br/>" +
            "往年分值：" + (it.exam_weight == null ? "—" : it.exam_weight + " 分");
        }
      },
      legend: { bottom: 8, data: ["覆盖度", "考试权重（按最大分值归一化）"], textStyle: { fontSize: 12 } },
      radar: {
        indicator: indicators,
        radius: narrow ? "46%" : "58%",
        center: ["50%", "46%"],
        axisName: { color: "#4a5568", fontSize: narrow ? 10 : 11, lineHeight: narrow ? 13 : 15 },
        splitArea: { areaStyle: { color: ["#ffffff", "#f4f7fc"] } }
      },
      series: [{
        type: "radar",
        data: [
          {
            name: "覆盖度",
            value: coverage,
            itemStyle: { color: "#2456d6" },
            areaStyle: { color: "rgba(36,86,214,0.18)" },
            lineStyle: { width: 2 }
          },
          {
            name: "考试权重（按最大分值归一化）",
            value: weight,
            itemStyle: { color: "#e67e22" },
            areaStyle: { color: "rgba(230,126,34,0.12)" },
            lineStyle: { width: 2, type: "dashed" }
          }
        ]
      }]
    });
    window.addEventListener("resize", function () { chart.resize(); });
  }

  /* ---------- blind spot list (shared detail builder, table + mobile cards) ---------- */
  function sortedItems(data) {
    return data.items.slice().sort(function (a, b) {
      var sa = a.blind_spot_score == null ? -1 : a.blind_spot_score;
      var sb = b.blind_spot_score == null ? -1 : b.blind_spot_score;
      if (sa !== sb) return sb - sa;
      return String(a.topic_id || "").localeCompare(String(b.topic_id || ""), "en");
    });
  }

  function chunkRef(c) {
    var parts = [];
    if (c.doc) parts.push(esc(c.doc));
    if (typeof c.page === "number") parts.push("第 " + c.page + " 页");
    if (c.heading) parts.push(esc(c.heading));
    return parts.join(" · ");
  }

  function termsHtml(it) {
    if (!Array.isArray(it.terms) || it.terms.length === 0) return "";
    var lis = it.terms.map(function (t) {
      var alias = Array.isArray(t.aliases) && t.aliases.length
        ? '<span class="term-alias">（别名：' + t.aliases.map(esc).join("、") + "）</span>" : "";
      var found = t.found
        ? '<span class="term-found">✓ 找到</span>'
        : '<span class="term-miss">✗ 没找到</span>';
      var chunks = "";
      if (t.found && Array.isArray(t.chunks) && t.chunks.length) {
        var shown = t.chunks.slice(0, 3).map(function (c) {
          return "<div>" + chunkRef(c) + "</div>";
        }).join("");
        if (t.chunks.length > 3)
          shown += '<div class="muted">…等共 ' + t.chunks.length + " 段</div>";
        chunks = '<div class="term-chunks">' + shown + "</div>";
      }
      return '<li><div class="term-line"><span class="term-name">' + esc(t.term) + "</span>" +
        alias + found + "</div>" + chunks + "</li>";
    });
    return '<h4 style="margin-top:14px">考点词明细</h4><ul class="term-list">' + lis.join("") + "</ul>";
  }

  function supportHtml(it) {
    if (it.support_chunks == null && it.support_chars == null) return "";
    var chunks = it.support_chunks == null ? "—" : it.support_chunks;
    var chars = it.support_chars == null ? "—" : it.support_chars;
    return '<p class="muted" style="font-size:13px;margin:8px 0 0">支撑正文：' +
      chunks + " 段，共 " + chars + " 字</p>";
  }

  function evidenceHtml(it) {
    var ev = it.best_evidence;
    if (!ev) return "";
    var html = '<h4 style="margin-top:14px">最强证据</h4><div class="evidence">';
    if (ev.content) html += '<div class="ev-content">' + renderMarkdown(ev.content) + "</div>";
    var parts = [];
    if (ev.document_name) parts.push(esc(ev.document_name));
    if (typeof ev.page === "number") parts.push("第 " + ev.page + " 页");
    if (ev.heading) parts.push(esc(ev.heading));
    var scores = [];
    if (ev.semantic_score != null) scores.push("语义分 " + fmtNum(ev.semantic_score, 4));
    if (ev.keyword_score != null) scores.push("关键词分 " + fmtNum(ev.keyword_score, 4));
    html += '<div class="ev-meta">' + parts.join(" · ") +
      (scores.length ? (parts.length ? " · " : "") + scores.join(" · ") : "") + "</div></div>";
    return html;
  }

  function questionsHtml(it) {
    if (!Array.isArray(it.exam_questions) || it.exam_questions.length === 0) return "";
    var qs = it.exam_questions.map(function (q, qi) {
      var line = "第 " + esc(q.question_no) + " 题 · " +
        (q.points == null ? "分值未知" : q.points + " 分");
      if (Array.isArray(q.matched_terms) && q.matched_terms.length)
        line += " · 命中考点词：" + q.matched_terms.map(esc).join("、");
      if (q.similarity != null) line += " · 相似度 " + fmtNum(q.similarity, 3);
      var content = "";
      if (q.content) {
        var text = String(q.content);
        var snippet = text.slice(0, QUESTION_SNIPPET);
        var expandable = text.length > QUESTION_SNIPPET;
        var shortText = snippet + (expandable ? "…" : "");
        content = '<div class="q-content"><span class="q-snippet" data-short="' +
          esc(shortText) + '" data-full="' + esc(text) + '">' + esc(shortText) + "</span>";
        if (expandable)
          content += ' <button class="q-toggle" data-q="' + qi + '">展开原文</button>';
        content += "</div>";
      }
      return '<div class="q-item"><div class="q-line">' + line + "</div>" + content + "</div>";
    }).join("");
    return '<h4 style="margin-top:14px">关联的往年试题</h4>' + qs;
  }

  function detailHtml(it) {
    var html = '<div class="detail-box">';
    if (it.reason)
      html += '<h4>判定理由</h4><p class="reason-text" style="margin-top:0">' + esc(it.reason) + "</p>";
    html += supportHtml(it) + termsHtml(it) + evidenceHtml(it) + questionsHtml(it);
    if (!it.reason && !it.best_evidence && !it.terms &&
        !(Array.isArray(it.exam_questions) && it.exam_questions.length))
      html += '<p class="muted" style="margin:0">这条记录缺少证据与试题数据。</p>';
    html += "</div>";
    return html;
  }

  function toggleQuestion(btn) {
    var item = btn.closest(".q-item");
    var snippet = item.querySelector(".q-snippet");
    if (!snippet) return;
    var showing = btn.textContent === "收起原文";
    btn.textContent = showing ? "展开原文" : "收起原文";
    snippet.textContent = showing ? snippet.getAttribute("data-short") : snippet.getAttribute("data-full");
  }

  function renderBlindList(data) {
    var names = topicNames(data);
    var items = sortedItems(data);

    var tbody = document.getElementById("blind-tbody");
    var rowsHtml = "";
    var cardsHtml = "";
    items.forEach(function (it, idx) {
      var name = it.topic_name || names[it.topic_id] || it.topic_id || "—";
      var cov = fmtNum(it.coverage_score, 4);
      var weight = it.exam_weight == null ? "—" : it.exam_weight;
      var blind = fmtNum(it.blind_spot_score);

      rowsHtml +=
        '<tr class="row-main" data-idx="' + idx + '">' +
        "<td>" + esc(name) + "</td>" +
        "<td>" + levelBadge(it.coverage_level) + "</td>" +
        '<td class="num">' + cov + "</td>" +
        '<td class="num">' + weight + "</td>" +
        '<td class="num">' + blind + "</td>" +
        '<td class="exp muted" style="text-align:center">&#9656;</td></tr>' +
        '<tr class="row-detail" data-detail="' + idx + '" hidden><td colspan="6">' + detailHtml(it) + "</td></tr>";

      cardsHtml +=
        '<div class="blind-card"><div class="bc-head" data-idx="' + idx + '">' +
        '<span class="bc-name">' + esc(name) + "</span>" + levelBadge(it.coverage_level) +
        '<span class="exp muted">&#9656;</span></div>' +
        '<div class="bc-stats">' +
        "<div><b>" + cov + '</b>覆盖度</div>' +
        "<div><b>" + weight + '</b>往年分值</div>' +
        "<div><b>" + blind + '</b>盲区分值</div>' +
        "</div><div class=\"bc-detail\" data-idx=\"" + idx + "\" hidden>" + detailHtml(it) + "</div></div>";
    });
    tbody.innerHTML = rowsHtml;
    document.getElementById("blind-cards").innerHTML = cardsHtml;

    function toggle(root, idx) {
      var head = root.querySelector('[data-idx="' + idx + '"]');
      var detail = root.querySelector('.row-detail[data-detail="' + idx + '"], .bc-detail[data-idx="' + idx + '"]');
      var open = !detail.hidden;
      detail.hidden = open;
      head.classList.toggle("open", !open);
      var exp = head.querySelector(".exp");
      if (exp) exp.innerHTML = open ? "&#9656;" : "&#9662;";
    }

    tbody.addEventListener("click", function (e) {
      if (e.target.closest(".q-toggle")) { toggleQuestion(e.target.closest(".q-toggle")); return; }
      var tr = e.target.closest("tr.row-main");
      if (tr) toggle(tbody, tr.getAttribute("data-idx"));
    });
    var cards = document.getElementById("blind-cards");
    cards.addEventListener("click", function (e) {
      if (e.target.closest(".q-toggle")) { toggleQuestion(e.target.closest(".q-toggle")); return; }
      var head = e.target.closest(".bc-head");
      if (head) toggle(cards, head.getAttribute("data-idx"));
    });
  }

  /* ---------- qoder sessions ---------- */
  function loadSessions() {
    return fetch(SESSIONS_URL)
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (data) {
        var wrap = document.getElementById("sessions-body");
        var totalRow = document.getElementById("sessions-total");
        if (!data || !Array.isArray(data.rows) || data.rows.length === 0) {
          wrap.innerHTML = '<tr><td colspan="5" class="muted">会话数据不可用。</td></tr>';
          totalRow.hidden = true;
          return;
        }
        var html = "";
        var cardsHtml = "";
        data.rows.forEach(function (r) {
          var modelCls = /GLM/i.test(r.model || "") ? "model-tag glm" : "model-tag";
          html +=
            "<tr>" +
            "<td>" + esc(r.id == null ? "—" : r.id) + "</td>" +
            '<td class="title-cell">' + inlineCode(r.title || "—") + "</td>" +
            "<td class=" + JSON.stringify(modelCls) + ">" + esc(r.model || "—") + "</td>" +
            '<td class="num">' + (r.turns == null ? "—" : r.turns) + "</td>" +
            "<td>" + esc(r.duration || "—") + "</td>" +
            "</tr>";
          cardsHtml +=
            '<div class="session-card">' +
            '<div class="sc-head"><span class="sc-id">会话 ' + esc(r.id == null ? "—" : r.id) + "</span>" +
            '<span class="' + modelCls + '">' + esc(r.model || "—") + "</span></div>" +
            '<div class="sc-title">' + inlineCode(r.title || "—") + "</div>" +
            '<div class="sc-stats">' +
            "<div><b>" + (r.turns == null ? "—" : r.turns) + "</b>轮数</div>" +
            "<div><b>" + esc(r.duration || "—") + "</b>耗时</div>" +
            "</div></div>";
        });
        wrap.innerHTML = html;
        var t = data.totals || {};
        document.getElementById("total-rows").textContent = t.rows != null ? t.rows : "—";
        document.getElementById("total-turns").textContent = t.turns != null ? t.turns : "—";
        cardsHtml += '<div class="session-total">合计 ' + (t.rows != null ? t.rows : "—") +
          " 条记录 · " + (t.turns != null ? t.turns : "—") + " 轮</div>";
        document.getElementById("sessions-cards").innerHTML = cardsHtml;
      })
      .catch(function () {
        document.getElementById("sessions-body").innerHTML =
          '<tr><td colspan="5" class="muted">会话数据不可用。</td></tr>';
        document.getElementById("sessions-total").hidden = true;
      });
  }

  /* ---------- usage summary: three optional blocks ---------- */
  function statCard(value, label, unit) {
    return '<div class="stat"><div class="v">' + (value == null ? "—" : esc(value)) +
      '</div><div class="k">' + esc(label) + (unit && value != null ? " · " + esc(unit) : "") + "</div></div>";
  }

  function srcLine(obj) {
    var parts = [];
    if (obj && obj.source) parts.push("来源：" + esc(obj.source));
    if (obj && obj.exported_at) parts.push("导出时间：" + esc(obj.exported_at));
    return parts.length ? '<p class="usage-src">' + parts.join(" · ") + "</p>" : "";
  }

  function loadUsage() {
    return fetch(USAGE_URL)
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (data) {
        var collecting = document.getElementById("usage-collecting");
        var filled = document.getElementById("usage-filled");
        if (!data || data.status === "collecting") return;
        var blocks = [];

        var site = data.site_stats;
        if (site && (site.pv != null || site.uv != null)) {
          var period = site.period ? "（" + esc(site.period) + "）" : "";
          blocks.push('<div class="usage-block"><h3>Qoder Sites 访问统计' + period + "</h3>" +
            '<div class="usage-stats">' +
            statCard(site.pv, "页面浏览 PV") + statCard(site.uv, "独立访客 UV") +
            "</div>" + srcLine(site) + "</div>");
        }

        var usage = data.usage || {
          usage_days: data.usage_days, study_sessions: data.study_sessions,
          questions_answered: data.questions_answered, total_minutes: data.total_minutes,
          source: data.source, exported_at: data.exported_at
        };
        if (usage && (usage.usage_days != null || usage.study_sessions != null ||
            usage.questions_answered != null || usage.total_minutes != null)) {
          blocks.push('<div class="usage-block"><h3>使用记录汇总</h3><div class="usage-stats">' +
            statCard(usage.usage_days, "使用天数", "天") +
            statCard(usage.study_sessions, "学习会话数", "次") +
            statCard(usage.questions_answered, "做题数", "题") +
            statCard(usage.total_minutes, "累计学习时长", "分钟") +
            "</div>" + srcLine(usage) + "</div>");
        }

        var feedback = data.feedback;
        if (Array.isArray(feedback) && feedback.length) {
          var quotes = feedback.map(function (f) {
            return "<li>" + esc(typeof f === "string" ? f : (f.quote || "")) + "</li>";
          }).join("");
          var meta = Array.isArray(feedback) && feedback[0] && typeof feedback[0] === "object"
            ? srcLine(feedback[0]) : "";
          blocks.push('<div class="usage-block"><h3>用户反馈</h3>' +
            '<ul class="feedback-list">' + quotes + "</ul>" + meta + "</div>");
        }

        if (!blocks.length) return;
        collecting.hidden = true;
        filled.hidden = false;
        document.getElementById("usage-blocks").innerHTML = blocks.join("");
      })
      .catch(function () { /* keep collecting state */ });
  }

  document.addEventListener("DOMContentLoaded", function () {
    loadCoverage();
    loadSessions();
    loadUsage();
  });
})();
