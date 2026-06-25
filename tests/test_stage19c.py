"""Stage 19c 验证脚本：收窄 WrongSymbolDetector SmartSkip。"""
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
    errs = detect("详见[1]，他说：「你好」。")
    assert len(errs) == 0, [
        (item.offset, item.original_text, item.context_before, item.context_after)
        for item in errs
    ]
    results.append(("numeric footnote", "ok", "[1] skipped"))
except Exception as exc:
    errors.append(("numeric footnote", str(exc)))


try:
    errs = detect("这里有[注]，正文是「你好」。")
    assert len(errs) == 0, [
        (item.offset, item.original_text, item.context_before, item.context_after)
        for item in errs
    ]
    results.append(("explicit annotation", "ok", "[注] skipped"))
except Exception as exc:
    errors.append(("explicit annotation", str(exc)))


try:
    errs = detect("他说：[重要的事]必须现在决定。")
    offsets = {item.offset for item in errs}
    assert len(errs) == 2, [
        (item.offset, item.original_text, item.context_before, item.context_after)
        for item in errs
    ]
    assert offsets == {3, 8}
    assert all(not item.is_nested for item in errs)
    results.append(("short Chinese bracket", "ok", "[重要的事] detected"))
except Exception as exc:
    errors.append(("short Chinese bracket", str(exc)))


try:
    errs = detect("「这是[重要的事]，别忘了。」")
    offsets = {item.offset for item in errs}
    assert len(errs) == 2, [
        (item.offset, item.original_text, item.is_nested)
        for item in errs
    ]
    assert offsets == {3, 8}
    assert all(item.is_nested for item in errs)
    results.append(("nested short Chinese bracket", "ok", "detected with is_nested=True"))
except Exception as exc:
    errors.append(("nested short Chinese bracket", str(exc)))


print("=" * 55)
print("  Stage 19c Verification Report — SmartSkip")
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
