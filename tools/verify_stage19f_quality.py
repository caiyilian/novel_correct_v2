#!/usr/bin/env python3
"""Stage 19f quality gate for corrected novel output."""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Dict, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.io.loader import TextLoader


NON_STANDARD_SYMBOLS = set('[]【】［］{}《》“”"')
MOJIBAKE_SYMBOLS = {
    "\u9286",  # 銆, common mojibake fragment for 「」
    "\u5c8b",  # 岋
    "\u7d1d",  # 紝
    "\u9287",  # 銇
    "\u5c7b",  # 屻
}


def normalize_for_compare(text: str) -> str:
    """Remove whitespace for answer comparison."""
    return re.sub(r"\s+", "", text)


def count_non_standard(text: str) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for ch in text:
        if ch in NON_STANDARD_SYMBOLS or ch in MOJIBAKE_SYMBOLS:
            counts[ch] = counts.get(ch, 0) + 1
    return counts


def quick_similarity(left: str, right: str) -> float:
    """Return a near-linear bigram Dice similarity for large normalized texts."""
    if not left and not right:
        return 1.0
    if not left or not right:
        return 0.0
    if len(left) == 1 or len(right) == 1:
        return 1.0 if left == right else 0.0

    left_bigrams = Counter(left[i:i + 2] for i in range(len(left) - 1))
    right_bigrams = Counter(right[i:i + 2] for i in range(len(right) - 1))
    overlap = sum((left_bigrams & right_bigrams).values())
    return (2 * overlap) / (sum(left_bigrams.values()) + sum(right_bigrams.values()))


def resolve_path(path_text: Optional[str], directory: str, prefix: str) -> Optional[Path]:
    if path_text:
        path = Path(path_text)
        if path.exists():
            return path
    matches = sorted(
        p for p in Path(directory).iterdir()
        if p.name.startswith(prefix) and p.suffix == ".txt"
    )
    return matches[0] if matches else None


def quality_report(corrected_path: Path, answer_path: Optional[Path] = None) -> dict:
    corrected = TextLoader().load(corrected_path)
    text = corrected.text
    left_count = text.count("「")
    right_count = text.count("」")
    non_standard = count_non_standard(text)

    report = {
        "corrected_path": str(corrected_path),
        "chars": len(text),
        "lines": corrected.line_count(),
        "left_quote_count": left_count,
        "right_quote_count": right_count,
        "quote_balanced": left_count == right_count,
        "non_standard_total": sum(non_standard.values()),
        "non_standard_by_symbol": non_standard,
        "answer_path": str(answer_path) if answer_path else "",
        "answer_match_ignore_whitespace": None,
    }

    if answer_path:
        answer = TextLoader().load(answer_path)
        corrected_norm = normalize_for_compare(text)
        answer_norm = normalize_for_compare(answer.text)
        report["answer_match_ignore_whitespace"] = round(
            quick_similarity(corrected_norm, answer_norm),
            4,
        )
        report["answer_chars_ignore_whitespace"] = len(answer_norm)
        report["corrected_chars_ignore_whitespace"] = len(corrected_norm)

    return report


def check_thresholds(
    report: dict,
    max_non_standard: int,
    min_quote_count: int,
    min_answer_match: float,
) -> list[str]:
    failures: list[str] = []
    if report["non_standard_total"] >= max_non_standard:
        failures.append(
            f"non_standard_total {report['non_standard_total']} >= {max_non_standard}"
        )
    if report["left_quote_count"] < min_quote_count:
        failures.append(
            f"left_quote_count {report['left_quote_count']} < {min_quote_count}"
        )
    if report["right_quote_count"] < min_quote_count:
        failures.append(
            f"right_quote_count {report['right_quote_count']} < {min_quote_count}"
        )
    if not report["quote_balanced"]:
        failures.append(
            f"quote counts not balanced: 「{report['left_quote_count']} vs 」{report['right_quote_count']}"
        )
    match = report.get("answer_match_ignore_whitespace")
    if match is not None and match < min_answer_match:
        failures.append(f"answer_match_ignore_whitespace {match} < {min_answer_match}")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("corrected", nargs="?", help="corrected novel path")
    parser.add_argument(
        "--answer",
        default=None,
        help="optional answer file for ignore-whitespace comparison",
    )
    parser.add_argument("--max-non-standard", type=int, default=10)
    parser.add_argument("--min-quote-count", type=int, default=1340)
    parser.add_argument("--min-answer-match", type=float, default=0.9)
    parser.add_argument("--json", action="store_true", help="print machine-readable JSON")
    parser.add_argument("--enforce", action="store_true", help="exit non-zero when thresholds fail")
    args = parser.parse_args()

    corrected = resolve_path(args.corrected, "output", "corrected_")
    answer = resolve_path(args.answer, "data", "answer_") if args.answer is not False else None
    if corrected is None:
        print("corrected novel file not found", file=sys.stderr)
        return 2

    report = quality_report(corrected, answer)
    failures = check_thresholds(
        report,
        max_non_standard=args.max_non_standard,
        min_quote_count=args.min_quote_count,
        min_answer_match=args.min_answer_match,
    )
    report["threshold_failures"] = failures

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print("=" * 60)
        print("  Stage 19f Quality Report")
        print("=" * 60)
        print(f"  File: {report['corrected_path']}")
        print(f"  Size: {report['chars']} chars, {report['lines']} lines")
        print(f"  Quotes: 「{report['left_quote_count']} / 」{report['right_quote_count']}")
        print(f"  Balanced: {report['quote_balanced']}")
        print(f"  Non-standard total: {report['non_standard_total']}")
        print(f"  Non-standard by symbol: {report['non_standard_by_symbol']}")
        if report["answer_match_ignore_whitespace"] is not None:
            print(f"  Answer match (ignore whitespace): {report['answer_match_ignore_whitespace']:.2%}")
        if failures:
            print("  Threshold failures:")
            for failure in failures:
                print(f"    - {failure}")
        else:
            print("  Thresholds: PASS")
        print("=" * 60)

    return 1 if args.enforce and failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
