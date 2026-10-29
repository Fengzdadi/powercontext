/* ExamRadar site — all data is read from site/data/*.json, nothing is hardcoded. */
(function () {
  "use strict";

  var COVERAGE_URL = "data/sample-coverage.json";
  var SESSIONS_URL = "data/qoder-sessions.json";
  var USAGE_URL = "data/usage-summary.json";
  var DEMO_VIDEO = "media/demo.mp4";

  var LEVEL_LABEL = { covered: "已覆盖", thin: "薄弱", missing: "缺失" };

  function esc(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }

  function fmtNum(v, digits) {
    if (v == null || isNaN(v)) return "—";
    return Number(v).toFixed(digits == null ? 2 : digits);
  }

  function fmtCredits(v) {
    if (v == null || isNaN(v)) return "—";
    return String(Math.round(v * 100) / 100);
  }

  function renderMarkdown(text) {
    if (typeof marked === "undefined") return "<p>" + esc(text) + "</p>";
    try {
      return marked.parse(esc(text));
    } catch (e) {
      return "<p>" + esc(text) + "</p>";
    }
  }

  /* ---------- screenshot placeholders: imgFallback lives in index.html <head> ---------- */

  /* ---------- coverage snapshot ---------- */
  function loadCoverage() {
    return fetch(COVERAGE_URL)
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (data) {
        if (!data || !Array.isArray(data.items) || data.items.length === 0) {
          document.getElementById("radar-empty").hidden = false;
          document.getElementById("radar-chart").style.display = "none";
          document.getElementById("blind-empty").hidden = false;
          return;
        }
        renderRadarMeta(data);
        renderRadarChart(data);
        renderBlindList(data);
      })
      .catch(function () {
        document.getElementById("radar-empty").hidden = false;
        document.getElementById("blind-empty").hidden = false;
      });
  }

  function renderRadarMeta(data) {
    var meta = document.getElementById("radar-meta");
    var bits = [];
    if (data.course_id) bits.push("课程 " + esc(data.course_id));
    if (Array.isArray(data.topics)) bits.push(data.topics.length + " 个知识点");
    if (data.created_at) bits.push("导出时间 " + esc(String(data.created_at).replace("T", " ").slice(0, 16)));
    meta.textContent = bits.join(" · ");
    var th = document.getElementById("radar-thresholds");
    if (th && data.config) {
      var parts = [];
      if (data.config.t_covered != null) parts.push("covered ≥ " + data.config.t_covered);
      if (data.config.t_thin != null) parts.push("thin ≥ " + data.config.t_thin);
      th.textContent = parts.length ? "判定阈值：" + parts.join("，") : "";
    }
  }

  function topicNames(data) {
    var names = {};
    (data.topics || []).forEach(function (t) { names[t.id] = t.name; });
    return names;
  }

  function renderRadarChart(data) {
    if (typeof echarts === "undefined") return;
    var names = topicNames(data);
    var items = data.items;
    var indicators = items.map(function (it) {
      return { name: (it.topic_name || names[it.topic_id] || it.topic_id || ""), max: 1 };
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
    var chart = echarts.init(document.getElementById("radar-chart"));
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
        radius: "62%",
        center: ["50%", "46%"],
        axisName: { color: "#4a5568", fontSize: 11 },
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

  function evidenceSource(ev) {
    if (!ev) return "";
    var parts = [];
    if (ev.document_name) parts.push(esc(ev.document_name));
    if (typeof ev.page === "number") parts.push("第 " + ev.page + " 页");
    if (ev.heading) parts.push(esc(ev.heading));
    return parts.join(" · ");
  }

  function renderBlindList(data) {
    var names = topicNames(data);
    var items = data.items.slice();
    items.sort(function (a, b) {
      var sa = a.blind_spot_score == null ? -1 : a.blind_spot_score;
      var sb = b.blind_spot_score == null ? -1 : b.blind_spot_score;
      if (sa !== sb) return sb - sa;
      return (b.exam_weight || 0) - (a.exam_weight || 0);
    });
    var tbody = document.getElementById("blind-tbody");
    var html = "";
    items.forEach(function (it, idx) {
      var lv = it.coverage_level;
      var badge = lv && LEVEL_LABEL[lv]
        ? '<span class="badge ' + lv + '">' + LEVEL_LABEL[lv] + "</span>"
        : '<span class="badge unknown">未知</span>';
      var name = it.topic_name || names[it.topic_id] || it.topic_id || "—";
      html +=
        '<tr class="row-main" data-idx="' + idx + '">' +
        "<td>" + esc(name) + "</td>" +
        "<td>" + badge + "</td>" +
        '<td class="num">' + fmtNum(it.coverage_score, 4) + "</td>" +
        '<td class="num">' + (it.exam_weight == null ? "—" : it.exam_weight) + "</td>" +
        '<td class="num">' + fmtNum(it.blind_spot_score) + "</td>" +
        '<td class="exp muted" style="text-align:center">&#9656;</td></tr>';

      var d = '<tr class="row-detail" data-detail="' + idx + '" hidden><td colspan="6"><div class="detail-box">';
      if (it.reason) {
        d += '<h4>判定理由</h4><p class="reason-text" style="margin-top:0">' + esc(it.reason) + "</p>";
      }
      var ev = it.best_evidence;
      if (ev) {
        d += '<h4 style="margin-top:14px">最强证据</h4><div class="evidence">';
        if (ev.content) d += '<div class="ev-content">' + renderMarkdown(ev.content) + "</div>";
        var src = evidenceSource(ev);
        var scores = [];
        if (ev.semantic_score != null) scores.push("语义分 " + fmtNum(ev.semantic_score, 4));
        if (ev.keyword_score != null) scores.push("关键词分 " + fmtNum(ev.keyword_score, 4));
        d += '<div class="ev-meta">' + (src ? src : "") +
          (scores.length ? (src ? " · " : "") + scores.join(" · ") : "") + "</div></div>";
      }
      if (Array.isArray(it.exam_questions) && it.exam_questions.length) {
        d += '<h4 style="margin-top:14px">关联的往年试题</h4><ul class="q-list">';
        it.exam_questions.forEach(function (q) {
          d += "<li>第 " + esc(q.question_no) + " 题 · " +
            (q.points == null ? "分值未知" : q.points + " 分") +
            (q.similarity != null ? " · 相似度 " + fmtNum(q.similarity, 3) : "") + "</li>";
        });
        d += "</ul>";
      }
      if (!it.reason && !ev && !(Array.isArray(it.exam_questions) && it.exam_questions.length)) {
        d += '<p class="muted" style="margin:0">这条记录缺少证据与试题数据。</p>';
      }
      d += "</div></td></tr>";
      html += d;
    });
    tbody.innerHTML = html;
    tbody.addEventListener("click", function (e) {
      var tr = e.target.closest("tr.row-main");
      if (!tr) return;
      var idx = tr.getAttribute("data-idx");
      var detail = tbody.querySelector('tr.row-detail[data-detail="' + idx + '"]');
      var open = !detail.hidden;
      detail.hidden = open;
      tr.classList.toggle("open", !open);
      tr.querySelector(".exp").innerHTML = open ? "&#9656;" : "&#9662;";
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
          wrap.innerHTML = '<tr><td colspan="6" class="muted">会话数据不可用。</td></tr>';
          totalRow.hidden = true;
          return;
        }
        var html = "";
        data.rows.forEach(function (r) {
          var modelCls = /GLM/i.test(r.model || "") ? "model-tag glm" : "model-tag";
          html +=
            "<tr>" +
            "<td>" + esc(r.id == null ? "—" : r.id) + "</td>" +
            '<td class="title-cell">' + esc(r.title || "—") + "</td>" +
            "<td class=" + JSON.stringify(modelCls) + ">" + esc(r.model || "—") + "</td>" +
            '<td class="num">' + (r.turns == null ? "—" : r.turns) + "</td>" +
            "<td>" + esc(r.duration || "—") + "</td>" +
            '<td class="num">' + fmtCredits(r.credits) + "</td>" +
            "</tr>";
        });
        wrap.innerHTML = html;
        var t = data.totals || {};
        document.getElementById("total-rows").textContent = t.rows != null ? t.rows : "—";
        document.getElementById("total-turns").textContent = t.turns != null ? t.turns : "—";
        document.getElementById("total-credits").textContent = t.credits != null ? fmtCredits(t.credits) : "—";
      })
      .catch(function () {
        document.getElementById("sessions-body").innerHTML =
          '<tr><td colspan="6" class="muted">会话数据不可用。</td></tr>';
        document.getElementById("sessions-total").hidden = true;
      });
  }

  /* ---------- usage summary ---------- */
  function loadUsage() {
    return fetch(USAGE_URL)
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (data) {
        var collecting = document.getElementById("usage-collecting");
        var filled = document.getElementById("usage-filled");
        if (!data || data.status === "collecting") {
          return; // default markup already shows the "collecting" state
        }
        collecting.hidden = true;
        filled.hidden = false;
        var stats = document.getElementById("usage-stats");
        var defs = [
          ["usage_days", "使用天数", "天"],
          ["study_sessions", "学习会话数", "次"],
          ["questions_answered", "做题数", "题"],
          ["total_minutes", "累计学习时长", "分钟"]
        ];
        stats.innerHTML = defs.map(function (d) {
          var v = data[d[0]];
          return '<div class="stat"><div class="v">' + (v == null ? "—" : esc(v)) +
            '</div><div class="k">' + d[1] + (v == null ? "" : " · " + d[2]) + "</div></div>";
        }).join("");
        var src = [];
        if (data.source) src.push("来源：" + esc(data.source));
        if (data.exported_at) src.push("导出时间：" + esc(data.exported_at));
        document.getElementById("usage-src").textContent = src.join(" · ");
      })
      .catch(function () { /* keep collecting state */ });
  }

  /* ---------- demo video ---------- */
  function loadVideo() {
    fetch(DEMO_VIDEO, { method: "HEAD" })
      .then(function (r) {
        if (r.ok) {
          document.getElementById("video-pending").hidden = true;
          var v = document.getElementById("demo-video");
          v.hidden = false;
          v.load();
        }
      })
      .catch(function () { /* keep pending placeholder */ });
  }

  document.addEventListener("DOMContentLoaded", function () {
    loadCoverage();
    loadSessions();
    loadUsage();
    loadVideo();
  });
})();
