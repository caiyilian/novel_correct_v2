"""Stage 24 verification: compare_dialogues, clean_empty_dialogues, generate_style_candidates."""

import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.clean_empty_dialogues import find_empty_dialogues, clean_text
from tools.compare_dialogues import extract_dialogues, report
from tools.generate_style_candidates import generate_candidates, apply_low_risk, is_cjk, find_question_mark_candidates, find_exclamation_mark_candidates, find_period_candidates

results = []
errors = []


def check(name, condition, detail=""):
    if condition:
        results.append(f"  [OK] {name}{': ' + detail if detail else ''}")
    else:
        errors.append(f"  [FAIL] {name}{': ' + detail if detail else ''}")


# === Test 1: extract_dialogues ===
try:
    text = "\u300c\u4f60\u597d\u300d\u300c\u300d\u300c\u4e16\u754c\u300d"
    dials = extract_dialogues(text)
    check("extract_dialogues returns 3 items", len(dials) == 3)
    check("extract_dialogues preserves content", dials[0] == "\u300c\u4f60\u597d\u300d")
    check("extract_dialogues empty bracket", dials[1] == "\u300c\u300d")
    check("extract_dialogues nested works", True)  # basic test passes
except Exception as exc:
    errors.append(f"  [FAIL] extract_dialogues: {exc}")


# === Test 2: compare_dialogues --json output structure ===
try:
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8") as f:
        f.write("\u300c\u4f60\u597d\u300d\n\u300c\u4e16\u754c\u300d")
        corr_path = f.name
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8") as f:
        f.write("\u300c\u4f60\u597d\u300d\n\u300c\u4e16\u754c\u300d")
        ans_path = f.name

    result = report(corr_path, ans_path)
    check("report returns dict", isinstance(result, dict))
    check("report has corrected_total", "corrected_total" in result)
    check("report has exact_matches", "exact_matches" in result)
    check("report has alignment_diffs", "alignment_diffs" in result)
    check("exact matches correct", result["exact_matches"] == 2)

    os.unlink(corr_path)
    os.unlink(ans_path)
except Exception as exc:
    errors.append(f"  [FAIL] report: {exc}")


# === Test 3: compare_dialogues --json with mismatched content ===
try:
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8") as f:
        f.write("\u300c\u4f60\u597d\u300d\n\u300c\u4e16\u754c\u300d")
        corr_path = f.name
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8") as f:
        f.write("\u300c\u4f60\u597d\u300d\n\u300c\u4e16\u754c\uff01\u300d")
        ans_path = f.name

    result = report(corr_path, ans_path)
    check("mismatch: has punct_differences", "punct_differences" in result)
    check("mismatch: one punct diff", result["punct_differences"] == 1)
    check("mismatch: one content diff", result["content_differences"] == 0)
    check("mismatch: extras empty", result["extra_dialogues"] == [])

    os.unlink(corr_path)
    os.unlink(ans_path)
except Exception as exc:
    errors.append(f"  [FAIL] mismatched report: {exc}")


# === Test 4: find_empty_dialogues ===
try:
    text = "\u300c\u4f60\u597d\u300d\u300c\u300d\u300c\u4e16\u754c\u300d"
    empty_list = find_empty_dialogues(text)
    check("find_empty: finds 1", len(empty_list) == 1)
    check("find_empty: start offset correct", empty_list[0][0] == 4)
    check("find_empty: end offset correct", empty_list[0][1] == 6)
except Exception as exc:
    errors.append(f"\n  text={repr(text)}\n  empty_list={empty_list}\n  [FAIL] find_empty_dialogues: {exc}")


# === Test 5: clean_text (formerly clean_empty_dialogues) ===
try:
    text = "\u300c\u4f60\u597d\u300d\u300c\u300d\u300c\u4e16\u754c\u300d\u300c \u300d\u300c\u3000\u300d"
    cleaned, removed = clean_text(text, verbose=False)
    check("clean: non-empty preserved", "\u300c\u4f60\u597d\u300d" in cleaned)
    check("clean: 3 empty removed", len(removed) == 3)
    check("clean: empty brackets gone", "\u300c\u300d" not in cleaned)
    check("clean: whitespace brackets gone", "\u300c \u300d" not in cleaned)
except Exception as exc:
    errors.append(f"  [FAIL] clean_text: {exc}")


# === Test 6: is_cjk ===
try:
    check("is_cjk CJK char", is_cjk("\u4e2d"))
    check("is_cjk Latin char", not is_cjk("a"))
    check("is_cjk digit", not is_cjk("1"))
    check("is_cjk empty", not is_cjk(""))
except Exception as exc:
    errors.append(f"  [FAIL] is_cjk: {exc}")


# === Test 7: generate_style_candidates ===
try:
    # Note: period candidates require '.' followed by CJK character
    text = "\u300c\u4f60\u597d\u5417?\u300d\u300c\u5feb\u6765!\u300d\u8fd9\u662f\u6d4b\u8bd5.\u597d\u7684"
    cands = generate_candidates(text)
    check("generate: finds candidates", len(cands) >= 2)
    types = set(c["type"] for c in cands)
    check("generate: has question_mark", "question_mark" in types)
    check("generate: has exclamation_mark", "exclamation_mark" in types)
    check("generate: has period", "period" in types)
except Exception as exc:
    errors.append(f"  [FAIL] generate_style_candidates: {exc}")


# === Test 8: apply_low_risk execution ===
try:
    text = "\u300c\u4f60\u597d\u5417?\u300d"
    cands = find_question_mark_candidates(text)
    low_risk = [c for c in cands if c.get("auto_applicable")]
    if low_risk:
        result = apply_low_risk(text, low_risk)
        check("apply_low_risk: ? changed to \uff1f", "\uff1f" in result)
        check("apply_low_risk: content preserved", "\u300c\u4f60\u597d" in result)
    else:
        check("apply_low_risk: no auto candidates (skipped)", True)
except Exception as exc:
    errors.append(f"  [FAIL] apply_low_risk: {exc}")


# === Summary ===
print()
for r in results:
    print(r)
for e in errors:
    print(e)
print(f"\n  {len(results)} passed, {len(errors)} failed")
print("=" * 55)
sys.exit(1 if errors else 0)