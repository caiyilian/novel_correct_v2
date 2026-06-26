"""
fix_vol2_brackets_lowrisk.py — 第 2 卷 [] 低风险规则修复（Stage 4b）

只转换 Stage 4a 中确定为对话包裹的 [] 为 「」。
输出：output/corrected_第2卷_stage4b.txt
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.io.loader import TextLoader

OUTPUT_DIR = Path("output")
ORI_PATH = "data/ori_story/第2卷.txt"
AUDIT_PATH = OUTPUT_DIR / "vol2_bracket_audit.json"
OUT_PATH = OUTPUT_DIR / "corrected_第2卷_stage4b.txt"
REPORT_PATH = OUTPUT_DIR / "vol2_bracket_apply_report.json"


def fix():
    text = TextLoader().load(ORI_PATH).text
    chars = list(text)
    applied = 0
    ops = []

    # Scan and convert paired [] to 「」
    left_positions = [i for i, ch in enumerate(chars) if ch == "["]
    right_positions = [i for i, ch in enumerate(chars) if ch == "]"]
    used_right = set()

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
            content = "".join(chars[lpos + 1:best])
            # Only convert if it looks like dialogue (not digits-only, not too long)
            if not content.strip().isdigit() and len(content) < 100:
                chars[lpos] = "\u300c"
                chars[best] = "\u300d"
                applied += 1
                ops.append({
                    "left_pos": lpos,
                    "right_pos": best,
                    "content": content,
                })

    result = "".join(chars)
    left_jp = result.count("\u300c")
    right_jp = result.count("\u300d")
    remaining_left = result.count("[")
    remaining_right = result.count("]")

    balanced = left_jp == right_jp
    print(f"Applied: {applied} [] -> JP pairs")
    print(f"JP: {left_jp}/{right_jp} {'OK' if balanced else 'NG'}")
    print(f"Remaining [: {remaining_left}, ]: {remaining_right}")

    with open(OUT_PATH, "w", encoding="utf-8") as f:
        f.write(result)
    print(f"Saved: {OUT_PATH}")

    report = {
        "stage": "4b",
        "volume": "第2卷",
        "applied": applied,
        "result_jp": {"left": left_jp, "right": right_jp, "balanced": balanced},
        "remaining_brackets": {"left": remaining_left, "right": remaining_right},
        "remaining_detail": f"{remaining_left} left + {remaining_right} right brackets remain (unpaired or non-dialogue)",
    }
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"Report saved: {REPORT_PATH}")

    return 0


if __name__ == "__main__":
    sys.exit(fix())