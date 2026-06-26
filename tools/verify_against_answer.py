#!/usr/bin/env python3
"""
tools/verify_against_answer.py --- Answer verification tool

Compare corrected output against a ground truth answer file.
Line structures may differ (answer may merge paragraphs), so comparison
is based on content with whitespace ignored.

Usage:
    python tools/verify_against_answer.py output/corrected_NAME.txt data/answer/answer_NAME.txt
    python tools/verify_against_answer.py output/corrected_NAME.txt data/answer/answer_NAME.txt --json output/verify_report.json
"""

from __future__ import annotations

import argparse
import difflib
import json
import re
import sys
from pathlib import Path
from typing import Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.io.loader import TextLoader


# --- Non-standard symbol definitions ---

NON_STANDARD_EXPECTED = {
    "\u005b": "\u300c",  # [ -> left JP quote
    "\u005d": "\u300d",  # ] -> right JP quote
    "\u3010": "\u300c",  # 【 -> left JP quote
    "\u3011": "\u300d",  # 】 -> right JP quote
    "\uff3b": "\u300c",  # full-width [ -> left JP quote
    "\uff3d": "\u300d",  # full-width ] -> right JP quote
    "\u007b": "\u300c",  # { -> left JP quote
    "\u007d": "\u300d",  # } -> right JP quote
    "\u300a": "\u300c",  # << -> left JP quote
    "\u300b": "\u300d",  # >> -> right JP quote
    "\u201c": "\u300c",  # left double curly quote -> left JP quote
    "\u201d": "\u300d",  # right double curly quote -> right JP quote
}

NON_STANDARD_SET = set(NON_STANDARD_EXPECTED.keys())


def normalize_text(text: str) -> str:
    """Remove all whitespace for content-only comparison."""
    return re.sub(r"\s+", "", text)


def symbol_stats(text: str) -> dict:
    """Compute bracket symbol statistics for a text."""
    ns_by_sym: Dict[str, int] = {}
    for ch in text:
        if ch in NON_STANDARD_SET:
            ns_by_sym[ch] = ns_by_sym.get(ch, 0) + 1
    return {
        "left_japanese_quote": text.count("\u300c"),
        "right_japanese_quote": text.count("\u300d"),
        "non_standard_total": sum(ns_by_sym.values()),
        "non_standard_by_symbol": dict(
            sorted(ns_by_sym.items(), key=lambda x: -x[1])
        ),
    }


# --- Report generation ---


def generate_report(corrected_path: str, answer_path: str) -> dict:
    corrected_doc = TextLoader().load(corrected_path)
    answer_doc = TextLoader().load(answer_path)

    corrected_text = corrected_doc.text
    answer_text = answer_doc.text

    # Basic info
    c_sym = symbol_stats(corrected_text)
    a_sym = symbol_stats(answer_text)

    # Content comparison (ignore whitespace)
    corrected_norm = normalize_text(corrected_text)
    answer_norm = normalize_text(answer_text)

    matcher = difflib.SequenceMatcher(None, corrected_norm, answer_norm)
    matching_chars = sum(
        len(corrected_norm[i1:i2])
        for tag, i1, i2, j1, j2 in matcher.get_opcodes()
        if tag == "equal"
    )
    total_chars = len(answer_norm)
    match_rate = matching_chars / total_chars if total_chars > 0 else 1.0

    # Diff snippets for review
    diff_snippets: List[dict] = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag != "equal":
            c_snip = corrected_norm[i1:i2][:200] if corrected_norm[i1:i2] else ""
            a_snip = answer_norm[j1:j2][:200] if answer_norm[j1:j2] else ""
            if c_snip or a_snip:
                diff_snippets.append({
                    "tag": tag,
                    "corrected": c_snip,
                    "answer": a_snip,
                    "corrected_len": i2 - i1,
                    "answer_len": j2 - j1,
                })

    # Symbol comparison
    symbol_compare = {}
    for key in ("left_japanese_quote", "right_japanese_quote", "non_standard_total"):
        cv = c_sym[key]
        av = a_sym[key]
        symbol_compare[key] = {
            "corrected": cv,
            "answer": av,
            "diff": cv - av,
            "match": cv == av,
        }

    # Quote balance
    c_balanced = c_sym["left_japanese_quote"] == c_sym["right_japanese_quote"]

    return {
        "corrected_path": corrected_path,
        "answer_path": answer_path,
        "corrected": {
            "chars": len(corrected_text),
            "lines": corrected_doc.line_count(),
            "chars_no_whitespace": len(corrected_norm),
        },
        "answer": {
            "chars": len(answer_text),
            "lines": answer_doc.line_count(),
            "chars_no_whitespace": len(answer_norm),
        },
        "symbol_stats": {
            "corrected": c_sym,
            "answer": a_sym,
            "comparison": symbol_compare,
        },
        "quote_balance": {
            "corrected_balanced": c_balanced,
        },
        "matching": {
            "matching_chars_no_whitespace": matching_chars,
            "total_answer_chars_no_whitespace": total_chars,
            "match_rate": round(match_rate, 4),
        },
        "diff_snippets_count": len(diff_snippets),
        "diff_snippets": diff_snippets[:60],
    }


# --- Terminal output ---


def _icon(ok: bool) -> str:
    return "[OK]" if ok else "[NG]"


def print_report(report: dict):
    c = report["corrected"]
    a = report["answer"]
    c_sym = report["symbol_stats"]["corrected"]
    a_sym = report["symbol_stats"]["answer"]
    comp = report["symbol_stats"]["comparison"]
    match = report["matching"]
    bal = report["quote_balance"]

    sep = "=" * 68

    print(sep)
    print("  Stage 22a - Answer Verification Report")
    print(sep)
    print(f"  Corrected: {c['chars']:,} chars, {c['lines']} lines")
    print(f"  Answer:    {a['chars']:,} chars, {a['lines']} lines")
    print()

    # Symbol comparison
    print(f"  -- Symbol Comparison --")
    print(f"  {'Metric':<32} {'Corrected':>10} {'Answer':>10} {'Diff':>8}  Status")
    print(f"  " + "-" * 72)
    rows = [
        ("left_japanese_quote", "Left quote", "\u300c"),
        ("right_japanese_quote", "Right quote", "\u300d"),
        ("non_standard_total", "Non-standard symbols", ""),
    ]
    for key, label, _ in rows:
        v = comp[key]
        print(f"  {label:<32} {v['corrected']:>10} {v['answer']:>10} "
              f"{v['diff']:+>8}  {_icon(v['match'])}")

    print()
    print(f"  -- Quote Balance --")
    print(f"  Corrected: {_icon(bal['corrected_balanced'])}  "
          f"( counts: {c_sym['left_japanese_quote']} vs {c_sym['right_japanese_quote']})")
    print(f"  Answer:    {_icon(c_sym['left_japanese_quote'] == c_sym['right_japanese_quote'] and a_sym['left_japanese_quote'] == a_sym['right_japanese_quote'])}  "
          f"( counts: {a_sym['left_japanese_quote']} vs {a_sym['right_japanese_quote']})")

    ns = c_sym["non_standard_by_symbol"]
    if ns:
        print(f"\n  -- Remaining Non-standard Symbols --")
        for ch, cnt in list(ns.items())[:15]:
            display = repr(ch).strip("'")
            print(f"    U+{ord(ch):04X} ({display}): {cnt}")
        if len(ns) > 15:
            print(f"    ... and {len(ns) - 15} more types")

    print()
    print(f"  -- Matching (ignoring whitespace) --")
    print(f"  Match rate:            {match['match_rate']:.4f} ({match['match_rate']:.2%})")
    print(f"  Matching chars:        {match['matching_chars_no_whitespace']:,}")
    print(f"  Answer total chars:    {match['total_answer_chars_no_whitespace']:,}")
    print()

    snippets = report["diff_snippets"]
    print(f"  Diff snippets: {report['diff_snippets_count']} total "
          f"(showing first {len(snippets)})")
    for ds in snippets[:30]:
        tag = ds["tag"]
        c_text = ds["corrected"][:100] if ds["corrected"] else "[empty]"
        a_text = ds["answer"][:100] if ds["answer"] else "[empty]"
        print(f"    [{tag}] C: {c_text}")
        if a_text != c_text:
            print(f"          A: {a_text}")

    print()
    print(sep)


# --- JSON output ---


def save_json(report: dict, output_path: str):
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"  JSON saved: {output_path}")


# --- Entry point ---


def main():
    parser = argparse.ArgumentParser(
        description="Answer verification tool",
    )
    parser.add_argument("corrected_file", help="corrected file path")
    parser.add_argument("answer_file", help="ground truth answer file path")
    parser.add_argument(
        "--json", default="",
        help="JSON output path",
    )
    args = parser.parse_args()

    if not Path(args.corrected_file).exists():
        print(f"Error: corrected file not found: {args.corrected_file}")
        sys.exit(1)
    if not Path(args.answer_file).exists():
        print(f"Error: answer file not found: {args.answer_file}")
        sys.exit(1)

    report = generate_report(
        corrected_path=args.corrected_file,
        answer_path=args.answer_file,
    )

    print_report(report)

    if args.json:
        save_json(report, args.json)

    print("Done.")


if __name__ == "__main__":
    main()
