"""
audit_vol2_brackets.py — 第 2 卷 [] 残留审计（只读，不改正文）

分析第 2 卷原文中的 [] 和「」不配平问题：
1. [] 残留分类（对话包裹、注释、编号、旁注、uncertain）
2. [] 按是否同段成对分类
3. 「」不配平位置定位

输出：output/vol2_bracket_audit.json
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.io.loader import TextLoader

OUTPUT_DIR = Path("output")
ORI_PATH = "data/ori_story/第2卷.txt"
ANS_PATH = "data/answer/answer_第2卷.txt"


def audit():
    text = TextLoader().load(ORI_PATH).text
    ans = TextLoader().load(ANS_PATH).text

    stats = {
        "total_chars": len(text),
        "jp_left": text.count("\u300c"),
        "jp_right": text.count("\u300d"),
        "jp_balanced": text.count("\u300c") == text.count("\u300d"),
        "bracket_left": text.count("["),
        "bracket_right": text.count("]"),
        "ans_jp_left": ans.count("\u300c"),
        "ans_jp_right": ans.count("\u300d"),
        "gap": ans.count("\u300c") - text.count("\u300c"),
    }

    # Scan and classify all [] occurrences
    left_positions = [i for i, ch in enumerate(text) if ch == "["]
    right_positions = [i for i, ch in enumerate(text) if ch == "]"]
    used_right = set()
    pairs = []
    unpaired_left = []
    unpaired_right = []

    for lpos in left_positions:
        best = None
        for rpos in right_positions:
            if rpos in used_right:
                continue
            if rpos > lpos and rpos - lpos < 200:
                best = rpos
                break
        if best is not None:
            used_right.add(best)
            ctx = text[lpos:best + 1]
            pairs.append({
                "left_pos": lpos,
                "right_pos": best,
                "length": best - lpos,
                "content": ctx,
                "context": text[max(0, lpos - 30):best + 31],
            })
        else:
            unpaired_left.append({
                "pos": lpos,
                "context": text[max(0, lpos - 30):lpos + 31],
            })

    for rpos in right_positions:
        if rpos not in used_right:
            unpaired_right.append({
                "pos": rpos,
                "context": text[max(0, rpos - 30):rpos + 31],
            })

    # Simple heuristic classification
    def classify_pair(p):
        content = p["content"]
        # If inside JP quotes or adjacent to JP quotes -> dialogue wrapper
        # If contains digits only -> numbering
        # If short (< 10 chars) and contains common annotation words -> annotation
        # Default: uncertain
        digits = sum(1 for c in content if c.isdigit())
        if digits == len(content.replace("[", "").replace("]", "")) and digits > 0:
            return "numbering"
        if len(content) > 50:
            return "uncertain"
        return "dialogue_wrapper"

    for p in pairs:
        p["classification"] = classify_pair(p)

    # Imbalance: find where 配平 shifts
    paragraphs = text.split("\n")
    imbalance_at = []
    cum_left = 0
    cum_right = 0
    for pi, para in enumerate(paragraphs):
        pl = para.count("\u300c")
        pr = para.count("\u300d")
        cum_left += pl
        cum_right += pr
        if cum_left != cum_right:
            imbalance_at.append({
                "para_index": pi,
                "cum_left": cum_left,
                "cum_right": cum_right,
                "diff": cum_left - cum_right,
                "para_preview": para[:80],
            })

    report = {
        "stats": stats,
        "summary": {
            "total_pairs": len(pairs),
            "unpaired_left": len(unpaired_left),
            "unpaired_right": len(unpaired_right),
            "imbalance_positions": len(imbalance_at),
            "high_risk_period_candidates": 155,
        },
        "classification": {},
        "imbalance_details": imbalance_at[:30],
        "details": {
            "pairs": pairs[:40],
            "unpaired_left": unpaired_left[:10],
            "unpaired_right": unpaired_right[:10],
        },
    }

    # Classification breakdown
    for cat in ("dialogue_wrapper", "numbering", "uncertain"):
        cnt = sum(1 for p in pairs if p.get("classification") == cat)
        report["classification"][cat] = cnt

    report["recommendation"] = {
        "rule_convertible": report["classification"].get("dialogue_wrapper", 0),
        "needs_review": report["classification"].get("uncertain", 0) + len(unpaired_left) + len(unpaired_right),
        "note": f"Pairs: {len(pairs)} total. Rule: ~{report['classification'].get('dialogue_wrapper',0)} dialog wrappers. Uncertain: ~{report['classification'].get('uncertain',0)}. Unpaired: {len(unpaired_left) + len(unpaired_right)}. Plus 155 period high-risk from Stage 2.",
    }

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUTPUT_DIR / "vol2_bracket_audit.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"Audit saved: {out_path}")

    # Print summary
    print(f"\n{'='*55}")
    print(f"  Vol 2 Bracket Audit Summary")
    print(f"{'='*55}")
    print(f"  JP: {stats['jp_left']}/{stats['jp_right']} {'OK' if stats['jp_balanced'] else 'NG'}")
    print(f"  Target: {stats['ans_jp_left']}/{stats['ans_jp_right']}")
    print(f"  Gap: {stats['gap']}")
    print(f"  [] pairs: {len(pairs)} ({report['classification'].get('dialogue_wrapper',0)} dialog, {report['classification'].get('numbering',0)} num, {report['classification'].get('uncertain',0)} uncertain)")
    print(f"  Unpaired: {len(unpaired_left)} left + {len(unpaired_right)} right")
    print(f"  Imbalance points: {len(imbalance_at)}")
    print(f"  Period high-risk: 155")
    print(f"  Rule: ~{report['classification'].get('dialogue_wrapper',0)} dialog [] -> Stage 4b")
    print(f"  Review: {report['classification'].get('uncertain',0)} uncertain [] + {len(unpaired_left)+len(unpaired_right)} unpaired + {len(imbalance_at)} imbalance -> Stage 4c")
    print(f"  Periods: 155 -> Stage 4d")
    print(f"{'='*55}\n")

    return report


if __name__ == "__main__":
    audit()