#!/usr/bin/env python3
"""Calibrate coverage thresholds on sample data.

Run from the app/ directory:
    .venv/bin/python ../scripts/calibrate.py [--course db101] [--source auto]

Outputs per-topic score distributions and suggests threshold values.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app"))

from examradar.config import get_settings
from examradar.seekdb import ensure_tables, hybrid_search, get_connection
from examradar.embedding import get_embedding_model
from examradar.syllabus import parse_syllabus


def main():
    parser = argparse.ArgumentParser(description="Calibrate coverage thresholds")
    parser.add_argument("--course", default="db101")
    parser.add_argument("--source", default="auto")
    parser.add_argument("--syllabus", default=None,
                        help="Path to syllabus file (default: samples/course-db/syllabus.txt)")
    args = parser.parse_args()

    s = get_settings()
    print(f"Database: {s.effective_database}")
    print(f"Thresholds: T_covered={s.coverage_t_covered}, T_thin={s.coverage_t_thin}, "
          f"kw_scale={s.coverage_kw_scale}")
    print()

    ensure_tables()

    syllabus_path = args.syllabus or str(
        Path(__file__).resolve().parent.parent / "samples" / "course-db" / "syllabus.txt"
    )
    text = Path(syllabus_path).read_text(encoding="utf-8")
    topics = parse_syllabus(text)
    print(f"Parsed {len(topics)} topics from {syllabus_path}")
    print()

    model = get_embedding_model()

    print(f"{'ID':<5} {'Topic':<30} {'Sem':>6} {'KW':>8} {'Score':>7} {'Level':<10}")
    print("-" * 80)

    sem_scores = []
    kw_scores = []
    combined_scores = []

    for topic in topics:
        query_vec = model.embed_one(topic.search_query, is_query=True)
        hits, _, _ = hybrid_search(
            query_text=topic.search_query,
            query_vector=query_vec,
            course_id=args.course,
            doc_kinds=["notes", "slides", "paper"],
            top_k=5,
        )
        if hits:
            best = hits[0]
            sem = best.get("_semantic_score") or 0.0
            kw = best.get("_keyword_score") or 0.0
            kw_norm = min(kw / s.coverage_kw_scale, 1.0)
            combined = 0.6 * sem + 0.4 * kw_norm
            if combined >= s.coverage_t_covered:
                level = "covered"
            elif combined >= s.coverage_t_thin:
                level = "thin"
            else:
                level = "missing"
            sem_scores.append(sem)
            kw_scores.append(kw)
            combined_scores.append(combined)
        else:
            sem, kw, combined = 0.0, 0.0, 0.0
            level = "missing"
            sem_scores.append(0.0)
            kw_scores.append(0.0)
            combined_scores.append(0.0)

        name_short = topic.name[:28]
        print(f"{topic.topic_id:<5} {name_short:<30} {sem:>6.4f} {kw:>8.2f} "
              f"{combined:>7.4f} {level:<10}")

    print()
    print("Score distribution:")
    print(f"  Semantic: min={min(sem_scores):.4f}, max={max(sem_scores):.4f}, "
          f"mean={sum(sem_scores)/len(sem_scores):.4f}")
    print(f"  Keyword:  min={min(kw_scores):.2f}, max={max(kw_scores):.2f}, "
          f"mean={sum(kw_scores)/len(kw_scores):.2f}")
    print(f"  Combined: min={min(combined_scores):.4f}, max={max(combined_scores):.4f}, "
          f"mean={sum(combined_scores)/len(combined_scores):.4f}")

    sorted_scores = sorted(combined_scores)
    n = len(sorted_scores)
    print(f"  Combined percentiles: p25={sorted_scores[n//4]:.4f}, "
          f"p50={sorted_scores[n//2]:.4f}, p75={sorted_scores[3*n//4]:.4f}")

    print()
    print("Exam question assignment:")
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT question_no, points, content, embedding FROM chunks "
                "WHERE course_id = %s AND doc_kind = 'exam' AND question_no IS NOT NULL "
                "ORDER BY question_no",
                (args.course,),
            )
            exam_chunks = cur.fetchall()
    finally:
        conn.close()

    print(f"Found {len(exam_chunks)} exam chunks")

    import numpy as np
    topic_embeddings = {}
    for t in topics:
        vec = model.embed_one(t.search_query, is_query=True)
        topic_embeddings[t.topic_id] = np.array(vec)

    for chunk in exam_chunks:
        q_no = chunk["question_no"]
        pts = float(chunk.get("points") or 0)
        emb_raw = chunk.get("embedding")
        if emb_raw is None:
            continue
        if isinstance(emb_raw, str):
            emb_raw = json.loads(emb_raw)
        q_vec = np.array([float(x) for x in emb_raw])

        best_topic = None
        best_sim = -1.0
        for t in topics:
            t_vec = topic_embeddings[t.topic_id]
            cos_sim = float(np.dot(q_vec, t_vec) / (np.linalg.norm(q_vec) * np.linalg.norm(t_vec)))
            sim = (1 + cos_sim) / 2
            if sim > best_sim:
                best_sim = sim
                best_topic = t.topic_id

        topic_name = next((t.name for t in topics if t.topic_id == best_topic), "?")
        print(f"  Q{q_no} ({pts}分) -> {best_topic} {topic_name} (sim={best_sim:.4f})")

    print()
    topic_weights = {t.topic_id: 0.0 for t in topics}
    for chunk in exam_chunks:
        q_no = chunk["question_no"]
        pts = float(chunk.get("points") or 0)
        emb_raw = chunk.get("embedding")
        if emb_raw is None:
            continue
        if isinstance(emb_raw, str):
            emb_raw = json.loads(emb_raw)
        q_vec = np.array([float(x) for x in emb_raw])
        best_topic = None
        best_sim = -1.0
        for t in topics:
            t_vec = topic_embeddings[t.topic_id]
            cos_sim = float(np.dot(q_vec, t_vec) / (np.linalg.norm(q_vec) * np.linalg.norm(t_vec)))
            sim = (1 + cos_sim) / 2
            if sim > best_sim:
                best_sim = sim
                best_topic = t.topic_id
        if best_topic:
            topic_weights[best_topic] += pts

    print("Blind spot ranking (exam_weight * (1 - coverage_score)):")
    blind_spots = []
    for i, t in enumerate(topics):
        weight = topic_weights[t.topic_id]
        score = combined_scores[i]
        blind = weight * (1 - score)
        blind_spots.append((t.topic_id, t.name, weight, score, blind))
    blind_spots.sort(key=lambda x: -x[4])
    for tid, name, weight, score, blind in blind_spots:
        print(f"  {tid} {name:<30} weight={weight:>5.1f}  coverage={score:.4f}  blind={blind:.2f}")


if __name__ == "__main__":
    main()
