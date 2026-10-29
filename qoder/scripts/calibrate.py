#!/usr/bin/env python3
"""Calibrate coverage rules on sample data.

Run from the app/ directory:
    .venv/bin/python ../scripts/calibrate.py [--course db101] [--source auto]

Runs the full coverage analysis (persisting a coverage run) and prints, for
every topic and every key term: whether it was found, in which chunks
(document/page/heading), its best semantic score, and how far the topic sits
from the covered thresholds. Judgments are compared against the design truth
in samples/course-db/README.md.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app"))

from examradar.config import get_settings
from examradar.coverage import analyze
from examradar.seekdb import ensure_tables
from examradar.syllabus import parse_syllabus

DESIGN_LEVELS = {
    "t01": "missing", "t02": "thin", "t03": "covered", "t04": "missing",
    "t05": "missing", "t06": "covered", "t07": "covered", "t08": "thin",
    "t09": "covered", "t10": "covered",
}


def _ref_str(ref: dict) -> str:
    parts = []
    if ref.get("doc"):
        parts.append(Path(ref["doc"]).stem)
    if ref.get("page"):
        parts.append(f"p{ref['page']}")
    if ref.get("heading"):
        parts.append(ref["heading"][:20])
    return "·".join(parts)


def main():
    parser = argparse.ArgumentParser(description="Calibrate coverage rules")
    parser.add_argument("--course", default="db101")
    parser.add_argument("--source", default="auto")
    parser.add_argument("--syllabus", default=None,
                        help="Path to syllabus file (default: samples/course-db/syllabus.txt)")
    args = parser.parse_args()

    s = get_settings()
    print(f"Database: {s.seekdb_database}")
    print(f"Thresholds: term_ratio_covered={s.coverage_term_ratio_covered}, "
          f"support_chars_covered={s.coverage_support_chars}, "
          f"min_body_chars={s.coverage_min_body_chars}")
    print()

    ensure_tables()

    syllabus_path = args.syllabus or str(
        Path(__file__).resolve().parent.parent / "samples" / "course-db" / "syllabus.txt"
    )
    text = Path(syllabus_path).read_text(encoding="utf-8")
    topics = parse_syllabus(text)
    print(f"Parsed {len(topics)} topics from {syllabus_path}")
    print()

    result = analyze(args.course, text, source=args.source)

    ratio_t = s.coverage_term_ratio_covered
    support_t = s.coverage_support_chars

    mismatches = 0
    for item in result["items"]:
        tid = item["topic_id"]
        level = item["coverage_level"]
        score = item["coverage_score"]
        found = sum(1 for t in item["terms"] if t["found"])
        total = len(item["terms"])
        ratio = found / total if total else 0.0
        support = item["support_chars"]

        design = DESIGN_LEVELS.get(tid)
        marker = ""
        if design is not None and design != level:
            marker = f"  <<< MISMATCH: design says {design}"
            mismatches += 1

        print(f"=== {tid} {item['topic_name']}")
        print(f"  level={level} score={score:.4f} "
              f"terms={found}/{total} (ratio {ratio:.2f} vs {ratio_t}) "
              f"support={item['support_chunks']}段/{support}字 (vs {support_t})"
              f"{marker}")
        for t in item["terms"]:
            if t["found"]:
                refs = [_ref_str(r) for r in t["chunks"][:3]]
                more = f" 等{len(t['chunks'])}处" if len(t["chunks"]) > 3 else ""
                sem = t.get("best_sem")
                sem_s = f" sem={sem:.4f}" if sem is not None else " sem=-"
                print(f"    [找到] {t['term']}{sem_s} -> {'、'.join(refs)}{more}")
            else:
                print(f"    [未找到] {t['term']}")
        if level == "covered":
            print(f"    距离阈值: 比例高出 {ratio - ratio_t:.2f}, "
                  f"支撑字数高出 {support - support_t}")
        elif level == "thin":
            gap_ratio = max(0.0, ratio_t - ratio)
            gap_support = max(0, support_t - support)
            print(f"    距离阈值: 比例差 {gap_ratio:.2f}, 支撑字数差 {gap_support}")
        print()

    print("Exam question assignment (question -> topic, basis):")
    for item in result["items"]:
        for q in item["exam_questions"]:
            basis = "、".join(q["matched_terms"]) if q["matched_terms"] else "纯语义"
            print(f"  Q{q['question_no']} ({q['points']:.0f}分) -> "
                  f"{item['topic_id']} {item['topic_name'][:16]} "
                  f"依据[{basis}] sim={q['similarity']:.4f}")
    print()

    print("Blind spot ranking (exam_weight * (1 - coverage_score)):")
    for item in result["items"]:
        print(f"  {item['topic_id']} {item['topic_name'][:24]:<26} "
              f"weight={item['exam_weight']:>5.1f} "
              f"coverage={item['coverage_score']:.4f} "
              f"blind={item['blind_spot_score']:.2f}")

    print()
    if mismatches:
        print(f"RESULT: {mismatches} topic(s) disagree with design truth")
        sys.exit(1)
    print("RESULT: all topic judgments match design truth")


if __name__ == "__main__":
    main()
