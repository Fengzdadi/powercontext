// Document parsing and chunking (runs in the browser).

const CJK = /[㐀-鿿豈-﫿぀-ヿ가-힯]/g;

// Rough token estimate for the XLM-R tokenizer: ~1 token per CJK character, ~1 per 4 other characters.
export function estimateTokens(text) {
  const cjk = (text.match(CJK) ?? []).length;
  return cjk + Math.ceil((text.length - cjk) / 4);
}

function splitSentences(text) {
  // Keep the delimiter with its sentence; paragraphs are hard boundaries.
  const out = [];
  for (const para of text.split(/\n\s*\n/)) {
    const parts = para.replace(/\s*\n\s*/g, " ").match(/[^。！？；!?;]+[。！？；!?;]+["”’」』)]*|[^。！？；!?;]+$/g) ?? [];
    for (const p of parts) {
      // English sentences inside a part: split on ". " followed by an upper-case letter or digit.
      for (const s of p.split(/(?<=[.])\s+(?=[A-Z0-9])/)) if (s.trim()) out.push(s.trim());
    }
    out.push("\n");
  }
  return out;
}

// Greedy sentence packing up to maxTokens per chunk with one sentence of overlap. Sentences longer than
// maxTokens are cut by characters. The title is prepended to every chunk so each chunk is self-describing
// for both the embedding and the full-text index.
export function chunkDocument({ title = "", text }, { maxTokens = 300, overlapTokens = 40 } = {}) {
  const body = text.replace(/\r\n?/g, "\n").trim();
  const header = title ? `${title}\n` : "";
  const budget = Math.max(32, maxTokens - estimateTokens(header));
  if (estimateTokens(body) <= budget) return [header + body];
  const chunks = [];
  let cur = [];
  let curTok = 0;
  const flush = () => {
    const t = cur.join(" ").replace(/ ?\n ?/g, "\n").trim();
    if (t) chunks.push(header + t);
  };
  for (let s of splitSentences(body)) {
    if (s === "\n") {
      if (cur.length) cur.push("\n");
      continue;
    }
    while (estimateTokens(s) > budget) {
      // cut an over-long sentence into budget-sized pieces
      let cut = s.length;
      while (estimateTokens(s.slice(0, cut)) > budget) cut = Math.floor(cut * 0.8);
      if (cur.length) {
        flush();
        cur = [];
        curTok = 0;
      }
      chunks.push(header + s.slice(0, cut).trim());
      s = s.slice(cut);
    }
    const tok = estimateTokens(s);
    if (curTok + tok > budget && cur.length) {
      flush();
      // overlap: carry the last sentence if it is short enough
      const last = [...cur].reverse().find((x) => x !== "\n");
      cur = last && estimateTokens(last) <= overlapTokens ? [last] : [];
      curTok = cur.length ? estimateTokens(cur[0]) : 0;
    }
    cur.push(s);
    curTok += tok;
  }
  flush();
  return chunks;
}

export async function sha256Hex(text) {
  const buf = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text));
  return [...new Uint8Array(buf)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

// Files -> [{ key, title, text, source }]. .txt/.md: one document per file; .jsonl/.json: one per record
// with { id?, title?, text|content|body }.
export async function parseFiles(files) {
  const docs = [];
  for (const f of files) {
    const name = f.webkitRelativePath || f.name;
    const raw = await f.text();
    if (/\.(jsonl|ndjson)$/i.test(name)) {
      raw.split(/\n/).forEach((line, i) => {
        if (line.trim()) docs.push(recordToDoc(JSON.parse(line), `${name}#${i}`, name));
      });
    } else if (/\.json$/i.test(name)) {
      const data = JSON.parse(raw);
      (Array.isArray(data) ? data : [data]).forEach((r, i) => docs.push(recordToDoc(r, `${name}#${i}`, name)));
    } else {
      const title = name.replace(/\.[^.]+$/, "").split("/").pop();
      docs.push({ key: name, title, text: raw, source: name });
    }
  }
  return docs.filter((d) => d.text && d.text.trim());
}

function recordToDoc(r, fallbackKey, source) {
  const text = r.text ?? r.content ?? r.body ?? "";
  return { key: String(r.id ?? r.key ?? fallbackKey), title: String(r.title ?? ""), text: String(text), source };
}
