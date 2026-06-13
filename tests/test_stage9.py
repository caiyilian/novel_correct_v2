"""Stage 9 验证脚本：LongDialogueDetector 超长对话检测器"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

results = []
errors = []

from src.core.text import TextDoc
from src.detector.long_dialogue import LongDialogueDetector

# Test 1: 导入
try:
    from src.detector.long_dialogue import LongDialogueDetector
    results.append(("imports", "ok", "LongDialogueDetector importable"))
except Exception as e:
    errors.append(("imports", str(e)))

# Test 2: 短对话 — 无错误
try:
    text = "「你好」他说道。「我很好」"
    doc = TextDoc(text)
    detector = LongDialogueDetector(max_length=80)
    errs = detector.detect(doc)
    assert len(errs) == 0, f"expected 0, got {len(errs)}"
    results.append(("short dialogues", "ok", "no false positives"))
except Exception as e:
    errors.append(("short dialogues", str(e)))

# Test 3: 超长对话 — 检测到
try:
    # 构造一个超长对话（超过 80 字符）
    long_text = "「" + "你好。" * 30 + "」"
    text = long_text + "「短对话」"
    doc = TextDoc(text)
    detector = LongDialogueDetector(max_length=80)
    errs = detector.detect(doc)
    assert len(errs) >= 1, f"expected >=1, got {len(errs)}"
    e = errs[0]
    assert e.error_type == "long_dialogue"
    results.append(("long dialogue detected", "ok",
                    f"length={len(long_text)-2} chars, L{e.line_number}"))
except Exception as e:
    errors.append(("long dialogue detected", str(e)))

# Test 4: 自定义阈值
try:
    text = "「你好吗？」「我很好，谢谢。」「再见。」"
    doc = TextDoc(text)
    # 设置很小的阈值，所有对话都会触发
    detector = LongDialogueDetector(max_length=5, top_k=10)
    errs = detector.detect(doc)
    assert len(errs) >= 1, f"expected >=1, got {len(errs)}"
    results.append(("custom max_length", "ok",
                    f"max_length=5, detected {len(errs)} long dialogues"))
except Exception as e:
    errors.append(("custom max_length", str(e)))

# Test 5: Top K 限制
try:
    text = ""
    for i in range(10):
        text += "「" + "A" * 100 + "」\n"
    doc = TextDoc(text)
    # top_k=3，只返回最长的 3 个
    detector = LongDialogueDetector(max_length=50, top_k=3)
    errs = detector.detect(doc)
    assert len(errs) == 3, f"expected 3, got {len(errs)}"
    results.append(("top_k limit", "ok", "only 3 returned as configured"))
except Exception as e:
    errors.append(("top_k limit", str(e)))

# Test 6: 空文本
try:
    text = ""
    doc = TextDoc(text)
    detector = LongDialogueDetector()
    errs = detector.detect(doc)
    assert len(errs) == 0
    results.append(("empty text", "ok", "no errors"))
except Exception as e:
    errors.append(("empty text", str(e)))

# Test 7: 无符号文本
try:
    text = "这是一段普通的叙述文字，没有任何对话符号。"
    doc = TextDoc(text)
    detector = LongDialogueDetector()
    errs = detector.detect(doc)
    assert len(errs) == 0
    results.append(("no brackets", "ok", "no errors"))
except Exception as e:
    errors.append(("no brackets", str(e)))

# Test 8: 混合短长对话
try:
    text = (
        "「短对话」\n"
        "「这是一段比较长的对话，但还没有达到超长阈值」\n"
        "「" + "很长" * 50 + "」\n"  # 100 字，肯定超长
        "「正常对话」"
    )
    doc = TextDoc(text)
    detector = LongDialogueDetector(max_length=80, top_k=5)
    errs = detector.detect(doc)
    # 应该只检测到那个 100 字的超长对话
    assert len(errs) >= 1, f"expected >=1, got {len(errs)}"
    results.append(("mixed dialogue lengths", "ok",
                    f"detected {len(errs)} long dialogues"))
except Exception as e:
    errors.append(("mixed dialogue lengths", str(e)))

# Test 9: 正好等于阈值的对话 — 不应检测
try:
    text = "「" + "A" * 80 + "」"  # 正好 80 字符
    doc = TextDoc(text)
    detector = LongDialogueDetector(max_length=80)
    errs = detector.detect(doc)
    # max_length 是严格大于才检测，所以 80 不算超长
    assert len(errs) == 0, f"expected 0, got {len(errs)}"
    results.append(("exactly at threshold", "ok", "80 chars not detected (must exceed)"))
except Exception as e:
    errors.append(("exactly at threshold", str(e)))

# Test 10: 真实小说扫描
try:
    from src.io.loader import TextLoader
    loader = TextLoader()
    doc = loader.load("data/ori_story/第1卷.txt")
    detector = LongDialogueDetector(max_length=80, top_k=20)
    errs = detector.detect(doc)
    results.append(("real novel scan 第1卷", "ok",
                    f"found {len(errs)} long dialogues (top 20)"))
except Exception as e:
    errors.append(("real novel scan 第1卷", str(e)))

# Test 11: 第3卷扫描（全卷弯引号，不会有「」匹配）
try:
    doc = loader.load("data/ori_story/第3卷.txt")
    detector = LongDialogueDetector(max_length=80, top_k=20)
    errs = detector.detect(doc)
    # 第3卷没有「」，所以应该 0 结果
    assert len(errs) == 0, f"expected 0, got {len(errs)}"
    results.append(("real novel scan 第3卷", "ok",
                    "0 long dialogues (no 「」 in this volume)"))
except Exception as e:
    errors.append(("real novel scan 第3卷", str(e)))

# Test 12: ErrorRecord 字段完整性
try:
    text = "「" + "很长" * 50 + "」"
    doc = TextDoc(text)
    detector = LongDialogueDetector(max_length=80, top_k=5)
    errs = detector.detect(doc)
    assert len(errs) >= 1
    e = errs[0]
    assert e.error_id.startswith("e-")
    assert e.error_type == "long_dialogue"
    assert e.line_number >= 1
    assert e.offset >= 0
    assert e.status == "pending"
    results.append(("ErrorRecord completeness", "ok", "all fields populated"))
except Exception as e:
    errors.append(("ErrorRecord completeness", str(e)))

# Print report
print("=" * 55)
print("  Stage 9 Verification Report — LongDialogueDetector")
print("=" * 55)
for name, status, detail in results:
    print(f"  [OK] {name}: {detail}")
for name, detail in errors:
    print(f"  [FAIL] {name}: {detail}")
print("=" * 55)
print(f"  {len(results)} passed, {len(errors)} failed")
print("=" * 55)
