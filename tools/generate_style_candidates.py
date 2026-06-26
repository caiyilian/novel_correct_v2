"""
标点规范化候选生成器

扫描修正后的文本，生成标点风格规范的候选记录。
每条候选带风险等级：低风险可自动应用，高风险只输出不自动改。

用法:
    python tools/generate_style_candidates.py output/corrected_第1卷.txt
    python tools/generate_style_candidates.py output/corrected_第1卷.txt --candidates output/style_candidates.jsonl
    python tools/generate_style_candidates.py output/corrected_第1卷.txt --apply-low-risk --output output/corrected_第1卷_punct.txt
"""

import argparse
import json
import re
import sys
from pathlib import Path
from typing import List, Tuple, Optional


def is_cjk(ch: str) -> bool:
    """Check if character is CJK (Chinese/Japanese/Korean)."""
    if not ch:
        return False
    cp = ord(ch)
    return (
        (0x4E00 <= cp <= 0x9FFF) or
        (0x3400 <= cp <= 0x4DBF) or
        (0xF900 <= cp <= 0xFAFF) or
        (0x2E80 <= cp <= 0x2EFF)
    )


def is_latin(ch: str) -> bool:
    """Check if character is Latin letter or digit."""
    if not ch:
        return False
    return ch.isascii() and (ch.isalpha() or ch.isdigit())


def context_slice(text: str, pos: int, width: int = 20) -> Tuple[str, str, str]:
    """Get context before, current char, and context after."""
    start = max(0, pos - width)
    end = min(len(text), pos + 1 + width)
    before = text[start:pos]
    after = text[pos + 1:end]
    current = text[pos]
    return before, current, after


def find_question_mark_candidates(text: str) -> List[dict]:
    """Find ? in CJK context -> should be ？"""
    candidates = []
    for m in re.finditer(r"\?", text):
        pos = m.start()
        before = text[max(0, pos - 3):pos]
        after = text[pos + 1:pos + 4]
        has_cjk_before = any(is_cjk(ch) for ch in before)
        has_cjk_after = any(is_cjk(ch) for ch in after)

        # Low risk: between CJK characters (or CJK before + 」 after, etc.)
        if has_cjk_before:
            ctx_before, _, ctx_after = context_slice(text, pos)
            risk = "low" if has_cjk_before else "high"
            candidates.append({
                "type": "question_mark",
                "offset": pos,
                "original": "?",
                "candidate": "？",
                "context_before": ctx_before[-20:],
                "context_after": ctx_after[:20],
                "risk_level": risk,
                "auto_applicable": risk == "low",
            })
    return candidates


def find_exclamation_mark_candidates(text: str) -> List[dict]:
    """Find ! in CJK context -> should be ！"""
    candidates = []
    for m in re.finditer(r"!", text):
        pos = m.start()
        before = text[max(0, pos - 3):pos]
        after = text[pos + 1:pos + 4]
        has_cjk_before = any(is_cjk(ch) for ch in before)
        has_cjk = has_cjk_before or any(is_cjk(ch) for ch in after)

        if has_cjk:
            ctx_before, _, ctx_after = context_slice(text, pos)
            risk = "low" if has_cjk_before else "high"
            candidates.append({
                "type": "exclamation_mark",
                "offset": pos,
                "original": "!",
                "candidate": "！",
                "context_before": ctx_before[-20:],
                "context_after": ctx_after[:20],
                "risk_level": risk,
                "auto_applicable": risk == "low",
            })
    return candidates


def find_tilde_candidates(text: str) -> List[dict]:
    """Find consecutive ~ -> ～"""
    candidates = []
    for m in re.finditer(r"~+", text):
        pos = m.start()
        length = m.end() - m.start()
        ctx_before, _, ctx_after = context_slice(text, pos)
        candidates.append({
            "type": "tilde",
            "offset": pos,
            "length": length,
            "original": "~" * length,
            "candidate": "～" * length,
            "context_before": ctx_before[-20:],
            "context_after": ctx_after[:20],
            "risk_level": "low",
            "auto_applicable": True,
        })
    return candidates


def find_period_candidates(text: str) -> List[dict]:
    """Find . at sentence end -> ？ or ！ or 。
    High risk: need context to determine. Only mark obvious candidates.
    """
    candidates = []
    # Check for '.' followed by CJK or 「 (likely sentence end)
    for m in re.finditer(r"\.(?=[\u300c\s\u4e00-\u9fff])", text):
        pos = m.start()
        # Skip if part of ...
        if text[max(0, pos - 2):pos] == "..":
            continue
        # Skip if part of number (e.g., 3.14)
        if pos > 0 and (text[pos - 1].isdigit() or is_latin(text[pos - 1])):
            if pos + 1 < len(text) and (text[pos + 1].isdigit() or is_latin(text[pos + 1])):
                continue
        ctx_before, _, ctx_after = context_slice(text, pos)
        # Only if CJK context
        if any(is_cjk(ch) for ch in text[max(0, pos - 5):pos]):
            candidates.append({
                "type": "period",
                "offset": pos,
                "original": ".",
                "candidate": "。",
                "context_before": ctx_before[-20:],
                "context_after": ctx_after[:20],
                "risk_level": "high",
                "auto_applicable": False,
            })
    return candidates


def generate_candidates(text: str) -> List[dict]:
    """Generate all punctuation normalization candidates."""
    candidates = []
    candidates.extend(find_question_mark_candidates(text))
    candidates.extend(find_exclamation_mark_candidates(text))
    candidates.extend(find_tilde_candidates(text))
    candidates.extend(find_period_candidates(text))
    candidates.sort(key=lambda c: c["offset"])
    return candidates


def apply_low_risk(text: str, candidates: List[dict]) -> str:
    """Apply all low-risk candidates to the text."""
    # Apply in reverse order to preserve offsets
    result = list(text)
    for c in reversed(candidates):
        if c["auto_applicable"]:
            length = c.get("length", 1)
            for i in range(length):
                result[c["offset"] + i] = c["candidate"][i] if len(c["candidate"]) == length else c["candidate"]
    return "".join(result)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", help="corrected novel file path")
    parser.add_argument("--candidates", default="", help="output JSONL path for candidates")
    parser.add_argument("--apply-low-risk", action="store_true", help="apply low-risk candidates to text")
    parser.add_argument("--output", default="", help="output file path (with --apply-low-risk)")
    args = parser.parse_args()

    if not Path(args.input).exists():
        print(f"Error: input file not found: {args.input}", file=sys.stderr)
        return 1

    with open(args.input, "r", encoding="utf-8-sig") as f:
        text = f.read()

    candidates = generate_candidates(text)

    # Summary
    low = [c for c in candidates if c["auto_applicable"]]
    high = [c for c in candidates if not c["auto_applicable"]]
    by_type: dict = {}
    for c in candidates:
        t = c["type"]
        by_type.setdefault(t, {"low": 0, "high": 0})
        by_type[t]["low" if c["auto_applicable"] else "high"] += 1

    print(f"{'='*60}")
    print(f"  标点规范化候选生成")
    print(f"{'='*60}")
    print(f"  文件: {args.input}")
    print(f"  总候选: {len(candidates)}")
    print(f"    低风险（可自动应用）: {len(low)}")
    print(f"    高风险（需人工/LLM）: {len(high)}")
    print()
    print(f"  按类型:")
    for t, counts in sorted(by_type.items()):
        print(f"    {t:20s}: low={counts['low']}, high={counts['high']}")

    if args.candidates:
        Path(args.candidates).parent.mkdir(parents=True, exist_ok=True)
        with open(args.candidates, "w", encoding="utf-8") as f:
            for c in candidates:
                f.write(json.dumps(c, ensure_ascii=False) + "\n")
        print(f"\n  Candidates saved: {args.candidates}")

    if args.apply_low_risk:
        if not args.output:
            print("  Error: --output required with --apply-low-risk", file=sys.stderr)
            return 1
        result = apply_low_risk(text, candidates)
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(result)
        # Quick stats
        orig_q = text.count("?") + text.count("!")
        new_q = result.count("？") + result.count("！")
        print(f"\n  低风险已应用并保存: {args.output}")
        print(f"    ?+!  原: {orig_q}  → ？+！: {new_q}")
        print(f"    ~    原: {text.count('~')}  → ～: {result.count('～')}")

    return 0


if __name__ == "__main__":
    sys.exit(main())