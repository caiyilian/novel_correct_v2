"""Stage 14 验证脚本：CorrectionVerifier 纠正确认器"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
results = []; errors = []
from src.core.error_record import ErrorRecord
from src.verifier.agent import CorrectionVerifier, VerifierResult

try: from src.verifier.agent import CorrectionVerifier, VerifierResult; results.append(("imports", "ok", "importable"))
except Exception as e: errors.append(("imports", str(e)))

v = CorrectionVerifier()
e = lambda t="wrong_symbol": ErrorRecord(error_type=t, line_number=1, offset=0)

# Test 2
try:
    r = v.verify(error=e(), original_text="[你好]「再见」", modified_text="「你好」「再见」")
    assert r.verdict == "pass"; results.append(("valid fix passes", "ok", f"verdict={r.verdict}"))
except Exception as ex: errors.append(("valid fix passes", str(ex)))

# Test 3
try:
    r = v.verify(error=e(), original_text="[你好]「再见」", modified_text="你好再见")
    assert r.verdict == "fail"; results.append(("brackets deleted fail", "ok", f"verdict={r.verdict}"))
except Exception as ex: errors.append(("brackets deleted fail", str(ex)))

# Test 4
try:
    r = v.verify(error=e(), original_text="[hi]", modified_text="「你好」" * 5)
    assert r.verdict == "fail"; results.append(("excessive length fail", "ok", f"verdict={r.verdict}"))
except Exception as ex: errors.append(("excessive length fail", str(ex)))

# Test 5
try:
    r = v.verify(error=e("consecutive"), original_text="」」", modified_text="」」")
    assert r.verdict == "fail"; results.append(("unfixed consecutive", "ok", f"verdict={r.verdict}"))
except Exception as ex: errors.append(("unfixed consecutive", str(ex)))

# Test 6
try:
    r = v.verify(error=e("consecutive"), original_text="」」", modified_text="」「「")
    assert r.verdict == "fail"; results.append(("remaining consecutive", "ok", f"verdict={r.verdict}"))
except Exception as ex: errors.append(("remaining consecutive", str(ex)))

# Test 7
try:
    err = e("wrong_symbol"); err.fix_applied = ""
    r = v.verify(error=err, original_text="[测试]「对话」", modified_text="[测试]「对话」")
    assert r.verdict == "fail"; results.append(("wrong symbol unchanged", "ok", f"verdict={r.verdict}"))
except Exception as ex: errors.append(("wrong symbol unchanged", str(ex)))

# Test 8
try:
    r = v.verify(error=e("consecutive"), original_text="「你好」", modified_text="「你好」")
    assert r.verdict == "pass"; results.append(("identical text passes", "ok", "no change"))
except Exception as ex: errors.append(("identical text passes", str(ex)))

# Test 9
try:
    r = v.verify(error=e(), original_text="[你好]", modified_text="「你好」")
    assert r.verdict == "pass"; results.append(("no LLM fallback", "ok", "rules alone"))
except Exception as ex: errors.append(("no LLM fallback", str(ex)))

# Test 10
try:
    r = v.verify(error=e("long_dialogue"), original_text="「你好。他走上前来。你好吗？」", modified_text="「你好。」他走上前来。「你好吗？」")
    assert r.verdict == "pass"; results.append(("dialogue split valid", "ok", "pass"))
except Exception as ex: errors.append(("dialogue split valid", str(ex)))

# Test 11
try:
    r = v.verify(error=e(), original_text="[test]", modified_text="「test」")
    assert hasattr(r, "verdict") and hasattr(r, "reason") and hasattr(r, "confidence")
    results.append(("VerifierResult structure", "ok", f"verdict={r.verdict}, confidence={r.confidence}"))
except Exception as ex: errors.append(("VerifierResult structure", str(ex)))

print("=" * 55)
print("  Stage 14 Verification Report — CorrectionVerifier")
print("=" * 55)
for n, s, d in results: print(f"  [OK] {n}: {d}")
for n, d in errors: print(f"  [FAIL] {n}: {d}")
print("=" * 55)
print(f"  {len(results)} passed, {len(errors)} failed")
print("=" * 55)
