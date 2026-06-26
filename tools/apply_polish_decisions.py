"""
将 PolishJudge 的裁决应用到文本，每次修改通过 Verifier 校验，失败则回滚。

用法:
    python tools/apply_polish_decisions.py output/corrected_第1卷_clean.txt ^
        --candidates output/style_candidates.jsonl ^
        --decisions output/polish_decisions.jsonl ^
        --output output/corrected_第1卷_final.txt
"""

import argparse
import json
import re
import sys
import time
from collections import Counter
from pathlib import Path
from typing import List, Optional, Tuple

# 添加项目根目录
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def load_jsonl(path: str) -> List[dict]:
    items = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                items.append(json.loads(line))
    return items


def load_text(path: str) -> str:
    with open(path, "r", encoding="utf-8-sig") as f:
        return f.read()


def save_text(path: str, text: str):
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def quick_verify(text: str, original: str, initial_non_std: int = 9999,
                 initial_balance_diff: int = 0) -> List[str]:
    """快速规则验证，返回失败列表。"""
    failures = []

    # 1. Quote balance — check it didn't get worse
    left = text.count("\u300c")
    right = text.count("\u300d")
    new_diff = abs(left - right)
    if new_diff > initial_balance_diff:
        failures.append(f"quote_balance: {left} vs {right} (worse: {new_diff} > {initial_balance_diff})")

    # 2. Non-standard symbols — check it didn't get worse
    non_std_set = set("[]\u3010\u3011\uff3b\uff3d{}\u300a\u300b\u201c\u201d")
    non_std_count = sum(1 for ch in text if ch in non_std_set)
    if non_std_count > initial_non_std:
        failures.append(f"non_standard: {non_std_count} (worse than initial {initial_non_std})")

    # 3. Consecutive
    for i in range(1, len(text)):
        if text[i] == text[i - 1] and text[i] in ("\u300c", "\u300d"):
            failures.append(f"consecutive_at_{i}")
            break

    # 4. Answer match rate (optional)
    if original:
        orig_norm = re.sub(r"\s+", "", original)
        text_norm = re.sub(r"\s+", "", text)
        # Quick bigram similarity
        if orig_norm and text_norm:
            from collections import Counter
            orig_bigrams = Counter(orig_norm[j:j + 2] for j in range(len(orig_norm) - 1))
            text_bigrams = Counter(text_norm[j:j + 2] for j in range(len(text_norm) - 1))
            overlap = sum((orig_bigrams & text_bigrams).values())
            similarity = (2 * overlap) / (sum(orig_bigrams.values()) + sum(text_bigrams.values())) if orig_bigrams else 1.0
            if similarity < 0.95:
                failures.append(f"similarity_drop: {similarity:.4f}")

    return failures


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", help="input corrected text file")
    parser.add_argument("--candidates", required=True, help="candidates JSONL path")
    parser.add_argument("--decisions", required=True, help="decisions JSONL path")
    parser.add_argument("--output", required=True, help="output text path")
    parser.add_argument("--report", default="", help="apply report JSON path")
    parser.add_argument("--answer", default="", help="answer file path for match rate check")
    args = parser.parse_args()

    if not Path(args.input).exists():
        print(f"Error: input not found: {args.input}", file=sys.stderr)
        return 1
    if not Path(args.candidates).exists():
        print(f"Error: candidates not found: {args.candidates}", file=sys.stderr)
        return 1
    if not Path(args.decisions).exists():
        print(f"Error: decisions not found: {args.decisions}", file=sys.stderr)
        return 1

    text = load_text(args.input)
    candidates = load_jsonl(args.candidates)
    decisions = load_jsonl(args.decisions)

    if len(candidates) != len(decisions):
        print(f"Error: candidates ({len(candidates)}) != decisions ({len(decisions)}). "
              f"Cannot safely match by position.", file=sys.stderr)
        return 1

    original_text = load_text(args.answer) if args.answer else ""

    # Pre-compute initial counts for delta checks
    non_std_set = set("[]\u3010\u3011\uff3b\uff3d{}\u300a\u300b\u201c\u201d")
    initial_non_std = sum(1 for ch in text if ch in non_std_set)
    initial_balance_diff = abs(text.count("\u300c") - text.count("\u300d"))

    # Build apply list: decisions with "apply" matched to candidates by index
    applies: List[Tuple[int, dict, dict]] = []  # (index_in_candidates, candidate, decision)
    VALID_DECISIONS = {"apply", "keep", "uncertain"}
    for i, (c, d) in enumerate(zip(candidates, decisions)):
        dec = d.get("decision", "")
        cid = d.get("candidate_id", "")
        if dec not in VALID_DECISIONS:
            print(f"Error: decision[{i}] has unexpected value: {dec}", file=sys.stderr)
            return 1
        if dec == "apply" and cid not in ("c1", f"apply_{i}"):
            print(f"Error: decision[{i}] apply with invalid candidate_id: {cid}. "
                  f"No safe match.", file=sys.stderr)
            return 1
        if dec == "apply":
            applies.append((i, c, d))

    print(f"{'='*60}")
    print(f"  Apply Polish Decisions")
    print(f"{'='*60}")
    print(f"  Candidates: {len(candidates)}")
    print(f"  Decisions:  {len(decisions)}")
    print(f"  To apply:   {len(applies)}")
    print()

    result_text = text
    ops: List[dict] = []
    successes = 0
    failures = 0

    for idx, (c_idx, cand, dec) in enumerate(applies):
        offset = cand.get("offset", -1)
        length = cand.get("length", 1)
        original_char = cand.get("original", "")
        candidate_char = cand.get("candidate", original_char)

        if offset < 0 or offset >= len(result_text):
            ops.append({
                "candidate_index": c_idx,
                "status": "skipped",
                "reason": f"invalid offset: {offset}",
            })
            failures += 1
            continue

        # Verify current char matches expected original
        actual = result_text[offset:offset + length]
        if actual != original_char:
            ops.append({
                "candidate_index": c_idx,
                "offset": offset,
                "original": original_char,
                "actual": actual,
                "status": "skipped",
                "reason": f"offset mismatch: expected {repr(original_char)}, got {repr(actual)}",
            })
            failures += 1
            continue

        # Apply
        patched = result_text[:offset] + candidate_char + result_text[offset + length:]

        # Quick verify
        verification_failures = quick_verify(patched, original_text, initial_non_std, initial_balance_diff)

        if verification_failures:
            ops.append({
                "candidate_index": c_idx,
                "decision_id": dec.get("case_id", ""),
                "offset": offset,
                "original": original_char,
                "candidate": candidate_char,
                "status": "rolled_back",
                "reason": "; ".join(verification_failures),
            })
            failures += 1
        else:
            result_text = patched
            ops.append({
                "candidate_index": c_idx,
                "decision_id": dec.get("case_id", ""),
                "offset": offset,
                "original": original_char,
                "candidate": candidate_char,
                "status": "applied",
                "reason": "",
            })
            successes += 1

        if (idx + 1) % 50 == 0 or idx == 0 or idx == len(applies) - 1:
            print(f"  [{idx+1}/{len(applies)}] {successes} applied, {failures} failed", file=sys.stderr)

    # Save final text
    save_text(args.output, result_text)
    print(f"\n  Final text saved: {args.output}")

    # Verify final state
    left = result_text.count("\u300c")
    right = result_text.count("\u300d")
    non_std = sum(1 for ch in result_text if ch in "[]\u3010\u3011{}\u300a\u300b\u201c\u201d")
    print(f"  Final quote balance: {left}/{right} {'[OK]' if left==right else '[NG]'}")
    print(f"  Final non-standard:  {non_std}")
    print(f"  Applied: {successes}, Failed/Rolled back: {failures}")

    # Save report
    if args.report:
        report = {
            "input": args.input,
            "output": args.output,
            "total_candidates": len(candidates),
            "to_apply": len(applies),
            "applied": successes,
            "failed": failures,
            "operations": ops,
            "final_quote_left": left,
            "final_quote_right": right,
            "final_non_standard": non_std,
        }
        Path(args.report).parent.mkdir(parents=True, exist_ok=True)
        with open(args.report, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        print(f"  Report saved: {args.report}")

    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())