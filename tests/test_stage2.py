"""Stage 2 验证脚本：TextLoader + TextDoc"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

results = []
errors = []

# Test 1: 导入
try:
    from src.core.text import TextDoc
    from src.io.loader import TextLoader, load_text, LoaderError
    results.append(("imports", "ok", "TextDoc, TextLoader, load_text, LoaderError"))
except Exception as e:
    errors.append(("imports", str(e)))

# Test 2: TextDoc 基础功能
try:
    doc = TextDoc("Hello\nWorld\nThird Line", encoding="utf-8", path="test.txt")
    assert doc.text == "Hello\nWorld\nThird Line"
    assert doc.line_count() == 3
    assert doc.encoding == "utf-8"
    assert doc.path == "test.txt"
    lines = doc.lines()
    assert len(lines) == 3
    assert lines[0] == "Hello"
    assert lines[1] == "World"
    assert lines[2] == "Third Line"
    # 1-based 行号访问
    assert doc[1] == "Hello"
    assert doc[2] == "World"
    assert doc[3] == "Third Line"
    # 越界检查
    try:
        doc[0]
        errors.append(("TextDoc", "line 0 should raise IndexError"))
    except IndexError:
        pass
    try:
        doc[4]
        errors.append(("TextDoc", "line 4 should raise IndexError"))
    except IndexError:
        pass
    results.append(("TextDoc basic", "ok", "all assertions passed"))
except Exception as e:
    errors.append(("TextDoc basic", str(e)))

# Test 3: TextDoc 行范围与上下文
try:
    doc = TextDoc("Line1\nLine2\nLine3\nLine4\nLine5\nLine6")
    r = doc.line_range(2, 4)
    assert "Line2" in r and "Line3" in r and "Line4" in r
    ctx = doc.get_line_with_context(3, context=1)
    assert "Line2" in ctx and "Line3" in ctx and "Line4" in ctx
    assert ">>>" in ctx  # 当前行标记
    # offset 转换
    assert doc.offset_to_line(0) == 1   # "Line1" 的开头
    assert doc.line_to_offset(2) == 6   # "Line2" 的开头
    results.append(("TextDoc context", "ok", "line_range/context/offset all passed"))
except Exception as e:
    errors.append(("TextDoc context", str(e)))

# Test 4: 加载真实文件 — 第1卷.txt（已知为 UTF-16）
loader = TextLoader()
try:
    doc = loader.load("data/ori_story/第1卷.txt")
    assert doc.line_count() > 0, "should have lines"
    assert doc.encoding in ("utf-16-le", "utf-16-be", "utf-8"), f"unexpected encoding: {doc.encoding}"
    results.append(("load 第1卷.txt", "ok", f"{doc.line_count()} lines, encoding={doc.encoding}"))
except Exception as e:
    errors.append(("load 第1卷.txt", str(e)))

# Test 5: 加载第3卷.txt（已知可能使用不同编码）
try:
    doc = loader.load("data/ori_story/第3卷.txt")
    assert doc.line_count() > 0
    results.append(("load 第3卷.txt", "ok", f"{doc.line_count()} lines, encoding={doc.encoding}"))
except Exception as e:
    errors.append(("load 第3卷.txt", str(e)))

# Test 6: 加载第10卷.txt（最后一卷）
try:
    doc = loader.load("data/ori_story/第10卷.txt")
    assert doc.line_count() > 0
    results.append(("load 第10卷.txt", "ok", f"{doc.line_count()} lines, encoding={doc.encoding}"))
except Exception as e:
    errors.append(("load 第10卷.txt", str(e)))

# Test 7: 按行号访问真实文件内容
try:
    doc = loader.load("data/ori_story/第1卷.txt")
    first_line = doc[1]
    assert len(first_line) > 0
    results.append(("line access 第1卷.txt", "ok", f"line 1: {first_line[:60]}..."))
except Exception as e:
    errors.append(("line access 第1卷.txt", str(e)))

# Test 8: 便利函数 load_text
try:
    from src.io.loader import load_text
    doc = load_text("data/ori_story/第1卷.txt")
    assert doc.line_count() > 0
    results.append(("load_text convenience", "ok", f"{doc.line_count()} lines"))
except Exception as e:
    errors.append(("load_text convenience", str(e)))

# Test 9: 文件不存在
try:
    doc = loader.load("data/not_exists.txt")
    errors.append(("file not found", "should raise LoaderError"))
except LoaderError:
    results.append(("file not found", "ok", "LoaderError raised as expected"))
except Exception as e:
    errors.append(("file not found", f"unexpected error: {e}"))

# Test 10: 空文本
try:
    doc = TextDoc("", encoding="utf-8")
    assert doc.line_count() == 0
    assert doc.lines() == []
    results.append(("empty TextDoc", "ok", "0 lines"))
except Exception as e:
    errors.append(("empty TextDoc", str(e)))

# Print report
print("=" * 55)
print("  Stage 2 Verification Report — TextLoader & TextDoc")
print("=" * 55)
for name, status, detail in results:
    print(f"  [OK] {name}: {detail}")
for name, detail in errors:
    print(f"  [FAIL] {name}: {detail}")
print("=" * 55)
print(f"  {len(results)} passed, {len(errors)} failed")
print("=" * 55)

# Show a sample of real loaded data
print()
print("  --- Sample: 第1卷.txt first 3 lines ---")
doc = loader.load("data/ori_story/第1卷.txt")
for i in range(1, min(4, doc.line_count() + 1)):
    print(f"  L{i}: {doc[i][:80]}")
