// Ranking metrics over document ids (chunks are collapsed to their best-ranked document first).

export function dedupeDocs(hits, k) {
  const seen = new Set();
  const out = [];
  for (const h of hits) {
    const key = h.meta?.doc_key ?? h.id;
    if (seen.has(key)) continue;
    seen.add(key);
    out.push(key);
    if (out.length === k) break;
  }
  return out;
}

// qrel: Map docKey -> relevance (0/1). Judged negatives count as non-relevant, unjudged too.
export function scoreQuery(ranked, qrel, k) {
  const rel = (d) => qrel.get(d) ?? 0;
  const relevant = [...qrel.values()].filter((v) => v > 0).length;
  const top = ranked.slice(0, k);
  const hits = top.filter((d) => rel(d) > 0).length;
  let dcg = 0;
  top.forEach((d, i) => (dcg += rel(d) / Math.log2(i + 2)));
  let idcg = 0;
  for (let i = 0; i < Math.min(relevant, k); i++) idcg += 1 / Math.log2(i + 2);
  const firstRel = top.findIndex((d) => rel(d) > 0);
  return {
    recall: relevant ? hits / relevant : 0,
    ndcg: idcg ? dcg / idcg : 0,
    mrr: firstRel >= 0 ? 1 / (firstRel + 1) : 0,
  };
}

export function mean(xs) {
  return xs.length ? xs.reduce((a, b) => a + b, 0) / xs.length : 0;
}

export function median(xs) {
  if (!xs.length) return null;
  const s = [...xs].sort((a, b) => a - b);
  const m = s.length >> 1;
  return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
}

export function percentile(xs, p) {
  if (!xs.length) return null;
  const s = [...xs].sort((a, b) => a - b);
  return s[Math.min(s.length - 1, Math.max(0, Math.ceil((p / 100) * s.length) - 1))];
}
