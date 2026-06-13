"""Stage 6 验证脚本：ConsecutiveDetector 连续符号检测器"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

results = []
errors = []

from src.core.text import TextDoc
from src.detector.base import BaseDetector
from src.detector.consecutive import ConsecutiveDetector

# Test 1: 导入
try:
    from src.detector.base import BaseDetector
    from src.detector.consecutive import ConsecutiveDetector
    results.append(("imports", "ok", "BaseDetector, ConsecutiveDetector importable"))
except Exception as e:
    errors.append(("imports", str(e)))

# Test 2: 正确交替文本 — 无错误
try:
    text = "「你好」他说道。「我很好」谢谢。「再见」"
    doc = TextDoc(text, encoding="utf-8")
    detector = ConsecutiveDetector()
    errs = detector.detect(doc)
    assert len(errs) == 0, f"expected 0 errors, got {len(errs)}"
    results.append(("correct alternation", "ok", "no false positives"))
except Exception as e:
    errors.append(("correct alternation", str(e)))

# Test 3: 连续两个 」— 应有 1 个错误
try:
    text = "「你好」他说道。」我很好」"
    doc = TextDoc(text, encoding="utf-8")
    detector = ConsecutiveDetector()
    errs = detector.detect(doc)
    assert len(errs) >= 1, f"expected >= 1 error, got {len(errs)}"
    # 检查错误的类型和位置
    e = errs[0]
    assert e.error_type == "consecutive"
    assert "」" in e.original_text
    results.append(("consecutive 」」", "ok", f"offset={e.offset}, text={e.original_text!r}"))
except Exception as e:
    errors.append(("consecutive 」」", str(e)))

# Test 4: 连续两个「— 应有 1 个错误（「你好「 → 第二个「与第一个「连续）
try:
    text = "「你好「他说道。「我很好」"
    doc = TextDoc(text, encoding="utf-8")
    detector = ConsecutiveDetector()
    errs = detector.detect(doc)
    assert len(errs) >= 1, f"expected >= 1 error, got {len(errs)}"
    e = errs[0]
    assert e.error_type == "consecutive"
    # 验证检测到的是「连续: 第二个「的位置前一个符号也是「
    # text: 「(0) 你好「(3) 他说道。「(8) 我很好」(12)
    # offset 3 和 offset 8 都是"连续「"错误（前一个是「）
    assert e.offset in (3, 8), f"unexpected offset {e.offset}"
    assert text[e.offset] == "「"
    results.append(("consecutive 「「", "ok",
                    f"offset={e.offset}, before={text[e.offset-1]!r}, text={e.original_text!r}"))
except Exception as e:
    errors.append(("consecutive 「「", str(e)))

# Test 5: 跨行连续符号
try:
    text = "「你好\n」他说道。」"
    doc = TextDoc(text, encoding="utf-8")
    detector = ConsecutiveDetector()
    errs = detector.detect(doc)
    assert len(errs) >= 1, f"expected >= 1 error, got {len(errs)}"
    results.append(("cross-line consecutive", "ok", f"detected {len(errs)} error(s)"))
except Exception as e:
    errors.append(("cross-line consecutive", str(e)))

# Test 6: 连续多个错误
try:
    # 故意构造多个连续错误
    text = "「「「「"
    doc = TextDoc(text, encoding="utf-8")
    detector = ConsecutiveDetector()
    errs = detector.detect(doc)
    # 第一个「是开符号，第二个「是连续（错误），第三个「又是连续...
    assert len(errs) >= 1, f"expected >= 1 errors, got {len(errs)}"
    results.append(("multiple consecutive", "ok", f"{len(errs)} consecutive errors detected"))
except Exception as e:
    errors.append(("multiple consecutive", str(e)))

# Test 7: 正确交替的长文本
try:
    text = "「第一句」叙述。「第二句」叙述。「第三句」"
    doc = TextDoc(text, encoding="utf-8")
    detector = ConsecutiveDetector()
    errs = detector.detect(doc)
    assert len(errs) == 0, f"expected 0 errors, got {len(errs)}"
    results.append(("long correct alternation", "ok", "no false positives"))
except Exception as e:
    errors.append(("long correct alternation", str(e)))

# Test 8: 混合错误——既有 「「 也有 」」
try:
    text = "「第一句「第二句」第三句」第四句」"
    doc = TextDoc(text, encoding="utf-8")
    detector = ConsecutiveDetector()
    errs = detector.detect(doc)
    assert len(errs) >= 2, f"expected >= 2 errors, got {len(errs)}"
    results.append(("mixed consecutive errors", "ok", f"{len(errs)} errors detected"))
except Exception as e:
    errors.append(("mixed consecutive errors", str(e)))

# Test 9: 空文本
try:
    text = ""
    doc = TextDoc(text, encoding="utf-8")
    detector = ConsecutiveDetector()
    errs = detector.detect(doc)
    assert len(errs) == 0
    results.append(("empty text", "ok", "no errors"))
except Exception as e:
    errors.append(("empty text", str(e)))

# Test 10: 无符号文本
try:
    text = "这是一段普通的叙述文字，没有任何对话符号。"
    doc = TextDoc(text, encoding="utf-8")
    detector = ConsecutiveDetector()
    errs = detector.detect(doc)
    assert len(errs) == 0
    results.append(("no brackets", "ok", "no errors"))
except Exception as e:
    errors.append(("no brackets", str(e)))

# Test 11: 单独的「（没有」）
try:
    text = "「只有开头没有结尾"
    doc = TextDoc(text, encoding="utf-8")
    detector = ConsecutiveDetector()
    errs = detector.detect(doc)
    # 只有一个「，不会构成连续符号错误
    assert len(errs) == 0
    results.append(("unpaired only (no consecutive)", "ok", "no consecutive errors"))
except Exception as e:
    errors.append(("unpaired only (no consecutive)", str(e)))

# Test 12: 真实小说片段测试
try:
    from src.io.loader import TextLoader
    loader = TextLoader()
    doc = loader.load("data/ori_story/第1卷.txt")

    detector = ConsecutiveDetector()
    errs = detector.detect(doc)

    # 应该能检测到一些错误（如果存在的话）
    # 至少运行没有异常
    results.append(("real novel scan", "ok",
                    f"第1卷.txt: {len(errs)} consecutive errors found"))
except Exception as e:
    errors.append(("real novel scan", str(e)))

# Test 13: 验证 ErrorRecord 字段完整
try:
    text = "「你好」他说道。」我很好」"
    doc = TextDoc(text, encoding="utf-8")
    detector = ConsecutiveDetector()
    errs = detector.detect(doc)

    assert len(errs) >= 1
    e = errs[0]
    assert e.error_id.startswith("e-")
    assert e.error_type == "consecutive"
    assert e.line_number >= 1
    assert e.offset >= 0
    assert len(e.context_before) > 0
    assert len(e.context_after) > 0
    assert len(e.original_text) > 0
    assert e.status == "pending"

    results.append(("ErrorRecord completeness", "ok",
                    f"all fields populated for error at L{e.line_number}"))
except Exception as e:
    errors.append(("ErrorRecord completeness", str(e)))

# Print report
print("=" * 55)
print("  Stage 6 Verification Report — ConsecutiveDetector")
print("=" * 55)
for name, status, detail in results:
    print(f"  [OK] {name}: {detail}")
for name, detail in errors:
    print(f"  [FAIL] {name}: {detail}")
print("=" * 55)
print(f"  {len(results)} passed, {len(errors)} failed")
print("=" * 55)
