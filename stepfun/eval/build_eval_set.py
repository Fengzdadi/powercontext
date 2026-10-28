#!/usr/bin/env python3
"""Build the fixed bilingual retrieval eval set used by the benchmark.

Source: MIRACL v1.0 dev split (https://huggingface.co/datasets/miracl/miracl, Apache-2.0;
passages from Wikipedia, CC BY-SA). For a seeded random sample of queries per language we keep
every judged passage (relevance 1 = positive, 0 = judged hard negative). The corpus is the union of
those passages, so each query competes against hard negatives that other systems retrieved for it.

Only the Python standard library is used. Corpus shards are streamed and filtered, never stored.
Usage: python3 eval/build_eval_set.py [--zh 60] [--en 30] [--seed 2026]
"""
import argparse, gzip, io, json, os, random, sys, urllib.request
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor

HF = os.environ.get("HF_ENDPOINT", "https://huggingface.co").rstrip("/")
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
SHARDS = {"zh": 10, "en": 66}


def fetch_text(url):
    with urllib.request.urlopen(url, timeout=120) as r:
        return r.read().decode("utf-8")


def load_topics_qrels(lang):
    base = f"{HF}/datasets/miracl/miracl/resolve/main/miracl-v1.0-{lang}"
    topics = {}
    for line in fetch_text(f"{base}/topics/topics.miracl-v1.0-{lang}-dev.tsv").splitlines():
        qid, text = line.split("\t", 1)
        topics[qid] = text.strip()
    qrels = defaultdict(dict)
    for line in fetch_text(f"{base}/qrels/qrels.miracl-v1.0-{lang}-dev.tsv").splitlines():
        qid, _, docid, rel = line.split("\t")
        qrels[qid][docid] = int(rel)
    return topics, qrels


def scan_shard(lang, i, wanted):
    url = f"{HF}/datasets/miracl/miracl-corpus/resolve/main/miracl-corpus-v1.0-{lang}/docs-{i}.jsonl.gz"
    found = {}
    with urllib.request.urlopen(url, timeout=600) as r:
        with gzip.GzipFile(fileobj=io.BufferedReader(r, buffer_size=1 << 20)) as gz:
            for raw in gz:
                # Cheap prefix check before json parsing: lines start with {"docid": "...".
                start = raw.find(b'"docid": "') + 10
                docid = raw[start:raw.find(b'"', start)].decode()
                if docid in wanted:
                    doc = json.loads(raw)
                    found[docid] = {"title": doc["title"], "text": doc["text"]}
    print(f"  {lang} shard {i}: {len(found)} passages", file=sys.stderr)
    return found


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--zh", type=int, default=60)
    ap.add_argument("--en", type=int, default=30)
    ap.add_argument("--seed", type=int, default=2026)
    args = ap.parse_args()
    rng = random.Random(args.seed)
    queries, qrels_out, corpus = [], [], {}
    for lang, n in (("zh", args.zh), ("en", args.en)):
        topics, qrels = load_topics_qrels(lang)
        eligible = sorted(q for q, j in qrels.items()
                          if sum(j.values()) >= 1 and sum(1 for v in j.values() if v == 0) >= 3)
        picked = sorted(rng.sample(eligible, n))
        wanted = {d for q in picked for d in qrels[q]}
        print(f"{lang}: {len(eligible)} eligible, picked {n}, {len(wanted)} judged passages", file=sys.stderr)
        found = {}
        with ThreadPoolExecutor(max_workers=8) as pool:
            for part in pool.map(lambda i: scan_shard(lang, i, wanted), range(SHARDS[lang])):
                found.update(part)
        missing = wanted - found.keys()
        if missing:
            print(f"  warning: {len(missing)} passages not found", file=sys.stderr)
        for q in picked:
            queries.append({"qid": f"{lang}-{q}", "lang": lang, "text": topics[q]})
            for d, rel in sorted(qrels[q].items()):
                if d in found:
                    qrels_out.append((f"{lang}-{q}", f"{lang}-{d}", rel))
        for d, doc in found.items():
            corpus[f"{lang}-{d}"] = {"id": f"{lang}-{d}", "lang": lang, **doc}
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, "corpus.jsonl"), "w", encoding="utf-8") as f:
        for d in sorted(corpus):
            f.write(json.dumps(corpus[d], ensure_ascii=False) + "\n")
    with open(os.path.join(OUT, "queries.jsonl"), "w", encoding="utf-8") as f:
        for q in queries:
            f.write(json.dumps(q, ensure_ascii=False) + "\n")
    with open(os.path.join(OUT, "qrels.tsv"), "w", encoding="utf-8") as f:
        for q, d, rel in qrels_out:
            f.write(f"{q}\t{d}\t{rel}\n")
    print(f"wrote {len(corpus)} passages, {len(queries)} queries, {len(qrels_out)} judgements", file=sys.stderr)


if __name__ == "__main__":
    main()
