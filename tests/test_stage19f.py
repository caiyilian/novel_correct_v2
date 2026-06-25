"""Stage 19f verification: first-volume quality gate."""

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.verify_stage19f_quality import (  # noqa: E402
    check_thresholds,
    quality_report,
    quick_similarity,
)


results = []
errors = []


def check(name, condition, detail=""):
    if condition:
        results.append(f"  [OK] {name}{': ' + detail if detail else ''}")
    else:
        errors.append(f"  [FAIL] {name}{': ' + detail if detail else ''}")


print("=" * 55)
print("  Stage 19f Verification Report — Quality Gate")
print("=" * 55)

with tempfile.TemporaryDirectory() as tmp:
    tmp_path = Path(tmp)
    corrected = tmp_path / "corrected.txt"
    answer = tmp_path / "answer.txt"
    corrected.write_text(
        "\u300c\u4f60\u597d\u300d\n"
        "\u300c\u8fd9\u662f\u4e00\u6bb5\u5bf9\u8bdd\u300d\n",
        encoding="utf-8",
    )
    answer.write_text(
        "\u300c\u4f60\u597d\u300d\n"
        "\u300c\u8fd9\u662f\u4e00\u6bb5\u5bf9\u8bdd\u300d\n",
        encoding="utf-8",
    )

    report = quality_report(corrected, answer)
    failures = check_thresholds(
        report,
        max_non_standard=1,
        min_quote_count=2,
        min_answer_match=0.9,
    )
    check("balanced quote counts", report["quote_balanced"], str(report))
    check("non-standard total is zero", report["non_standard_total"] == 0)
    check("answer similarity passes", report["answer_match_ignore_whitespace"] == 1.0)
    check("thresholds pass", failures == [], str(failures))

with tempfile.TemporaryDirectory() as tmp:
    tmp_path = Path(tmp)
    corrected = tmp_path / "corrected_bad.txt"
    corrected.write_text(
        "\u300c\u4f60\u597d\u3011\n",
        encoding="utf-8",
    )
    report = quality_report(corrected)
    failures = check_thresholds(
        report,
        max_non_standard=1,
        min_quote_count=1,
        min_answer_match=0.9,
    )
    check("detects non-standard symbol", report["non_standard_total"] == 1)
    check("detects threshold failure", bool(failures), str(failures))

base = "\u7f57\u4f26\u65af\u8bf4\u4f60\u597d\u7136\u540e\u7ee7\u7eed\u524d\u8fdb" * 5
similarity = quick_similarity(
    base,
    base[:20] + "\u4e86" + base[20:],
)
check("bigram similarity tolerates insertion", similarity > 0.9, f"{similarity:.4f}")

print()
for r in results:
    print(r)
for e in errors:
    print(e)
print(f"\n  {len(results)} passed, {len(errors)} failed")
print("=" * 55)
sys.exit(1 if errors else 0)
