"""Stage 19d 验证脚本：弯引号与孤立 ASCII 引号覆盖。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.core.text import TextDoc
from src.detector.wrong_symbol import WrongSymbolDetector


results = []
errors = []


def detect(text: str):
    return WrongSymbolDetector().detect(TextDoc(text))


try:
    errs = detect("他说：“你好”。")
    assert len(errs) == 2, [
        (item.offset, item.original_text, item.is_nested)
        for item in errs
    ]
    assert {item.offset for item in errs} == {3, 6}
    assert all(not item.is_nested for item in errs)
    results.append(("curly quotes", "ok", "detected opening and closing curly quotes"))
except Exception as exc:
    errors.append(("curly quotes", str(exc)))


try:
    errs = detect("「他说“你好”。」")
    assert len(errs) == 2, [
        (item.offset, item.original_text, item.is_nested)
        for item in errs
    ]
    assert {item.offset for item in errs} == {3, 6}
    assert all(item.is_nested for item in errs)
    results.append(("nested curly quotes", "ok", "detected with is_nested=True"))
except Exception as exc:
    errors.append(("nested curly quotes", str(exc)))


try:
    errs = detect('他说："你好')
    assert len(errs) == 1, [
        (item.offset, item.original_text, item.is_nested)
        for item in errs
    ]
    assert errs[0].offset == 3
    assert not errs[0].is_nested
    results.append(("unmatched ASCII quote", "ok", "single quote detected"))
except Exception as exc:
    errors.append(("unmatched ASCII quote", str(exc)))


try:
    errs = detect('「他说："你好。」')
    assert len(errs) == 1, [
        (item.offset, item.original_text, item.is_nested)
        for item in errs
    ]
    assert errs[0].offset == 4
    assert errs[0].is_nested
    results.append(("nested unmatched ASCII quote", "ok", "single quote detected with is_nested=True"))
except Exception as exc:
    errors.append(("nested unmatched ASCII quote", str(exc)))


print("=" * 55)
print("  Stage 19d Verification Report — Quote Coverage")
print("=" * 55)
for name, status, detail in results:
    print(f"  [OK] {name}: {detail}")
for name, detail in errors:
    print(f"  [FAIL] {name}: {detail}")
print("=" * 55)
print(f"  {len(results)} passed, {len(errors)} failed")
print("=" * 55)

if errors:
    raise SystemExit(1)
