"""
vol3_convergence_check.py — Stage 3d: Verify Vol 3 convergence state

Runs the full verification suite on the Stage 3c output and documents results.
"""

import json
import subprocess
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))
sys.path.insert(0, str(BASE / "tools"))

OUTPUT_DIR = BASE / "output"
ORI_PATH = BASE / "data/ori_story/第3卷.txt"
STAGE3C_PATH = OUTPUT_DIR / "corrected_第3卷_stage3c.txt"
ANS_PATH = BASE / "data/answer/answer_第3卷.txt"


def check():
    from compare_dialogues import report as compare_report
    from verify_against_answer import generate_report as verify_report

    # ── Stats ──
    text = open(STAGE3C_PATH, encoding="utf-8").read()
    jp_left = text.count("\u300c")
    jp_right = text.count("\u300d")
    curly_left = text.count("\u201c")
    curly_right = text.count("\u201d")
    non_std = sum(1 for ch in text if ch in "[]【】［］{}\u300a\u300b\u201c\u201d")

    print(f"{'='*60}")
    print(f"  Stage 3d: Vol 3 Convergence Verification")
    print(f"{'='*60}")
    print(f"  JP quotes:  {jp_left}/{jp_right} {'OK' if jp_left==jp_right else 'NG'}")
    print(f"  Target:     1215/1215")
    print(f"  Gap:        {1215 - jp_left} segments")
    print(f"  Curly:      {curly_left}/{curly_right}")
    print(f"  Non-std:    {non_std}")
    print(f"  Target met: {'YES' if jp_left==1215 and jp_right==1215 else 'NO'}")

    # ── compare_dialogues ──
    print(f"\n  [compare_dialogues]...", end=" ")
    try:
        cmp = compare_report(
            corrected_path=str(STAGE3C_PATH),
            answer_path=str(ANS_PATH),
            json_path=str(OUTPUT_DIR / "compare_第3卷_stage3d.json"),
            align=False,
        )
        print(f"extracted {cmp['corrected_total']}/{cmp['answer_total']}")
    except Exception as e:
        print(f"ERROR: {e}")
        cmp = None

    # ── verify_against_answer ──
    print(f"  [verify_against_answer]...", end=" ")
    try:
        vrf = verify_report(
            corrected_path=str(STAGE3C_PATH),
            answer_path=str(ANS_PATH),
        )
        print(f"match rate: {vrf['matching']['match_rate']:.4f}")
    except Exception as e:
        print(f"ERROR: {e}")
        vrf = None

    # ── main.py --detect ──
    print(f"  [main.py --detect]...", end=" ")
    try:
        r = subprocess.run(
            [sys.executable, "main.py", str(ORI_PATH), "--detect"],
            capture_output=True, text=True, timeout=120,
        )
        for line in r.stdout.split("\n"):
            if "Total:" in line and "errors" in line:
                import re
                m = re.search(r"Total:\s*(\d+)", line)
                if m:
                    print(f"{m.group(1)} errors detected")
                    detected = int(m.group(1))
                    break
        else:
            print("no total found")
            detected = -1
    except Exception as e:
        print(f"ERROR: {e}")
        detected = -1

    # ── Report ──
    report = {
        "stage": "3d",
        "volume": "第3卷",
        "target_jp": 1215,
        "current_jp": {"left": jp_left, "right": jp_right, "balanced": jp_left == jp_right},
        "gap": 1215 - jp_left,
        "remaining_curly": {"left": curly_left, "right": curly_right},
        "remaining_non_standard": non_std,
        "target_met": jp_left == 1215 and jp_right == 1215,
        "conclusion": "NOT_YET_CONVERGED — need Stage 3d-2 to locate 32 missing segments",
        "comparison": {
            "corrected_total": cmp["corrected_total"] if cmp else 0,
            "answer_total": cmp["answer_total"] if cmp else 0,
        } if cmp else None,
        "match_rate": round(vrf["matching"]["match_rate"], 4) if vrf else None,
        "detected_errors": detected,
    }

    out_path = OUTPUT_DIR / "verify_第3卷_stage3d.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"\n  Report saved: {out_path}")

    print(f"\n{'='*60}")
    print(f"  Conclusion: {report['conclusion']}")
    print(f"{'='*60}\n")

    return report


if __name__ == "__main__":
    check()