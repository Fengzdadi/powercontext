# Qoder 会话记录：09c-site-polish-2

| 项目 | 值 |
| --- | --- |
| 会话 ID | `8e45da84-f65d-4618-90a7-1693286474b6` |
| Qoder CLI | 1.1.80，模型 GLM-5.3，权限模式 acceptEdits |
| 工作目录 | `/Users/wanderer/Project/oceanbase/powercontext-camp/.camp/wt/eco-qoder-site/qoder` |
| 开始 / 结束 | 2026-10-29T00:50:42-0400 / 2026-10-29T00:57:45-0400 |
| 轮数 / 耗时 | 13 轮 / 7.0 分钟 |
| Credits | 257.26724848（逐条请求累加 107.24） |
| 原始记录 | `sessions/09c-site-polish-2.jsonl`（完整 stream-json） |

## 产品负责人的指令

接着改一处：手机宽度下雷达图的轴标签把英文缩写拆开了。

- 375px 下看到的：
  - "WAL 与 AR" / "IES"
  - "隔离级别与 MV" / "CC"
  - "（3NF、BCN" / "F）"
- 原因：标签按"每行最多 8 个字"折行，拆到了缩写中间。
- 规则和会话 05b 改应用里的雷达图一样：
  - 只在"："、"与"、"（"、空格这些位置换行；
  - 英文单词和 3NF、BCNF、WAL、ARIES、MVCC、2PC 这类缩写不能拆开；
  - 放不下就缩小半径或字号。

## 验收标准

桌面（1440×900）和手机（375×812）两种宽度都要检查，结果补进 DEVLOG 会话 09c 一节：

- 每个轴标签的每一行（SVG 的 text / tspan）都在图表容器内，并且和图例不相交。
- 列出每个知识点名称换行后的各行。任何一个换行点，前一个字符和后一个字符不能都是 ASCII 字母或数字。
- 截图，用 Read 看一遍。

规则同前：只改 `site/` 下除 `site/data/` 以外的文件和 DEVLOG；预览只用 18808 端口，结束时关掉；不要发布网站。

## 对话过程

<details><summary>Qoder 思考</summary>

Task: fix radar axis label wrapping in main.js `wrapAxisLabel`. Current: breaks after "："、"（" and hard-wraps every maxLine chars, splitting abbreviations.

New rules:
- Only break at "：", "与", "（", space positions.
- Never split English words/abbreviations (WAL, ARIES, MVCC, 2PC, 3NF, BCNF).
- If doesn't fit, shrink radius or font size.

Topic names (need to check actual names in sample-coverage.json):
- "函数依赖与范式（3NF、BCNF）" → break before （: "函数依赖与范式" / "（3NF、BCNF）". Hmm "、" — is 、a break point? The rules say break only at "：","与","（",space. "（3NF、BCNF）" at narrow width: 10 chars "（3NF、BCNF）" — width? At font 10px, ASCII chars ~5.5px, CJK 10px. "（3NF、BCNF）" = （(10) + 3NF(16.5) + 、(10) + BCNF(22) + ）(10) ≈ 68px. Narrow chart 333px wide, radius 46% → center at 50%,46%. Label placement outside. Should be fine on one line.
- "WAL 与 ARIES" → break at spaces and "与": "WAL 与" / "ARIES" or "WAL" / "与 ARIES".
- "隔离级别与 MVCC" → "隔离级别与" / "MVCC".

Implementation approach: tokenize the label into units: each ASCII alnum run (plus maybe ".", digits like 2PC) is one unbreakable token; each CJK char is a token but breaks only allowed after "：","与","（", space... Wait rule: "只在'：'、'与'、'（'、空格这些位置换行" — break opportunities after these chars. But what about long CJK stretches without those chars, e.g. "函数依赖与范式（3NF、BCNF）"? Break points: after "与" ("函数依赖与 / 范式（3NF、BCNF）")? and before/after "（". Hmm, if we only break at 与：（space, then "函数依赖与范式" (7 chars) must fit on one line unless we break after 与. At narrow maxLine=8: "函数依赖与" (5) + "范式（3NF、BCNF）" — that fits.

But what if a segment without break points exceeds width? E.g. a name like "事务与并发控制" has 与. Let me look at actual topic names first. Need to read sample-coverage.json topics.

Also line width limit: instead of char count, maybe measure by estimated width? Simpler: keep char-count-based but count ASCII chars as 0.5? Better: build lines by greedily packing tokens, with a width budget computed as maxLine (CJK chars) where ASCII chars count ~0.55. Hmm, but the acceptance is DOM-measured: labels in container, not overlapping legend, break points not between ASCII alnum chars. The width fitting is "放不下就缩小半径或字号".

Plan:
1. Read topics from sample-coverage.json.
2. Rewrite wrapAxisLabel(name, maxLine):
   - Tokenize: split into tokens where a token is a run of [A-Za-z0-9] (ASCII word, may include like "3NF","BCNF","WAL","ARIES","MVCC","2PC") or a single other char.
   - Break opportunities: after "：", "与", "（", or a space (space consumed, line break there). Also treat "、" ? Spec doesn't include "、" — keep only listed.
   - Greedy wrap: accumulate tokens; width estimate: CJK/full-width char = 1 unit, ASCII = 0.55 units; line limit maxLine units. If adding token exceeds limit and current line non-empty and a break is allowed at that point... Actually simpler model: allowed break points are exactly after those chars; elsewhere must not break even if exceeds. But then overflow possible → per rule, shrink font/radius.
   
   Hmm, but old behavior also wrapped CJK text anywhere. Names like "两阶段锁与并发控制（2PC）" have 与 and （. What about e.g. "SQL 查询优化"? space exists. "索引与查询优化" has 与. Let me check real names.

Let me define algorithm:
- Preprocess: insert "\n" after "：" and "（"? No wait — break BEFORE （ (original did `（` → `\n（`). Spec says break at "（" position — either before or after? Original: replace （ with \n（, i.e. break before （. Keep that.
- Allowed break chars: after "：", after "与", before "（", at spaces.
- Then greedy wrap remaining segments: for each segment (between allowed breaks), if segment fits within line budget, add; else — if segment itself has no allowed break inside, it must go on its own line (may overflow → handle via shrink).

Simplest robust implementation: tokenize into atomic units (ASCII alnum runs = one unit; single CJK char = unit; punctuation char = unit). Break allowed after units that are "：","与" or before unit "（", and at space units (spaces removed at breaks). Greedy fill lines up to width budget (CJK=1, ASCII char=0.5, using actual counts: measure per token: cjkCount*1 + asciiCount*0.5). maxLine is CJK-equivalent budget (8 narrow, 11 wide... but budget for ASCII-half chars).

Wait but what about breaking between plain CJK chars when no 与：（? E.g. hypothetical "查询优化技术" 6 chars — fits in 8 anyway. Longest CJK run without break chars among real names? Check the names first.

If a segment exceeds budget and contains no break opportunity, we can't split it without violating rules — then fallback: put on own line; if its width exceeds chart capacity, shrink font/radius. Per spec "放不下就缩小半径或字号".

Let me now get the topic names.

Also acceptance: "每个轴标签的每一行（SVG 的 text / tspan）都在图表容器内，并且和图例不相交" — need to measure label lines vs container and vs legend element. ECharts SVG renderer: labels are text elements possibly with tspans. Each line = tspan? Need to measure each tspan's rect.

Legend at bottom 8. Chart height 340 (narrow) / 430. Center 46% vertical. Radius 46% (narrow) / 58%. Labels at radius+~... Might collide with legend at bottom for bottom axis label. We'll measure: legend is an HTML? No — legend is part of ECharts SVG too ("覆盖度" and "考试权重…" text elements). Distinguish: legend texts vs axis labels. Axis label text elements contain the topic name; legend contains "覆盖度" / "考试权重（按最大分值归一化）". We can find legend via chart DOM: legend has fill colors maybe. Simpler: measure all svg text elements in container, classify: those whose textContent matches part of a topic name = axis label lines; others (legend) = legend. Check no intersection between axis label rects and legend rects.

Implementation of measurement: get container rect; get legend rects (text elements whose content is "覆盖度" or starts with "考试权重"); axis label rects: all other text elements (excluding empty). For each axis label line (tspan), getBoundingClientRect — tspans have rects? tspan elements do have getBoundingClientRect in Chrome? Actually SVGTSpanElement doesn't support getBoundingClientRect in all browsers... In Chrome, tspan.getBoundingClientRect() works? Hmm. SVG text with multiple lines: ECharts SVG renderer creates separate <text> elements per line? I recall zrender svg text uses one text element with tspans. getBoundingClientRect on tspan — Chrome supports it (returns geometry). Let me just measure text.getBoundingClientRect() for the full label and also tspan rects; if tspan fails, fallback: use getBBox? getBBox gives local coords. Simplest: measure text element rects (whole label bounding box) for container fit; for break-point validation use the generated strings from JS side (call wrapAxisLabel logic? It's inside closure). Alternative: read each text element's child tspans textContent via DOM and validate the break rule on concatenated lines: for each line, check last char and next line's first char are not both ASCII alnum. That validates via DOM: lines = tspan list per text element.

If tspans exist per line, we can also measure each tspan via getClientRects() (Range?). Range over tspan contents → getBoundingClientRect. Let's just try tspan.getBoundingClientRect() in the evaluate; Chrome supports geometry APIs on SVG elements broadly (getBoundingClientRect is on Element, works for SVG elements including tspan in Blink? tspan is SVGTextPositioningElement... In Blink, getBoundingClientRect works for tspan, yes I believe it returns the em box.)

OK. Now algorithm details. Let me write the code:

```js
function wrapAxisLabel(name, maxLine) {
  var s = String(name == null ? "" : name);
  if (!s) return "";
  // atomic tokens: ASCII alnum runs stay whole; everything else char by char
  var tokens = s.match(/[A-Za-z0-9]+|[^A-Za-z0-9]/g) || [];
  var isAlnum = function (t) { return /^[A-Za-z0-9]+$/.test(t); };
  var widthOf = function (t) {
    var w = 0;
    for (var i = 0; i < t.length; i++)
      w += t.charCodeAt(i) < 128 ? 0.55 : 1;
    return w;
  };
  var canBreakBefore = function (tok) {
    return tok === "（";
  };
  var canBreakAfter = function (tok) {
    return tok === "：" || tok === "与" || tok === " ";
  };
  var lines = [];
  var cur = "";
  var curW = 0;
  for (var i = 0; i < tokens.length; i++) {
    var tok = tokens[i];
    var w = widthOf(tok);
    if (tok === " " && cur === "") continue; // skip leading space on new line
    // decide if a break must happen before this token
    var mustBreak = false;
    if (cur !== "" ) {
      if (canBreakBefore(tok)) mustBreak = true;
      else if (prevBreakable && curW + w > maxLine) mustBreak = true;
    }
    ...
  }
}
```

Hmm, getting complicated. Cleaner: first split s into segments at allowed break points, where a "segment" is a chunk that must stay on one line (since breaks only allowed at those points). Break positions:
- before "（"
- after "：" 
- after "与"
- at spaces (drop the space when breaking)

Then greedy: pack consecutive segments into lines while total width ≤ maxLine.

But wait: "WAL 与 ARIES": segments = ["WAL", "与 ", "ARIES"]? Break after "与" and at space. Hmm breaking after 与 AND the following space — "WAL 与" / "ARIES" (space consumed at break). Fine: segments: "WAL" (break after following space), "与" (break after)... Let me define: iterate chars, build segment; when we encounter a break opportunity, close the segment there (break char included in current segment), and if the break was at a space, the space is dropped.

"函数依赖与范式（3NF、BCNF）": segments: "函数依赖与" (break after 与), "范式" (break before （), "（3NF、BCNF）". Greedy with maxLine=8: "函数依赖与" w=5; add "范式" → 7 ≤ 8 → line "函数依赖与范式"; add "（3NF、BCNF）" w= （1)+3NF(1.65)+、1+BCNF(2.2)+）1 = 6.85 → 7+6.85=13.85 > 8 → new line "（3NF、BCNF）". Result: "函数依赖与范式\n（3NF、BCNF）". 

"隔离级别与 MVCC": segments: "隔离级别与" (break after 与... then space) — careful: "与" followed by space " MVCC": break after 与 closes segment "隔离级别与"; then space then "MVCC" — space is a break opp; segment "MVCC". Greedy: "隔离级别与"=5, + "MVCC"=2.2 → 7.2 ≤ 8 → one line "隔离级别与 MVCC"? Wait but if we join segments "隔离级别与" + " " + "MVCC" — the space between: when joining on same line we keep the space. So I need to remember the space. Hmm: "与 " — after 与 there's a space. If joined, keep "与 MVCC" with space.

Simpler token approach: tokens = ASCII-alnum runs and single chars (incl space). Allowed break BEFORE token: token is "（", or previous token was "：" or "与" or " " (space). When breaking due to a previous space, drop the space. Greedy fill by width.

```js
function wrapAxisLabel(name, maxLine) {
  var s = String(name == null ? "" : name);
  if (!s) return "";
  var tokens = s.match(/[A-Za-z0-9]+|[^A-Za-z0-9]/g) || [];
  var widthOf = function (t) {
    var w = 0;
    for (var i = 0; i < t.length; i++) w += t.charCodeAt(i) < 128 ? 0.55 : 1;
    return w;
  };
  var lines = [];
  var cur = "";
  var curW = 0;
  var prev = ""; // previous token on the current line
  var pendingSpace = false;
  for (var i = 0; i < tokens.length; i++) {
    var tok = tokens[i];
    if (tok === " ") {
      if (cur === "") continue; // no leading space
      pendingSpace = true;
      continue;
    }
    var w = widthOf(tok);
    // break opportunities: before （; after ： or 与 (i.e. prev token was those)
    var breakHere = false;
    if (cur !== "") {
      if (tok === "（") breakHere = true;
      else if (prev === "：" || prev === "与") breakHere = true;
    }
    var piece = (pendingSpace && cur !== "" ? " " : "") + tok;
    if (!breakHere && cur !== "" && curW + widthOf(piece) > maxLine) {
      // no allowed break point here; only break if we can (we can't), so let it overflow? 
    }
  }
}
```

Hmm wait — but the old behavior wrapped anywhere for CJK; the new spec restricts to those chars. What if a CJK run without break chars exceeds maxLine? E.g. "查询处理与查询优化" — has 与. Check real names; if none exceed, we can simply not break elsewhere (overflow tolerable since measured against container). But acceptance requires all lines inside container. If some segment alone is too wide at current radius/font, we shrink font/radius per spec.

Let me now look at the actual topic names.

Also: with maxLine budgets 11 (wide) / 8 (narrow) in CJK units with ASCII 0.55: check each name fits. I'll compute after seeing names.

Note chart radius: desktop 58%, narrow 46%, font 11/10. If labels need more room, spec allows shrink. Let's see how measurements go.

Also legend overlap: bottom legend at bottom:8. Bottom axis label ("索引与..." whichever is at angle 90°... order: indicators in sorted order; ECharts places first indicator at top? Actually first indicator at angle 90° (top) going clockwise. With 10 indicators, bottom-ish ones are #5/#6 (angles 90+36*5=270 bottom? indicator i at angle (90 - i*36)? whatever) — labels near bottom may approach legend. Previous 09b fixed label-in-container but not legend intersection. Now need to check. May need to reduce radius or move legend. Let's measure first.

Let me get topic names.

</details>

**Qoder：** 先看数据里的知识点名称，再改 `wrapAxisLabel` 的折行算法。

🔧 **Bash** ```bash
.cache/scratch/pwvenv/bin/python -c "
import json
d=json.load(open('site/data/sample-coverage.json'))
for t in d['topics']:
    print(repr(t['name']))
"
```

<details><summary>结果</summary>

```
'关系模型与关系代数'
'SQL 查询与视图'
'索引：B+树与哈希索引'
'函数依赖与范式（3NF、BCNF）'
'查询处理与优化'
'事务的 ACID 特性'
'并发控制：两阶段锁与死锁'
'隔离级别与 MVCC'
'故障恢复：WAL 与 ARIES'
'分布式事务与两阶段提交（2PC）'
```

</details>

<details><summary>Qoder 思考</summary>

Topic names and expected wrapping with break points only at "："、"与"、"（"、空格:

Narrow (maxLine 8 CJK units, ASCII 0.55):

1. "关系模型与关系代数" — break after 与: segments "关系模型与"(5) + "关系代数"(4). 5+4=9 > 8 → two lines: "关系模型与" / "关系代数". OK.
2. "SQL 查询与视图" — tokens: "SQL"(1.65), space, "查询与"(3, break after 与), "视图"(2). Line: "SQL 查询与" = 1.65+0.55(space? space width 0.55)+3... space as ASCII 0.55. "SQL 查询与" = 1.65+0.55+3 = 5.2; + "视图" 2 → 7.2 ≤ 8 → single line. 
3. "索引：B+树与哈希索引" — break after "：" and after "与". tokens: "索引"(2), "："(1, break after), "B"(0.55), "+"(0.55), "树"(1), "与"(1, break after), "哈希索引"(4). Greedy: "索引："=3; add "B+树" (2.1) → 5.1; add "与" → 6.1; next "哈希索引" 4 → 10.1 > 8, break after 与 allowed → line1 "索引：B+树与" (6.1), line2 "哈希索引". Note: "B+树" — B and + and 树: is breaking between "B+" and "树" allowed? Only at break chars — no. Good.
   Wait — but breaking after "与" mid-phrase: "索引：B+树与 / 哈希索引" hmm acceptable per rules.
4. "函数依赖与范式（3NF、BCNF）" → "函数依赖与范式"(7) / "（3NF、BCNF）"(6.85). Single lines each? 7 ≤ 8 ✓, second line 6.85 ✓. 
5. "查询处理与优化" — "查询处理与"(5)+"优化"(2)=7 ≤ 8 single line. 
6. "事务的 ACID 特性" — "事务的"(3) " ACID"(0.55+2.2) " 特性"(0.55+2). Total 3+2.75+2.55=8.3 > 8 → need break. Break points: at spaces. "事务的 ACID" = 5.75, + " 特性" 2.55 → 8.3 > 8 → break at space before 特性: line1 "事务的 ACID"(5.75), line2 "特性". Hmm okay. Or treat space width smaller (0.3?). Space at font 10 ≈ 0.3 em. Let me use 0.3 for space. Then "事务的 ACID 特性" = 3+0.3+2.2+0.3+2 = 7.8 ≤ 8 → single line. Nice. I'll count space as 0.3, ASCII letters/digits 0.55... Actually more accurate: ASCII chars in 11px font ≈ 6px vs CJK 11px → 0.545. Space ≈ 0.3.
7. "并发控制：两阶段锁与死锁" — "并发控制："(5) "两阶段锁与"(5) "死锁"(2). Greedy: "并发控制：" 5, +"两阶段锁与" 5 → 10 > 8 → break after "：" → line1 "并发控制：", line2 "两阶段锁与死锁" 7 ≤ 8. Two lines.
8. "隔离级别与 MVCC" — "隔离级别与"(5)+" MVCC"(0.3+2.2)=7.5 ≤ 8 single line. 
9. "故障恢复：WAL 与 ARIES" — "故障恢复："=5, + " WAL"(0.3+1.65)=6.95, + " 与"(0.3+1)=8.25 > 8 → break after 与? Wait order: tokens: "故障恢复","：","WAL",space,"与",space,"ARIES". Break opps: after ：, after 与, at spaces. Greedy: line = "故障恢复：WAL 与" = 5+0.3+1.65+0.3+1 = 8.25 > 8. Hmm — greedy adds tokens one at a time; when adding "与" would exceed? 5+0.3+1.65=6.95 (after WAL), adding " " + "与" → 8.25 > 8. Break opportunity before "与"? Space before 与 allows break at that space → line1 "故障恢复：WAL"(6.95), line2 "与 ARIES"(0.3+1+0.3+2.75=4.35). Hmm that breaks at space, keeping "与 ARIES" together. Acceptable? Break rules say break at space — yes allowed. Alternatively line1 "故障恢复：WAL 与" slightly over 8 (8.25) still fits visually? maxLine 8 was a heuristic. Two-line is fine: "故障恢复：WAL" / "与 ARIES". Hmm, a bit awkward but compliant. 

   Actually wait — with space counted 0.3: at maxLine budget — maybe I should relax: since these labels are measured against the container anyway, I can allow slight over. But greedy with hard cap produces the above. Fine.

10. "分布式事务与两阶段提交（2PC）" — tokens: "分布式事务与"(6, break after 与), "两阶段提交"(5), "（2PC）"(1+1.65+1=3.65). Break before （. Greedy: "分布式事务与"6, +"两阶段提交" → 11 > 8 → break after 与 → line1 "分布式事务与", line2 "两阶段提交（2PC）" = 8.65 > 8 but no allowed break before （? There IS break before （! So line2 could be "两阶段提交" / "（2PC）". Greedy: line2 "两阶段提交"5 then "（2PC）" would make 8.65 > 8, and break before （ allowed → line3 "（2PC）". Three lines. Or line1+... hmm "分布式事务与"(6) + nothing... three lines: "分布式事务与 / 两阶段提交 / （2PC）". Acceptable.

    Alternatively allow 8.65 on one line → two lines. The cap choice affects. With cap 8 strictly → 3 lines. That's fine for narrow.

Wide (maxLine 11): all names fit single line except maybe none? "分布式事务与两阶段提交（2PC）" = 6+5+3.65 = 14.65 > 11 → break before （: "分布式事务与两阶段提交"(11) / "（2PC）". 11 ≤ 11 ✓ exactly. "并发控制：两阶段锁与死锁" = 5+5+2=12 > 11 → break after ：: "并发控制：" 5 / "两阶段锁与死锁" 7. Or break after 与: "并发控制：两阶段锁与"(10) / "死锁". Greedy picks first fit: line1 accumulates "并发控制：两阶段锁与" = 5+5=10 ≤ 11, adding "死锁" → 12 > 11 → break after 与 (allowed) → line2 "死锁". Result "并发控制：两阶段锁与 / 死锁". Hmm okay.
   "函数依赖与范式（3NF、BCNF）" = 7 + 6.85 = 13.85 > 11 → break before （ → "函数依赖与范式" / "（3NF、BCNF）". Good.
   Others single line.

Now, how does the greedy handle "break must only happen at allowed points, but overflow when no allowed point"? E.g. "两阶段提交" alone (5) fine. All segments ≤ 8 except none. OK.

Edge: what if a token would exceed with no break allowed (cur !== "", no breakHere, curW + w > maxLine)? Then we can't break — append anyway (overflow). In our data doesn't happen.

Now, "每个换行点前后字符不能都是 ASCII 字母或数字" — our breaks are at ：与（space — none between alnum. ✓ Also breaks after "与" — 与 is CJK. Before "（" — （ is punctuation. Space breaks: between WAL and 与, between 与 and ARIES, between ACID and 特性 — none both-alnum? "故障恢复：WAL" / "与 ARIES": break at space after WAL — prev char L (alnum), next char 与 (not alnum) ✓. If break at space between two ASCII words (e.g. "SQL 查询" — S...L then space then 查 CJK) fine. There's no space between two alnum words in the names except... "B+树"? no space. OK — but in general if a space sits between two ASCII words, breaking there violates the rule. In our data: "SQL 查询"(space between L and 查 ✓), "ACID 特性" (D→特 ✓), "WAL 与"(L→与 ✓), "与 ARIES"(与→A ✓). No violation.

Wait, one more consideration: does breaking after "与" where next token is ASCII cause a line starting with ASCII? e.g. "故障恢复：WAL / 与 ARIES" no. Fine.

Also chart geometry: line count per label up to 3 lines (narrow, #10). Radius 46% of 333px/2? container 333 wide, height 340. radius 46% of min(w,h)/2 = 46% of 170 = 78px. Center y = 46% of 340 = 156. Bottom label at angle... 10 indicators, first at top (90°). Indicator positions: ECharts radar starts at 90° and goes clockwise? indicator i at angle 90° - i*36°? So i=5 at -90° (bottom) → label below center at 156 + 78 + gap + label lines... 3-line label at 10px/13px lineHeight ≈ 39px + 78 + 156 = 273 < 340-legend. Legend at bottom 8, legend height ~20 → legend top ≈ 340-8-20=312. 273 < 312 ✓ probably.

But wait — order of indicators = items order (sorted by blind_spot_score desc): t04 first, then t08, t02, t01, t05, t10, t03, t06, t07, t09. Position 5 (index 5, t10 "查询处理与优化") at bottom. Which is at bottom exactly? With 10 indicators starting top going clockwise: index 5 is at bottom. t10 = "查询处理与优化" single line narrow. Fine.

Hmm wait, actually which direction/counterclockwise doesn't matter much; bottom label is index 5 (or 4/5/6 near bottom).

Also need to verify labels don't overlap legend. Will measure.

Now also: does ECharts use the "\n" in indicator name to create multiple tspans? Yes — zrender svg text supports rich/newline via tspans. Current code already relies on \n working (09b made labels SVG texts measurable with multi-line).

Let me now rewrite wrapAxisLabel in main.js:

```js
/* break lines only at ：、与、（ and spaces; ASCII words (WAL, MVCC, 3NF...) never split */
function wrapAxisLabel(name, maxLine) {
  var s = String(name == null ? "" : name);
  if (!s) return "";
  var tokens = s.match(/[A-Za-z0-9]+|[^A-Za-z0-9]/g) || [];
  var widthOf = function (t) {
    var w = 0;
    for (var i = 0; i < t.length; i++) {
      var c = t.charAt(i);
      w += c === " " ? 0.3 : (t.charCodeAt(i) < 128 ? 0.55 : 1);
    }
    return w;
  };
  var lines = [];
  var cur = "";
  var curW = 0;
  var prevTok = "";
  for (var i = 0; i < tokens.length; i++) {
    var tok = tokens[i];
    if (tok === " ") {
      if (cur !== "") cur += " ", curW += 0.3;
      continue;
    }
    var piece = tok;
    if (cur !== "" && (tok === "（" || prevTok === "：" || prevTok === "与")) {
      lines.push(cur); cur = ""; curW = 0;
    } else if (cur !== "" && curW + widthOf(tok) > maxLine) {
      // no allowed break point here — the token stays on the line even if it
      // slightly overflows; the container measurement is the real limit
    }
    cur += piece;
    curW += widthOf(tok);
    prevTok = tok;
  }
  if (cur !== "" || lines.length === 0) lines.push(cur);
  return lines.join("\n");
}
```

Hmm wait, there's a bug: when line overflows mid-run with no break point, we keep appending (overflow allowed). But there's also the case where curW + w > maxLine AND there IS a break opportunity — but break opportunity is checked before (tok === （ or prevTok in ：与). But greedy should also break at those points only when needed OR always? If we always break at ：与（even when it fits, "SQL 查询与视图" (7.2 ≤ 8) would become "SQL 查询与 / 视图"? With always-break: after "与" → break → line1 "SQL 查询与", then "视图" → line2. That's unnecessary. Better: break only when needed (exceeds maxLine). But careful: we must break at allowed points when the line would overflow; if we check "needed" first:

```js
if (cur !== "") {
  var needBreak = curW + widthOf(tok) > maxLine;
  var allowed = tok === "（" || prevTok === "：" || prevTok === "与";
  if (needBreak && allowed) { push line; reset }
}
```

Hmm but the break should happen BEFORE the token that overflows... e.g. "函数依赖与范式（3NF、BCNF）": tokens: 函,数,依,赖,与,范,式,（,3NF,、,BCNF,）. Greedy: cur="函数依赖与范式" (7). tok="（": needBreak? 7+1=8 ≤ 8 no → append "（" curW 8. tok="3NF" 1.65 → 9.65 > 8, allowed? tok is "3NF", prevTok "（" — not in list → no break, overflow → append. Line = "函数依赖与范式（3NF、BCNF）" all on one line! Bad — we wanted break before （.

So: for "（" we should break ALWAYS (it's a strong break point — original code did too). For ： and 与: break only when needed? Or always? Consider "索引：B+树与哈希索引" wide (11): always-break-after-：gives "索引： / B+树与哈希索引"(2.1+1+4=7.1+? = "B+树与哈希索引" = 0.55*2+1+1+4=7.1) two lines. Needed-only: cur "索引：" 3 + "B+树" 2.1 + "与" 1 + "哈希索引" 4 = 10.1 ≤ 11 → single line "索引：B+树与哈希索引". Single line is better if fits.

Decision: break at allowed points only when needed (line would exceed maxLine), EXCEPT before "（" always break? If "（" fits on the line, keeping it is fine: "分布式事务与两阶段提交（2PC）" wide = 11+3.65 > 11 → needed. Actually let me make it uniform: break when needed (overflow), at allowed points (before （, after ：/与, and treat trailing space as pending). But the greedy must consider that the break decision happens when adding a token that overflows — and at that moment check whether the PREVIOUS token was an allowed break point (：/与/space) or current tok is （.

Redo algorithm with "pending break" semantics:

```js
lines = []; cur = ""; curW = 0;
for each token tok (skipping leading spaces):
  w = widthOf(tok)
  allowed = (tok === "（") || (prevTok === "：" ) || (prevTok === "与") || prevWasSpace
  if (cur !== "" && curW + w > maxLine && allowed) {
     // trim trailing space of cur
     lines.push(cur.replace(/\s+$/,"")); cur = ""; curW = 0;
     // if break was due to prevWasSpace, the space already consumed at end of cur; after trim it's gone
  }
  if (tok === " ") { if (cur !== "") { cur += " "; curW += 0.3; prevWasSpace = true; } continue; }
  ...
```

Let me restructure cleanly:

```js
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
  var prevTok = "";
  var prevSpace = false;
  tokens.forEach(function (tok) {
    if (tok === " ") {
      if (cur !== "") { cur += " "; curW += 0.3; }
      prevSpace = true;
      return;
    }
    var w = widthOf(tok);
    var allowed = tok === "（" || prevTok === "：" || prevTok === "与" || prevSpace;
    if (cur !== "" && curW + w > maxLine && allowed) {
      lines.push(cur.replace(/ $/, ""));
      cur = "";
      curW = 0;
    }
    cur += tok;
    curW += w;
    prevTok = tok;
    prevSpace = false;
  });
  if (cur !== "" || lines.length === 0) lines.push(cur);
  return lines.join("\n");
}
```

Check "函数依赖与范式（3NF、BCNF）" narrow (8): tokens: 函(1)...: cur grows "函数依赖与范式"=7. tok "（": w=1; allowed (tok==="（") true; curW+w=8 > 8? No, 8 > 8 false → no break, append → cur "函数依赖与范式（" = 8. tok "3NF": w=1.65; allowed? prevTok "（" not in list, prevSpace false → not allowed → no break (even though 9.65 > 8) → append. Continue... whole label one line "函数依赖与范式（3NF、BCNF）" width 13.85. BAD.

Hmm. The issue: "（" should force break when the combined thing won't fit — i.e., break before （ if cur + "（...）" would exceed. Better: always break before "（" (like original did). That handles it: cur "函数依赖与范式" pushed; new line "（3NF、BCNF）" 6.85 ≤ 8 ✓.

Check "分布式事务与两阶段提交（2PC）" narrow: always break before （ → line1 "分布式事务与两阶段提交" = 11 > 8 — during accumulation: at some token it exceeds with no allowed break... tokens: 分(1)...分布式事务与 = 6; tok 两: w 1, curW+1=7 ≤ 8 append; 阶: 8 ≤ 8 append (curW=8); 段: 9 > 8, allowed? prevTok "阶" no → no break → append (overflow). ... line1 = "分布式事务与两阶段提交" (11, overflow). Then tok "（": always break → line2 "（2PC）". So line1 overflows budget by 3 CJK chars. Visually: line width ≈ 11 × 10px = 110px vs budget 80px. Chart narrow 333px wide, radius 46% → labels at side edges... For side labels (index 2/7 at left/right), width 110px might still fit in 333px container? The label at right side: starts at center+radius+offset ≈ 166+78+5 = 249, +110 = 359 > 333 — OUT of container! Problem.

But wait — would overflow actually happen? Which position is "分布式事务与两阶段提交（2PC）"? It's t09, sorted last (blind 0.00, tie by topic_id: t03,t06,t07,t09 all 0). Order: t04,t08,t02,t01,t05,t10,t03,t06,t07,t09 → index 9. Angle: index 9 near top-left. Label anchored right-aligned (left side labels are right-aligned toward axis). Top-left label: might collide with top label or go off left edge: width 110px, left position ≈ 166-78-5-110 = -27 → out of container!

So for this name at narrow width we need break after "与" too: "分布式事务与 / 两阶段提交 / （2PC）". With "break when needed at allowed points" — during accumulation at tok "两" (after 与): cur "分布式事务与"=6, adding 两 → 7 ≤ 8 no break needed... the break happens only when overflow occurs, i.e. at "段" (9>8) where not allowed. The greedy looks one token too late: it should have broken at the last allowed point BEFORE overflow.

Classic greedy wrapping: when token doesn't fit, break at last allowed position (or if none, hard overflow). Implement: track last allowed break position (index in cur / curW at that point). When curW + w > maxLine and no more... Actually simpler: when adding a token that overflows and there exists a recorded allowed break point in the current line, backtrack: split cur at that point.

Backtrack approach:
- maintain cur string, curW.
- maintain mark: {pos: index in cur string after which a break is allowed, w: curW at that pos} — the LAST allowed break point (after ：/与/space-consumed, or before... "before （" is handled by tok check).
- when adding tok: if cur !== "" && curW + w > maxLine:
  - if tok === "（" (allowed before) → break: push cur, reset.
  - else if mark exists → push cur.slice(0, mark.pos) (trim trailing space), cur = cur.slice(mark.pos) (trim leading space) + tok... hmm mark.pos after space already trimmed? Let me store mark.pos as position AFTER trimming trailing space.
  - else → hard append (overflow).
- after appending tok, update mark: if tok is "：" or "与" → mark = end of cur (with trailing space trimmed at break time...). If tok is " " → mark = position after trimming that trailing space... i.e. mark.pos = cur.length - 1 (excluding the space). Hmm, if later tokens appended after the space, breaking at the space means the later content goes to next line without the space.

Let me define mark.pos = length of cur with trailing whitespace trimmed (break here → next line starts after). When tok "：" or "与" appended: mark.pos = cur.length (no trailing space yet). When a space appended: mark.pos = cur.length - 1 (trim the space). Subsequent appends don't change mark.

Break action: head = cur.slice(0, mark.pos); tail = cur.slice(mark.pos); tail = tail.replace(/^ /, ""); push head; cur = tail; recompute curW = widthOf(cur); mark = null (or keep? after breaking, tail may itself contain another allowed point — e.g. tail "与 ARIES"... mark could persist but simpler null).

Also for tok === "（": break before it always? Only when needed (curW+1 > maxLine) or always? For "函数依赖与范式（3NF、BCNF）": at tok "（", curW=7, 7+1=8 not > 8 → no break → then "3NF" overflows (9.65) with mark? mark after "与" was set: mark.pos = 5 ("函数依赖与"). At "3NF": overflow, tok not （, mark exists → break at mark: push "函数依赖与", cur = "范式" + "3NF"... wait cur was "函数依赖与范式（", mark.pos=5 → head "函数依赖与", tail "范式（" + append "3NF" → cur "范式（3NF"... continues "范式（3NF、BCNF）" = 7.85... then final line "范式（3NF、BCNF）". Result: "函数依赖与 / 范式（3NF、BCNF）". Both ≤ 8 ✓. Break point between 与 and 范 — fine (not both alnum).

Hmm but semantically nicer would be "函数依赖与范式 / （3NF、BCNF）". Either is acceptable per the stated rules (break only at ：与（space). "函数依赖与 / 范式（3NF、BCNF）" — breaks after 与. OK.

Alternatively make "（" ALWAYS break (strong preference): "函数依赖与范式" / "（3NF、BCNF）" nicer. And for t09: at "（", cur "分布式事务与两阶段提交" (11, already overflowing since "段")... always-break-before-（: push line1 (11 wide, overflows container?) — still the earlier problem: line1 overflowed because no allowed break was used earlier. With backtrack algorithm, the overflow at "段" would have triggered backtrack to mark (after "与" at pos 6): push "分布式事务与", cur = "两阶段提交" then continue: "（" always break → push "两阶段提交", line3 "（2PC）". 

So: always break before "（" + backtrack at last allowed point on overflow. Let me verify all names narrow (maxLine 8):

1. "关系模型与关系代数": tokens up to 与: mark at 5 ("关系模型与"). Continue: 代(6)... cur "关系模型与关系代数"=9: at tok "数"? Let's trace: cur builds 关(1)系(2)模(3)型(4)与(5) mark=5. 关(6)系(7)代(8) — at "代" curW was 7, +1=8 not >8 → append (8). 数: 8+1=9 > 8, tok not （, mark=5 → backtrack: push "关系模型与", cur = "关系代" + "数" = "关系代数". Final: "关系模型与 / 关系代数" ✓.

2. "SQL 查询与视图": SQL(1.65) mark? tok SQL not ：/与; space → mark at pos 3 (cur "SQL" length 3, space makes cur "SQL " len 4, mark.pos=3). 查(1+...) cur "SQL 查询与" = 1.65+0.3+3 = 4.95, mark after 与 = 5 chars... cur.length=6 ("SQL 查询与"), mark.pos=6. 视: 4.95+1=5.95 ≤ 8 append. 图: 6.95 ≤ 8. Single line "SQL 查询与视图" ✓.

3. "索引：B+树与哈希索引" narrow: 索(1)引(2)：(3) mark=3. B(3.55)+(4.1)树(5.1)与(6.1) mark=6 ("索引：B+树与" length 6? cur="索引：B+树与" length 7 chars? 索,引,：,B,+,树,与 = 7 chars, width 2+1+0.55+0.55+1+1=6.1; mark.pos=7). 哈: 6.1+1=7.1 ≤8. 引(8.1)>8 → backtrack mark 7: push "索引：B+树与", cur "哈" + continue 引 索引 → line2 "哈希索引". Result: "索引：B+树与 / 哈希索引". Break after 与 ✓. Hmm "哈希索引" 4 wide fine.

4. "函数依赖与范式（3NF、BCNF）": traced above with always-break-before-（: at "（" cur="函数依赖与范式" (7) → push, line2 "（3NF、BCNF）" 6.85 ✓. Result 2 lines ✓.

5. "查询处理与优化": 查(1)...处(2)理(3)与(4) mark=4. 优(5)化(6) ≤ 8 single line ✓.

6. "事务的 ACID 特性": 事(1)务(2)的(3) space → mark=3 (cur "事务的 " len 4, mark.pos=3). A(3.55)C(4.1)I(4.65)D(5.2) space → cur "事务的 ACID " mark.pos=9 (len 10 -1). 特(6.2... 5.2+0.3+1=6.5)性(7.5) ≤ 8 → single line "事务的 ACID 特性" ✓ (width 7.5).

7. "并发控制：两阶段锁与死锁" narrow: 并(1)发(2)控(3)制(4)：(5) mark=5. 两(6)阶(7)段(8)锁(9>8!) — at 锁: curW 8 (并发控制：两阶段 = 5+3=8), +1=9 > 8, mark=5 → backtrack: push "并发控制：", cur "两阶段" + "锁" = "两阶段锁"(4) 与(5) mark=5. 死(6)锁(7) ≤ 8. line2 "两阶段锁与死锁" ✓. Result 2 lines.

8. "隔离级别与 MVCC": 隔离级别与(5) mark=5. space → cur "隔离级别与 " mark.pos=5. M(6.1)V(7.2)C(7.75)C(8.3>8!) — at second C: curW = 6.1+... let me recount: after space cur="隔离级别与 " w=5.3. M: 5.3+0.55=5.85, V 6.4, C 6.95, C 7.5. All ≤ 8. Single line "隔离级别与 MVCC" (7.5) ✓.

9. "故障恢复：WAL 与 ARIES" narrow: 故障恢复：(5) mark=5. space? No: "WAL" token (alnum run) — wait tokenization: "WAL" is one token [A-Za-z0-9]+. cur "故障恢复：" + "WAL" = 5+1.65=6.65 ≤ 8. space → mark.pos = cur.length ("故障恢复：WAL" len 8). cur "故障恢复：WAL " 6.95. 与: 7.95 ≤ 8 append; mark after 与 = cur.length ("故障恢复：WAL 与" len 10). space → mark.pos 10... wait mark after space: cur "故障恢复：WAL 与 " len 11, mark.pos=10 (trim space). ARIES token w=2.75: curW 8.25+2.75... curW now = 7.95+0.3=8.25. +2.75 = 11 > 8 → backtrack to mark.pos=10: head = "故障恢复：WAL 与", cur = "ARIES". Push "故障恢复：WAL 与" (width 7.95 ≤ 8 ✓), line2 "ARIES" ✓. Break between 与 and ARIES — 与 not alnum ✓. 

10. "分布式事务与两阶段提交（2PC）": traced: line1 "分布式事务与" (6), then 两(7) 阶(8) 段(9>8) backtrack mark=6 → push "分布式事务与", cur "两阶段"... wait at 段: cur was "两阶段" w=3, +1=4 ≤ 8 — hold on, after backtrack cur resets to "两" then re-append 段? Let me re-trace: cur "分布式事务与" (6), mark=6. 两: 6+1=7 ≤ 8 → cur "分布式事务与两" (7). 阶: 8 ≤ 8 → cur 8. 段: 9 > 8 → backtrack mark 6: push "分布式事务与", cur = "两阶段" (slice from 6) + "段" → "两阶段段"?? 

    BUG: backtrack gives cur = "两阶段" but the current token 段 hasn't been appended yet — I push head, cur = tail ("两阶段"), then append tok "段" → "两阶段段"? No wait — cur at overflow time is "分布式事务与两阶段" (9 chars incl 两阶段). mark.pos=6. tail = cur.slice(6) = "两阶段". Then append tok "段" → "两阶段段"?? NO — tok is "段" and cur tail is "两阶段" which already contains... wait cur = "分布式事务与两阶段" — 分,布,式,事,务,与,两,阶,段 = 9 chars. The token being added is "提" (提 has not been added). Let me redo: tokens: 分 布 式 事 务 与 | 两 阶 段 提 交 | （ 2PC ）. cur accumulates: after 与: "分布式事务与" (6) mark=6. 两: 7. 阶: 8. 段: curW 8, +1=9 > 8 → backtrack: push "分布式事务与", cur = "两阶段" wait cur was "分布式事务与两阶段"? No — at the point of processing tok 段, cur = "分布式事务与两阶" (8 chars, w 8). mark.pos=6. tail = cur.slice(6) = "两阶". Append tok 段 → cur "两阶段" (3). 提: 4. 交: 5. （: always break → push "两阶段提交", cur "（" ... 2PC(1.65) 、(1) BCNF... no ）: "（2PC）" = 3.65. Final lines: "分布式事务与 / 两阶段提交 / （2PC）" ✓ 

    I made an arithmetic slip above; correct: at tok 段, cur="分布式事务与两阶" (w=8). tail="两阶", +段 → "两阶段". Good, no duplication.

    Always-break-before-（: at tok "（", cur = "两阶段提交" (5). Break → push "两阶段提交", cur = "（". ✓

So the algorithm: always break before "（"; on overflow, backtrack to last allowed break (after ：/与/space); else hard overflow.

Hmm wait, for case 4 I want to double check "always break before （" when cur is empty? cur="" then no push of empty. Fine.

Also should mark persist after backtrack? tail might contain another allowed point (e.g. tail "与 ARIES"). After backtrack, set mark=null but as tokens continue, new marks get set. For tail "两阶段提交" no marks. Edge: after backtrack the tail + more tokens may overflow again with a mark inside the tail? mark was set on the ORIGINAL cur — positions past mark.pos are in tail; e.g. cur "A 与 B 与 C"... marks: after first 与 pos, then after second 与 later pos. Last mark = second. If overflow at C: backtrack at second mark: head "A 与 B", tail... wait cur was "A 与 B 与" hmm getting complicated. Setting mark=null after backtrack is safe (later marks will be recorded as tokens append). Slight suboptimality acceptable.

One more: "always break before （" — what about "（3NF、BCNF）" as the whole first content (cur empty)? No break, fine.

Now widths: space 0.3, ASCII 0.55, else 1. maxLine: narrow 8, wide 11. Check wide (11) results:

1. "关系模型与关系代数" 9 ≤ 11 single ✓
2. "SQL 查询与视图" ~7.2 single ✓
3. "索引：B+树与哈希索引" 10.1 ≤ 11 single ✓
4. "函数依赖与范式（3NF、BCNF）": at （ always break → "函数依赖与范式"(7) / "（3NF、BCNF）"(6.85) ✓ 2 lines
5. "查询处理与优化" 7 single ✓
6. "事务的 ACID 特性" 8.25 single ✓
7. "并发控制：两阶段锁与死锁": 并发控制：5, 两阶段锁与 10 (mark at 10), 死 11 ≤ 11, 锁 12 > 11 → backtrack mark 10: push "并发控制：两阶段锁与", cur "锁"... wait tok is 锁, cur = "并发控制：两阶段锁与死" (11). mark.pos=10 ("...与"). tail = "死". append 锁 → "死锁". Result: "并发控制：两阶段锁与 / 死锁". Hmm — line1 "并发控制：两阶段锁与" = 10 ≤ 11 ✓, line2 "死锁". Acceptable but a bit ugly ("与" dangling). Alternative: prefer earlier mark? Standard greedy takes last. Could prefer breaking after "：" (mark 5) giving "并发控制： / 两阶段锁与死锁"(7) — nicer. But greedy-with-last-mark gives the ugly one. Either complies with rules. Hmm. I could make marks prioritized: prefer the earliest mark that lets the tail fit? Complex. 

    Alternative approach: instead of last-mark backtrack, iterate: when overflow, choose break at the last allowed point such that... ugh.

    Actually simpler tweak: when overflow occurs and mark exists, backtrack; but then also check if head is much longer... no. Keep it simple; both comply. But visual quality matters for review. "并发控制：两阶段锁与 / 死锁" — the dangling 与 at end of line looks odd in Chinese. Whereas breaking after ：looks natural. Hmm.

    Option: treat "：" as ALWAYS break (strong break, like （). Then #7: "并发控制：" / "两阶段锁与死锁"(7) — nice. And #3 "索引：B+树与哈希索引" would become "索引： / B+树与哈希索引"(7.1) 2 lines at wide — previously single. Hmm at wide that's unnecessary split. But is it bad? It's consistent & clean. At narrow also 2 lines either way.

    With always-break after "：" AND before "（", results:
    - #3 wide: "索引：" / "B+树与哈希索引" (2 lines instead of 1). Slightly more split than needed but fine.
    - #9 wide: "故障恢复：" / "WAL 与 ARIES" (5 / 4.3). Nice!
    - #7: "并发控制：" / "两阶段锁与死锁". Nice.
    
    I think always-break at ： and （, need-break (backtrack) at 与/space is a good balance. Let me finalize:

    Rules: 
    - tok "：" → append, then mark forced-break-after (always).
    - tok "（" → always break before it.
    - overflow → backtrack to last soft mark (after 与 or space) if exists; else hard overflow.

    Verify #9 narrow with always-break after ：: "故障恢复：" pushed at ：? No — always break happens when NEXT token arrives: at tok "WAL", check prevTok === "：" → break: push "故障恢复：", cur "WAL". Then space mark, "与" append (mark after 与), space mark, "ARIES": curW "WAL 与 " = 1.65+0.3+1+0.3=3.25 + 2.75 = 6 ≤ 8 → single line "WAL 与 ARIES". Result: "故障恢复： / WAL 与 ARIES" ✓ nice.

    #6 "事务的 ACID 特性" narrow: single line 7.5 ✓ (no ：).

    #2 "SQL 查询与视图": single line ✓.

    #1 "关系模型与关系代数" narrow: backtrack → "关系模型与 / 关系代数" ✓.

Now labels count lines: narrow: #1:2, #2:1, #3:2, #4:2, #5:1, #6:1, #7:2, #8:1, #9:2, #10:3. Fine.

Now ECharts axisName lineHeight 13 (narrow)/15 (wide), fontSize 10/11. Container 333×340 narrow. Multi-line label height e.g. 3 lines = 39px + gap. Top label (index 0 = t04, 2 lines): chart center y 46% = 156.4, radius 46% of min(333,340)/2 = 0.46*166.5 = 76.6. Top label starts at 156-76.6-~30(3-line?)... t04 2 lines 26px → label top ≈ 156-77-5-26 = 48 > 0 ✓. Bottom label index 5 = t10 "查询处理与优化" 1 line: 156+77+5+13 = 251 < legend top ~312 ✓.

Side labels: index 2/7 (t01, t06) and 3/6... angles: 10 indicators: positions 0..9 at 90°, 54°, 18°, -18°, -54°, -90°, -126°, -162°, 162°, 126° (or mirrored). Left/right edge labels: index 2 (18°, upper right), index 3 (-18° lower right), 7 (-162° left), 8 (162° upper left). The widest single-line labels: #3 "索引：B+树与哈希索引"→ wait #3 sorted position? sorted order: t04(0), t08(1), t02(2), t01(3), t05(4), t10(5), t03(6), t06(7), t07(8), t09(9).

- index 2 = t08 "隔离级别与 MVCC" (7.5 wide, 1 line)
- index 3 = t02 "SQL 查询与视图" (1 line)
- index 7 = t06 "关系模型与关系代数" narrow → 2 lines
- index 8 = t07 "并发控制：两阶段锁与死锁" → 2 lines "并发控制：" / "两阶段锁与死锁"
- index 9 = t09 "分布式事务与 / 两阶段提交 / （2PC）" 3 lines
- index 0 = t04 top "函数依赖与范式" / "（3NF、BCNF）"
- index 5 = t10 bottom.

Right side labels (index 2, 3) anchored left at x = center + r*cos + gap: 166+76.6*cos(18°)+~8 ≈ 166+72.9+8 = 247; label width "隔离级别与 MVCC" ≈ 7.5*10 = 75px → right edge 322 < 333 ✓ barely (11px margin). "SQL 查询与视图" 7.2*10=72 → 319 ✓.

Left side (index 7, 8, 9): right-aligned ending at 166-72.9-8 = 85; width "两阶段锁与死锁" 7*10=70 → left edge 15 ✓. index 8 at 162°: x = 166+76.6*cos(162°)... cos162 = -0.95 → 166-72.9 = 93, minus gap 8 → right edge 85, width 70 → left 15 ✓. index 9 at 126°: cos=-0.588 → 166-45=121-8=113 right edge; widest line "两阶段提交" 5*10=50 → left 63 ✓.

Legend: legend at bottom with 2 items ("覆盖度", "考试权重（按最大分值归一化）") — might wrap? At 333 width, legend items total ≈ "覆盖度"(3*12=36+icon 25) + "考试权重（按最大分值归一化）" (14 chars*12=168+25) ≈ 254 < 333 fits one row.

Bottom label (index 5, t10, y=156+77+8+13=254) vs legend top (340-8-~20=312) ✓ no overlap.

So probably no radius/font shrink needed. If measurements show overlap, adjust.

Also — the acceptance requires "每个轴标签的每一行（SVG 的 text / tspan）都在图表容器内" — measure per line. I'll measure text elements and their tspans via getBoundingClientRect (tspan supports it in Chrome? Let me test; if not, use getBBox + transform... I'll try tspan.getBoundingClientRect() and fallback).

Hmm — actually how does zrender SVG render multi-line text? It may create multiple <text> elements (one per line) OR tspans. The 09b measurement counted "24 text elements" on mobile vs 17 desktop — 10 axis labels + legend(2) + ... 17 desktop = 10 labels + 2 legend + 5? Hmm whatever. Mobile 24 vs desktop 17: difference 7 — maybe multi-line labels become separate text elements. If each line is its own <text>, easier: measure all text rects; axis label lines = those matching topic-name fragments.

Plan for measurement script:
1. Load page at each width.
2. In container, collect all svg text elements; for each: rect + textContent.
3. Classify legend: textContent === "覆盖度" or startsWith("考试权重"). Axis labels: others with non-empty text.
4. Check each axis-label line rect within container rect (±1px).
5. Check no intersection between any axis-label rect and any legend rect (also legend icon rects? legend text only, and legend group... measure legend text rects expanded by ~25px left for icon? Simpler: check axis label rects don't intersect legend text rects inflated by 30px left/right margin).
6. Break-point validation: for each topic name, compute expected lines in Python (reimplement the algorithm) OR read from DOM: group text elements by axis label? Each multi-line label = multiple text elements at nearly same x/y — hard to group from DOM alone. Alternative: replicate the algorithm in Python for verification and assert DOM lines match? Overkill. Better: validate break rule directly on DOM: for each pair of adjacent text elements belonging to the same axis label... 

   How does ECharts SVG render multi-line axis names — separate <text> per line with dy? Let me inspect the DOM structure first, then decide grouping (e.g., tspan children of one text). If tspans: group = text element, lines = tspans; validate each adjacent tspan pair: last char of line i and first char of line i+1 not both alnum.

   If separate text elements: group by proximity? Alternatively evaluate in browser: echarts chart instance accessible? We could get chart via echarts.getInstanceByDom(el) and read option indicators' names (with \n), split to lines — that's authoritative. Then find corresponding DOM texts for measurement... mapping lines to DOM text elements by textContent equality (each line's text should match a DOM text element's content, possibly with spaces trimmed).

   Plan: in browser JS:
   ```js
   const el = document.getElementById('radar-chart');
   const chart = echarts.getInstanceByDom(el);
   const names = chart.getOption().radar[0].indicator.map(i => i.name); // with \n
   ```
   Then for each name, lines = name.split("\n"). For each line, find matching text element(s) in container (textContent.trim() === line.trim()) → rect. Check in container & no legend overlap. And validate break rule on adjacent lines.

   Edge: two different labels could share identical line text — not in our data.

   Legend texts: "覆盖度" and "考试权重（按最大分值归一化）" — get legend rect from option? Just classify DOM texts not matching any line as other (legend etc.), use their rects for overlap check. Legend also includes color icons (svg path/circle) — check overlap with all non-label svg elements that are in legend area... simpler: compute legend bounding: texts "覆盖度"/"考试权重…" rects, inflate horizontally by 30px, treat as legend zone; check label rects don't intersect.

Good. Also acceptance: "列出每个知识点名称换行后的各行" — I'll print the lines per topic in the report and into DEVLOG.

Also keep 09b checks passing (labels in container etc.) — the new check subsumes.

Implementation changes to main.js wrapAxisLabel. Also per spec "放不下就缩小半径或字号" — if measurements fail, adjust radius/fontSize. Let's implement and measure.

Also note: the current wrapAxisLabel is also used... only for radar indicators. OK.

Write new wrapAxisLabel:

```js
/* axis labels wrap only at ：、与、（ and spaces; ASCII words like WAL / MVCC /
   3NF are never split. Overflow beyond an allowed break point backtracks to the
   last soft break (after 与 or a space); ： and （ are hard breaks. */
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
  var mark = -1; // index in cur where a soft break (after 与 / space) is allowed
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
      } // else: no allowed break point — keep on the line (overflow measured against the container)
    }
    cur += tok;
    curW += w;
    if (tok === "：" || tok === "与") mark = cur.length;
    prevTok = tok;
  });
  if (cur !== "" || lines.length === 0) lines.push(cur);
  return lines.join("\n");
}
```

Wait — hard break "before （" and "after ：" implemented as: when tok is （ or prevTok is ： → push cur and start fresh. But hard break should happen even if line fits — yes that's what this does. Hmm — but hard break after ：always? "索引：B+树与哈希索引" desktop: "索引：" / "B+树与哈希索引". OK as decided.

Hmm, wait: hard-break after "：" only when next token arrives; if ： is last token, cur pushed at end anyway.

Edge in overflow branch: `else if` — if hard break triggered, overflow irrelevant since line reset. If overflow and mark>0 → backtrack. After backtrack, cur = tail; then append tok. Note tail could be "" after trimming (mark == cur.length when mark set right after 与 with no space... cur.slice(mark) = "" → cur becomes tok alone. Fine. mark>0 check: mark could be 0? cur non-empty means mark ≥ 1 when set after 与 (cur length ≥1). After space: cur.length-1 could be 0 if cur was just " "? cur starts non-empty before space added, so ≥1. OK.

Also `mark = cur.length` after ：/与 — but if later a hard break pushed cur and reset, mark=-1 ✓.

One issue: after backtrack (mark=-1), subsequent tokens can set new marks. Fine.

Also `prevTok` after space tokens: space returns early without updating prevTok — so prevTok stays the last non-space token. For "WAL 与": prevTok="WAL" when 与 appended; then space; then "ARIES": prevTok="与" → hard break?? BUG: "与" is not "：" so no. prevTok === "：" only. OK. But what about "故障恢复：WAL 与 ARIES": tokens: ...：(prevTok=：) then WAL → hard break (prevTok===：) ✓. Then 与 appended (mark set). Then space (mark updated to len-1). Then ARIES: prevTok="与" — not ：, tok not （. Overflow? curW("WAL ")=1.95... wait cur="WAL 与 " hmm: after hard break cur="WAL"; space → cur "WAL " mark=3; tok 与 → cur "WAL 与" mark=5 wait mark=cur.length=5? "WAL 与" is W,A,L,space,与 = 5 chars → mark=5. Then space → cur "WAL 与 " (6), mark=5. Then ARIES w=2.75: curW = 1.65+0.3+1+0.3 = 3.25; 3.25+2.75=6 ≤ 8 → append. cur "WAL 与 ARIES" ✓ single line.

Narrow maxLine for ASCII: "WAL 与 ARIES" 6.0 ✓.

Now also double-check #7 wide with hard-break after ：: "并发控制：" (5) pushed when 两 arrives. Then "两阶段锁与死锁" = 7 ≤ 11 single ✓. Narrow: "两阶段锁与死锁" 7 ≤ 8 ✓. 

#3 narrow: "索引：" hard break at B → line1 "索引："; then "B+树与哈希索引": B(0.55)+(0.55)树(1)与(1) mark at "B+树与"=3.1... 哈 4.1, 引 5.1, 索 6.1, 引 7.1 ≤ 8 single line "B+树与哈希索引" ✓ 2 lines total.

#10 wide: "分布式事务与两阶段提交（2PC）": at 与 mark=6; continue to （: hard break → line1 "分布式事务与两阶段提交" (11 ≤ 11 ✓), line2 "（2PC）" ✓.

#4 wide: hard break at （ → "函数依赖与范式"(7) / "（3NF、BCNF）" ✓.

#9 wide: "故障恢复：" break → "WAL 与 ARIES" (4.3) single ✓.

All good. Now what about desktop maxLine=11 and #10 line1 = 11 exactly ≤ 11 ✓.

Also single "2PC" etc never split ✓.

One more consideration — should the hard break after "：" also apply... what if label is "并发控制：两阶段锁与死锁" and AFTER hard break the remaining still overflows → backtrack at 与 mark etc. Covered.

Now also update chart geometry? Keep radius/font as is (58%/46%, 11/10). Measure; adjust if needed.

Now also `wrapAxisLabel` signature unchanged. maxLine semantics changed to width-budget. Fine.

Write the check script (radar_check_09c2.py or extend check_09c? The instruction: "结果补进 DEVLOG 会话 09c 一节" — I'll write a new script .cache/scratch/check_09c_radar.py and append results to DEVLOG 09c section as an additional subsection (e.g. "### F. 追加修复：雷达轴标签折行（同日第二轮反馈）"). Also take screenshots site-09c-desktop.png? New names: site-09c2-desktop.png / site-09c2-mobile.png, and Read them.

Let me implement.

</details>

**Qoder：** 原因明确：`wrapAxisLabel` 按固定字数硬折行，会拆开英文缩写。我把它改成只在"："、"与"、"（"、空格处换行，ASCII 单词/缩写作为不可拆的整体，超宽时回退到上一个合法断点。

🔧 **Edit** `site/assets/main.js`（替换 365 → 1582 字符）

<details><summary>结果</summary>

```
Successfully modified file: /Users/wanderer/Project/oceanbase/powercontext-camp/.camp/wt/eco-qoder-site/qoder/site/assets/main.js (1 replacements).
```

</details>

<details><summary>Qoder 思考</summary>

Now start the server and write the radar check script. Measurement plan (in-browser):

```js
const el = document.getElementById('radar-chart');
const chart = echarts.getInstanceByDom(el);
const inds = chart.getOption().radar[0].indicator;
const names = inds.map(i => i.name);
```
For each name: lines = name.split("\n"). For each line: find matching svg text element in container with textContent === line (or trimmed). Get rect. Check inside container rect (±1). Legend: find text elements with content "覆盖度" or starting "考试权重" → rects; check no intersection with label line rects (with a small horizontal inflation for the icon).

Note: multi-line rendering — does zrender svg put each line in its own <text>? Whatever, matching by content works either way (tspan has textContent too; if lines are tspans inside a text, tspan.getBoundingClientRect works in Chrome I think; query 'svg text, svg tspan'? I'll query both and use whichever elements match the line text).

Break rule: for adjacent lines, last char of prev, first char of next — not both [A-Za-z0-9].

Also list all lines per topic for DEVLOG.

Overlap with legend: rect intersection test with legend text rects inflated 30px horizontally and 6px vertically.

Also verify general container-fit of ALL svg texts (09b check).

Also confirm no abbreviation is split — implied by the break rule check.

Screenshot both widths, then Read.

Start server first.

</details>

🔧 **Bash** ```bash
.cache/scratch/pwvenv/bin/python -m http.server 18808 --directory site
```

<details><summary>结果</summary>

```
Command running in background with ID: bapgbg0co. Output is being written to: /var/folders/lg/918d_j1j5n1382m1p_zljygr0000gn/T/qoder-cli-cn-501/-Users-wanderer-Project-oceanbase-powercontext-camp--camp-wt-eco-qoder-site-qoder/a9dea624-193c-4651-9bff-b0cd2223f98d/tasks/bapgbg0co.output You will be notified when it completes. To check interim output, use Read on that file path.
```

</details>

🔧 **Write** `.cache/scratch/check_09c_radar.py`（写入 5274 字符）

<details><summary>结果</summary>

```
File created successfully at: /Users/wanderer/Project/oceanbase/powercontext-camp/.camp/wt/eco-qoder-site/qoder/.cache/scratch/check_09c_radar.py The file state is current in your context; no need to read it back.
```

</details>

🔧 **Bash** ```bash
.cache/scratch/pwvenv/bin/python .cache/scratch/check_09c_radar.py
```

<details><summary>结果</summary>

```
{
  "desktop_1440": {
    "container": {
      "left": 210,
      "right": 719.109375,
      "top": 3663.625,
      "bottom": 4093.625
    },
    "labels": [
      {
        "name": "函数依赖与范式 / （3NF、BCNF）",
        "lines": [
          {
            "line": "函数依赖与范式",
            "found": true,
            "left": 426,
            "right": 503,
            "top": 3692,
            "bottom": 3708
          },
          {
            "line": "（3NF、BCNF）",
            "found": true,
            "left": 423,
            "right": 506,
            "top": 3707,
            "bottom": 3723
          }
        ]
      },
      {
        "name": "隔离级别与 MVCC",
        "lines": [
          {
            "line": "隔离级别与 MVCC",
            "found": true,
            "left": 291,
            "right": 383,
            "top": 3741,
            "bottom": 3757
… （共 421 行，此处省略 381 行，完整内容见 .jsonl）
```

</details>

<details><summary>Qoder 思考</summary>

All passed, both widths:

- No label line out of container; all svg texts fit (09b check preserved).
- No legend overlap (bottom label "查询处理与优化" bottom 6046 vs legend top 6118 — 72px clear on mobile; desktop 4031 vs 4064 — 33px clear... wait desktop bottom label t09 "（2PC）" bottom 4031 vs legend top 4064.125, 33px gap ✓).
- No bad breaks (no break between two ASCII alnum chars).
- Abbreviations intact: WAL 与 ARIES, 隔离级别与 MVCC, （3NF、BCNF）, （2PC）, ACID, B+树.

Hmm one observation: mobile "事务的 ACID 特性" right edge 355 = container right exactly (355). In bounds (±1). Fine.

Wait — one thing to double check: the break rule validation only checked adjacent lines within a label. Also "any 换行点" — the break points we create are all at ：/（/与/space. Verified: bad_breaks empty means no adjacent alnum-alnum. ✓

Now screenshots: taken (site-09c2-desktop.png, site-09c2-mobile.png). Read them (expect unreliable descriptions again; must look and record).

Then re-run the full 09c check to ensure no regressions (check_09c.py) — quick since it covers everything. Then update DEVLOG with a new subsection in 09c, stop server.

</details>

**Qoder：** 两宽度全部通过：0 越界、0 图例相交、0 非法断点；缩写完整（WAL 与 ARIES、隔离级别与 MVCC、（3NF、BCNF）、（2PC）、ACID、B+树）。跑一遍完整 09c 回归，再看截图。

🔧 **Bash** ```bash
.cache/scratch/pwvenv/bin/python .cache/scratch/check_09c.py 2>&1 | tail -5
```

<details><summary>结果（出错）</summary>

```
Error: Allow Bash to run: .cache/scratch/pwvenv/bin/python .cache/scratch/check_09c.py 2>&1 | tail -5?
```

</details>

🔧 **Bash** ```bash
.cache/scratch/pwvenv/bin/python .cache/scratch/check_09c.py
```

<details><summary>结果</summary>

```
{
  "desktop_1440": {
    "scrollWidth": [
      1440,
      1440
    ],
    "scrollWidth_overflow": 0,
    "radar_labels": {
      "count": 17,
      "out_of_bounds": []
    },
    "backticks": {
      "raw_backticks": 0,
      "code_count": 16,
      "code_samples": [
        "--allowed-tools",
        "usage.credits",
        "duration_ms",
        "get_latest()",
        "scripts/e2e_verify.py",
        "docs/VALIDATION.md"
      ]
    },
    "sessions_totals": {
      "rows": "17",
      "turns": "1143",
      "credits": "3974.82"
    },
    "session_cells": {
      "rows": 17,
      "tall": []
    },
    "sessions_title_width": {
      "table": 1020,
      "title": 583,
      "pct": 0.5715686274509804,
      "title_cell": 583
    },
    "blind_expected_top_id": "t04",
    "blind_top_row_text": "函数依赖与范式（3NF、BCNF）\t缺失\t0.0000\t25\t25.00\t▾",
… （共 159 行，此处省略 119 行，完整内容见 .jsonl）
```

</details>

<details><summary>Qoder 思考</summary>

Full regression passes. Note: mobile radar_labels count changed 24 → 19 (fewer multi-line text elements because wrapping is smarter now), still 0 out of bounds. Now Read the new screenshots.

</details>

**Qoder：** 回归全绿。看新截图。

🔧 **Read** `.cache/scratch/site-09c2-desktop.png`

<details><summary>结果</summary>

```
[image]
```

</details>

🔧 **Read** `.cache/scratch/site-09c2-mobile.png`

<details><summary>结果</summary>

```
[image]
```

</details>

<details><summary>Qoder 思考</summary>

Again completely fabricated descriptions (desktop: "ExamMaster documentation" with API tables; mobile: Pandora help center). Same phenomenon — record honestly in DEVLOG.

Now append to DEVLOG 09c section a follow-up subsection. Structure: add "### F. 追加修复：雷达轴标签折行（同日第二轮反馈）" after E? Currently 09c section has A–E, E being 未做. Insert the new subsection before E or append after E as F? Logical: add F after E, or insert before E. I'll insert a new section "E. 追加修复…" and rename 未做 to F? Renaming changes existing content — acceptable and cleaner. Let me add:

- F. 追加修复：雷达轴标签折行（产品负责人第二轮反馈）

with content: 问题、规则、实现、量测结果（每个知识点两宽度的换行结果列表 + 越界/图例/断点检查 + 截图说明）。

Current E is "未做（留给产品负责人/后续会话）". I'll insert new section before "### E. 未做" as "### E. 追加修复：…" and rename old E to F. Or simpler: append new section F after E. Order-wise 未做 usually last. I'll insert before E and re-letter E→F.

List of wrapped lines for DEVLOG (from measurement):

桌面（1440，每行 ≤11 字宽）:
- 函数依赖与范式 / （3NF、BCNF）
- 隔离级别与 MVCC（单行）
- SQL 查询与视图（单行）
- 关系模型与关系代数（单行）
- 查询处理与优化（单行）
- 分布式事务与两阶段提交 / （2PC）
- 索引： / B+树与哈希索引
- 事务的 ACID 特性（单行）
- 并发控制： / 两阶段锁与死锁
- 故障恢复： / WAL 与 ARIES

手机（375，每行 ≤8 字宽）:
- 函数依赖与范式 / （3NF、BCNF）
- 隔离级别与 MVCC（单行）
- SQL 查询与视图（单行）
- 关系模型与 / 关系代数
- 查询处理与优化（单行）
- 分布式事务与 / 两阶段提交 / （2PC）
- 索引： / B+树与哈希索引
- 事务的 ACID 特性（单行）
- 并发控制： / 两阶段锁与死锁
- 故障恢复： / WAL 与 ARIES

Checks: 每行在容器内（oob 0）；与图例不相交（最近距离：手机底部标签底 6046 vs 图例顶 6118.9；桌面 4031 vs 4064.1）；断点检查 0 个 ASCII 字母数字相邻；09b 的"全部 SVG 文本在容器内"也复验（桌面 17 个、手机 19 个文本元素，0 越界）；完整 check_09c.py 回归全绿。截图 site-09c2-*.png 读取仍是与页面不符的描述（桌面被描述成 ExamMaster 文档、手机被描述成 Pandora 帮助中心），目视核对无法进行，以 DOM 量测代替。

Also mention implementation: tokens = ASCII 字母数字串不可拆；宽度按 CJK=1、ASCII=0.55、空格=0.3 估算；"（"前与"："后为硬换行；超宽回退到最近软断点（"与"后或空格处）；放不下时未动半径字号（量测全部在容器内，无需缩小）。

Write DEVLOG edit.

</details>

**Qoder：** 截图读取仍与页面完全不符（桌面被描述成"ExamMaster 文档"、手机被描述成 Pandora 帮助中心），照实记入 DEVLOG。追加 09c 小节的追加修复部分。

🔧 **Edit** `docs/DEVLOG.md`（替换 23 → 1661 字符）

<details><summary>结果</summary>

```
Successfully modified file: /Users/wanderer/Project/oceanbase/powercontext-camp/.camp/wt/eco-qoder-site/qoder/docs/DEVLOG.md (1 replacements).
```

</details>

<details><summary>Qoder 思考</summary>

Also update section D (改动的文件) to mention the wrapAxisLabel rewrite? The D section lists files; main.js is already listed but with "(inlineCode()、会话卡片与合计卡渲染)" — append wrapAxisLabel. Let me update it.

</details>

🔧 **Edit** `docs/DEVLOG.md`（替换 260 → 333 字符）

<details><summary>结果</summary>

```
Successfully modified file: /Users/wanderer/Project/oceanbase/powercontext-camp/.camp/wt/eco-qoder-site/qoder/docs/DEVLOG.md (1 replacements).
```

</details>

🔧 **TaskStop** ```json
{
 "task_id": "bapgbg0co"
}
```

<details><summary>结果</summary>

```
{"message":"Successfully stopped task: bapgbg0co (.cache/scratch/pwvenv/bin/python -m http.server 18808 --directory site)","task_id":"bapgbg0co","task_type":"local_bash","command":".cache/scratch/pwvenv/bin/python -m http.server 18808 --directory site"}
```

</details>

**指令：** <task-notification>
<task-id>bapgbg0co</task-id>
<tool-use-id>call_648c23c369124a4189a0727f</tool-use-id>
<output-file>/var/folders/lg/918d_j1j5n1382m1p_zljygr0000gn/T/qoder-cli-cn-501/-Users-wanderer-Project-oceanbase-powercontext-camp--camp-wt-eco-qoder-site-qoder/a9dea624-193c-4651-9bff-b0cd2223f98d/tasks/bapgbg0co.output</output-file>
<status>killed</status>
<summary>Background command "Start preview server on port 18808" was stopped</summary>
</task-notification>

**Qoder：** 雷达轴标签折行修完，服务器已关。改动只有 `site/assets/main.js` 的 `wrapAxisLabel()`（重写折行算法）和 DEVLOG 09c 一节（追加 E 小节、原“未做”顺延为 F）。

**修法**：标签切成不可拆的 token（连续 ASCII 字母数字——WAL、ARIES、MVCC、2PC、3NF、BCNF、ACID——整体不拆）；只在"："后、"（"前、"与"后、空格处换行；行宽按 CJK=1 / ASCII=0.55 / 空格=0.3 估算（宽屏预算 11、窄屏 8）；token 放不下时回退到行内最近的合法断点。本次量测所有行都在容器内，无需缩小半径或字号。

**验收**（`check_09c_radar.py`，两宽度，从 ECharts 实例取换行名后逐行匹配 SVG 元素量 rect）：
- 每行都在容器内：越界 0（09b 的“全部 SVG 文本在容器内”也复验通过，手机文本元素 24→19）；
- 与图例不相交：0 处（最近距离桌面 33px、手机 73px）；
- 换行点检查：相邻两行末/首字符“都是 ASCII 字母数字”的断点 0 个，缩写全部完整单行——例如“故障恢复： / WAL 与 ARIES”、“隔离级别与 MVCC”单行、“（3NF、BCNF）”、“（2PC）”；
- 换行结果逐知识点列表已写进 DEVLOG；
- `check_09c.py` 全项回归通过。

截图已用 Read 查看，但描述仍与页面完全不符（桌面被描述成"ExamMaster 文档"、手机被描述成 Pandora 帮助中心），照前例在 DEVLOG 记为“目视核对无法进行，以 DOM 量测代替”。未发布网站。

## 会话结果

雷达轴标签折行修完，服务器已关。改动只有 `site/assets/main.js` 的 `wrapAxisLabel()`（重写折行算法）和 DEVLOG 09c 一节（追加 E 小节、原“未做”顺延为 F）。

**修法**：标签切成不可拆的 token（连续 ASCII 字母数字——WAL、ARIES、MVCC、2PC、3NF、BCNF、ACID——整体不拆）；只在"："后、"（"前、"与"后、空格处换行；行宽按 CJK=1 / ASCII=0.55 / 空格=0.3 估算（宽屏预算 11、窄屏 8）；token 放不下时回退到行内最近的合法断点。本次量测所有行都在容器内，无需缩小半径或字号。

**验收**（`check_09c_radar.py`，两宽度，从 ECharts 实例取换行名后逐行匹配 SVG 元素量 rect）：
- 每行都在容器内：越界 0（09b 的“全部 SVG 文本在容器内”也复验通过，手机文本元素 24→19）；
- 与图例不相交：0 处（最近距离桌面 33px、手机 73px）；
- 换行点检查：相邻两行末/首字符“都是 ASCII 字母数字”的断点 0 个，缩写全部完整单行——例如“故障恢复： / WAL 与 ARIES”、“隔离级别与 MVCC”单行、“（3NF、BCNF）”、“（2PC）”；
- 换行结果逐知识点列表已写进 DEVLOG；
- `check_09c.py` 全项回归通过。

截图已用 Read 查看，但描述仍与页面完全不符（桌面被描述成"ExamMaster 文档"、手机被描述成 Pandora 帮助中心），照前例在 DEVLOG 记为“目视核对无法进行，以 DOM 量测代替”。未发布网站。

