"""Stage 8 验证脚本：UnpairedDetector & MissingBracketDetector"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

results = []
errors = []

from src.core.text import TextDoc
from src.detector.unpaired import UnpairedDetector
from src.detector.missing_bracket import MissingBracketDetector

# ── UnpairedDetector 测试 ─────────────────────────────

# Test 1: 导入
try:
    from src.detector.unpaired import UnpairedDetector
    from src.detector.missing_bracket import MissingBracketDetector
    results.append(("imports", "ok", "both detectors importable"))
except Exception as e:
    errors.append(("imports", str(e)))

# Test 2: 「数量相等 — 无错误
try:
    text = "「你好」他说道。「我很好」谢谢。「再见」"
    doc = TextDoc(text)
    detector = UnpairedDetector()
    errs = detector.detect(doc)
    assert len(errs) == 0, f"expected 0, got {len(errs)}"
    results.append(("Unpaired: balanced", "ok", "no false positives"))
except Exception as e:
    errors.append(("Unpaired: balanced", str(e)))

# Test 3: 缺失一个」— 检测到多余「
try:
    text = "「你好。我很好"
    doc = TextDoc(text)
    detector = UnpairedDetector()
    errs = detector.detect(doc)
    assert len(errs) == 1, f"expected 1, got {len(errs)}"
    e = errs[0]
    assert e.error_type == "unpaired"
    assert text[e.offset] == "「"
    results.append(("Unpaired: missing 」", "ok", f"detected 1 unpaired 「 at offset {e.offset}"))
except Exception as e:
    errors.append(("Unpaired: missing 」", str(e)))

# Test 4: 多余一个」— 检测到多余」
try:
    text = "你好。我很好」"
    doc = TextDoc(text)
    detector = UnpairedDetector()
    errs = detector.detect(doc)
    assert len(errs) == 1, f"expected 1, got {len(errs)}"
    e = errs[0]
    assert text[e.offset] == "」"
    results.append(("Unpaired: extra 」", "ok", f"detected 1 extra 」 at offset {e.offset}"))
except Exception as e:
    errors.append(("Unpaired: extra 」", str(e)))

# Test 5: 多个不成对
try:
    text = "「你好「我很好」"
    doc = TextDoc(text)
    detector = UnpairedDetector()
    errs = detector.detect(doc)
    # 有两个「和一个」，所以一个未匹配的「
    assert len(errs) == 1, f"expected 1, got {len(errs)}"
    results.append(("Unpaired: multiple unpaired", "ok",
                    f"detected {len(errs)} unpaired in '「你好「我很好」'"))
except Exception as e:
    errors.append(("Unpaired: multiple unpaired", str(e)))

# Test 6: 空文本
try:
    text = ""
    doc = TextDoc(text)
    detector = UnpairedDetector()
    errs = detector.detect(doc)
    assert len(errs) == 0
    results.append(("Unpaired: empty", "ok", "no errors"))
except Exception as e:
    errors.append(("Unpaired: empty", str(e)))

# Test 7: 无符号文本
try:
    text = "这是一段普通的叙述文字。"
    doc = TextDoc(text)
    detector = UnpairedDetector()
    errs = detector.detect(doc)
    assert len(errs) == 0
    results.append(("Unpaired: no brackets", "ok", "no errors"))
except Exception as e:
    errors.append(("Unpaired: no brackets", str(e)))

# Test 8: 复杂匹配
try:
    text = "「第一段」叙述。「第二段」再叙述。「第三段"
    doc = TextDoc(text)
    detector = UnpairedDetector()
    errs = detector.detect(doc)
    # 3 个「和 2 个」，所以 1 个未匹配的「
    assert len(errs) == 1, f"expected 1, got {len(errs)}"
    results.append(("Unpaired: complex match", "ok",
                    f"detected {len(errs)} unpaired in complex text"))
except Exception as e:
    errors.append(("Unpaired: complex match", str(e)))

# Test 9: 真实小说扫描
try:
    from src.io.loader import TextLoader
    loader = TextLoader()
    doc = loader.load("data/ori_story/第1卷.txt")
    detector = UnpairedDetector()
    errs = detector.detect(doc)
    results.append(("Unpaired: real novel 第1卷", "ok",
                    f"found {len(errs)} unpaired errors"))
except Exception as e:
    errors.append(("Unpaired: real novel 第1卷", str(e)))

# ── MissingBracketDetector 测试 ───────────────────────

# Test 10: 普通对话行（"说道："后无符号）
try:
    # 特征：某人说道：内容（至少 8 字符触发检测）
    text = "他说道：你好吗？\n「我很好」"
    doc = TextDoc(text)
    detector = MissingBracketDetector()
    errs = detector.detect(doc)
    assert len(errs) >= 1, f"expected >=1, got {len(errs)}"
    e = errs[0]
    assert e.error_type == "missing_bracket"
    results.append(("Missing: 说道： no bracket", "ok",
                    f"detected 1 missing bracket at L{e.line_number}: {e.original_text[:40]}"))
except Exception as e:
    errors.append(("Missing: 说道： no bracket", str(e)))

# Test 11: 已用「」包裹的对话 — 不应检测
try:
    text = "他说道：「你好吗」\n她答道：「我很好」"
    doc = TextDoc(text)
    detector = MissingBracketDetector()
    errs = detector.detect(doc)
    assert len(errs) == 0, f"expected 0, got {len(errs)}"
    results.append(("Missing: already bracketed", "ok", "no false positives"))
except Exception as e:
    errors.append(("Missing: already bracketed", str(e)))

# Test 12: 无特征词 — 不应检测
try:
    text = "今天天气真不错。去散步吧。"
    doc = TextDoc(text)
    detector = MissingBracketDetector()
    errs = detector.detect(doc)
    assert len(errs) == 0
    results.append(("Missing: no keywords", "ok", "no false positives"))
except Exception as e:
    errors.append(("Missing: no keywords", str(e)))

# Test 13: 多种特征词
try:
    text = "他问道：你叫什么名字？\n她回答说：我叫小明。\n他笑道：原来如此。"
    doc = TextDoc(text)
    detector = MissingBracketDetector()
    errs = detector.detect(doc)
    assert len(errs) == 3, f"expected 3, got {len(errs)}"
    results.append(("Missing: multiple keywords", "ok",
                    f"detected {len(errs)} lines with dialogue keywords"))
except Exception as e:
    errors.append(("Missing: multiple keywords", str(e)))

# Test 14: 真实小说扫描
try:
    doc = loader.load("data/ori_story/第1卷.txt")
    detector = MissingBracketDetector()
    errs = detector.detect(doc)
    results.append(("Missing: real novel 第1卷", "ok",
                    f"found {len(errs)} missing bracket candidates"))
except Exception as e:
    errors.append(("Missing: real novel 第1卷", str(e)))

# Test 15: ErrorRecord 字段完整性
try:
    text = "他说道：你好吗？今天天气真不错。"
    doc = TextDoc(text)
    detector = MissingBracketDetector()
    errs = detector.detect(doc)
    assert len(errs) >= 1
    e = errs[0]
    assert e.error_id.startswith("e-")
    assert e.error_type == "missing_bracket"
    assert e.line_number >= 1
    assert e.offset >= 0
    assert len(e.context_before) > 0 or len(e.context_after) > 0
    assert e.status == "pending"
    results.append(("ErrorRecord completeness", "ok", "all fields populated"))
except Exception as e:
    errors.append(("ErrorRecord completeness", str(e)))

# Print report
print("=" * 55)
print("  Stage 8 Verification Report — Unpaired & MissingBracket")
print("=" * 55)
for name, status, detail in results:
    if name in ("imports", "ErrorRecord completeness"):
        print(f"  [OK] {name}: {detail}")
    elif name.startswith("Unpaired"):
        print(f"  [OK] {name}: {detail}")
    elif name.startswith("Missing"):
        print(f"  [OK] {name}: {detail}")
for name, detail in errors:
    print(f"  [FAIL] {name}: {detail}")
print("=" * 55)
print(f"  {len(results)} passed, {len(errors)} failed")
print("=" * 55)
