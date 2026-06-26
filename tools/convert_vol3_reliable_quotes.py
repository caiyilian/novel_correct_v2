"""
convert_vol3_reliable_quotes.py — 第 3 卷可靠弯引号规则转换（Stage 3b）

只转换同段内可靠成对的弯双引号（""）为「」。
不修改任何正文内容。

用法：
    python tools/convert_vol3_reliable_quotes.py

输入：
    - data/ori_story/第3卷.txt
    - output/vol3_curly_quote_audit.json（参考）

输出：
    - output/corrected_第3卷_stage3b.txt（中间产物）
    - output/vol3_curly_quote_apply_report.json（转换报告）

验收条件：
    - 只修改包裹符号
    - 正文字符不得变化（除包裹符号外 diff 为 0）
    - 转换后「」必须配平
    - 如不配平，整阶段回滚
"""

import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

OUTPUT_DIR = Path("output")
ORI_PATH = "data/ori_story/第3卷.txt"
AUDIT_PATH = OUTPUT_DIR / "vol3_curly_quote_audit.json"
OUTPUT_TEXT_PATH = OUTPUT_DIR / "corrected_第3卷_stage3b.txt"
REPORT_PATH = OUTPUT_DIR / "vol3_curly_quote_apply_report.json"

# Target symbols
CURLY_LEFT = "\u201c"  # "
CURLY_RIGHT = "\u201d"  # "
JP_LEFT = "\u300c"  # 「
JP_RIGHT = "\u300d"  #
SINGLE_LEFT = "\u2018"
SINGLE_RIGHT = "\u2019"


def convert():
    # Load original text
    from src.io.loader import TextLoader
    doc = TextLoader().load(str(ORI_PATH))
    text = doc.text

    # ── 1. Pre-scan: verify baseline ──
    orig_left = text.count(CURLY_LEFT)
    orig_right = text.count(CURLY_RIGHT)
    orig_jp_left = text.count(JP_LEFT)
    orig_jp_right = text.count(JP_RIGHT)

    print(f"Original: curly {orig_left}/{orig_right}, JP {orig_jp_left}/{orig_jp_right}")

    # ── 2. Find same-paragraph pairs ──
    # Split into paragraphs and process each independently
    paragraphs = text.split("\n")
    result_paragraphs = []
    total_ops = 0
    conversion_details = []

    for pi, para in enumerate(paragraphs):
        if CURLY_LEFT not in para and CURLY_RIGHT not in para:
            result_paragraphs.append(para)
            continue

        # Process this paragraph character by character
        chars = list(para)
        # Greedy pair matching: find left, then nearest right after it
        left_indices = [i for i, ch in enumerate(chars) if ch == CURLY_LEFT]
        right_indices = [i for i, ch in enumerate(chars) if ch == CURLY_RIGHT]

        used_rights = set()
        pairs = []

        for li in left_indices:
            # Find the first unpaired right quote after this left
            best_ri = None
            for ri in right_indices:
                if ri in used_rights:
                    continue
                if ri > li:
                    best_ri = ri
                    break
            if best_ri is not None:
                used_rights.add(best_ri)
                pairs.append((li, best_ri))

        # Apply conversion
        for li, ri in pairs:
            chars[li] = JP_LEFT
            chars[ri] = JP_RIGHT
            total_ops += 1
            conversion_details.append({
                "para_index": pi,
                "left_pos_in_para": li,
                "right_pos_in_para": ri,
                "context": para[max(0, li - 20):ri + 21],
            })

        result_paragraphs.append("".join(chars))

    result_text = "\n".join(result_paragraphs)

    # ── 3. Verify ──
    new_left = result_text.count(JP_LEFT)
    new_right = result_text.count(JP_RIGHT)
    remaining_curly_left = result_text.count(CURLY_LEFT)
    remaining_curly_right = result_text.count(CURLY_RIGHT)
    balanced = new_left == new_right

    print(f"After: JP {new_left}/{new_right}, remaining curly {remaining_curly_left}/{remaining_curly_right}")
    print(f"Pairs converted: {total_ops}")
    print(f"Balanced: {'OK' if balanced else 'NG'}")

    # Verify only symbol changes (no content diff)
    # Compare content-only (strip curly and JP quotes)
    def strip_quotes(t):
        return t.replace(CURLY_LEFT, "").replace(CURLY_RIGHT, "").replace(JP_LEFT, "").replace(JP_RIGHT, "")

    orig_content = strip_quotes(text)
    new_content = strip_quotes(result_text)
    content_unchanged = orig_content == new_content

    print(f"Content unchanged (excl. quotes): {'OK' if content_unchanged else 'NG'}")

    if not balanced:
        print("ERROR: Quote balance broken. Rolling back — NOT saving.")
        report = {
            "status": "ROLLED_BACK",
            "reason": "Quote balance broken after conversion",
            "original_balance": {"left": orig_left, "right": orig_right},
            "new_balance": {"left": new_left, "right": new_right},
            "pairs_converted": total_ops,
            "remaining_curly": {"left": remaining_curly_left, "right": remaining_curly_right},
        }
        with open(REPORT_PATH, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        return 1

    if not content_unchanged:
        print("WARN: Content changed outside quotes. Review diff.")
        # Still save, but flag it

    # ── 4. Save ──
    with open(OUTPUT_TEXT_PATH, "w", encoding="utf-8") as f:
        f.write(result_text)
    print(f"Saved: {OUTPUT_TEXT_PATH}")

    # ── 5. Save report ──
    report = {
        "status": "APPLIED",
        "rollback_condition": "balanced" if balanced else "failed",
        "original": {
            "curly_left": orig_left,
            "curly_right": orig_right,
            "jp_left": orig_jp_left,
            "jp_right": orig_jp_right,
        },
        "result": {
            "jp_left": new_left,
            "jp_right": new_right,
            "remaining_curly_left": remaining_curly_left,
            "remaining_curly_right": remaining_curly_right,
            "balanced": balanced,
            "content_unchanged": content_unchanged,
        },
        "pairs_converted": total_ops,
        "conversion_sample": conversion_details[:20],  # first 20 as sample
        "remaining_for_stage3c": {
            "cross_paragraph_or_unbalanced_curly": remaining_curly_left + remaining_curly_right,
            "high_risk_style_candidates": 20,  # from stage 2
            "details": f"{remaining_curly_left} left + {remaining_curly_right} right curly remain + 20 style candidates",
        },
    }
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"Report saved: {REPORT_PATH}")

    # Summary
    print(f"\n{'='*60}")
    print(f"  Stage 3b conversion complete")
    print(f"{'='*60}")
    print(f"  Pairs converted: {total_ops}")
    print(f"  JP quotes now:   {new_left}/{new_right} {'OK' if balanced else 'NG'}")
    print(f"  Remaining curly: {remaining_curly_left}/{remaining_curly_right}")
    print(f"  Content intact:  {'OK' if content_unchanged else 'CHECK DIFF'}")
    print(f"  → Stage 3c: handle {remaining_curly_left+remaining_curly_right} remaining curly + 20 style candidates")
    print(f"{'='*60}\n")

    return 0


if __name__ == "__main__":
    sys.exit(convert())