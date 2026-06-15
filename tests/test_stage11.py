"""Stage 11 验证脚本：CorrectionToolset LLM 工具集"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

results = []
errors = []

from src.core.text import TextDoc
from src.core.error_queue import ErrorQueue
from src.core.error_record import ErrorRecord
from src.agent.tools import CorrectionToolset, SearchMatch

# Test 1: 导入
try:
    from src.agent.tools import CorrectionToolset, SearchMatch
    results.append(("imports", "ok", "CorrectionToolset, SearchMatch importable"))
except Exception as e:
    errors.append(("imports", str(e)))

# 准备测试数据
text = TextDoc(
    "第一行：开头叙述\n"
    "第二行：他说道：「你好吗？」\n"
    "第三行：[错误方括号内容]\n"
    "第四行：正常叙述\n"
    "这是第五行：另一段叙述\n"           # 隔开间距
    "第六行：长对话开始" + "很长" * 30 + "长对话结束」\n"
    "第七行：结束"
)
queue = ErrorQueue()
queue.add(ErrorRecord(               # offset ~28
    error_type="wrong_symbol", line_number=3, offset=28,
    context_before="第二行：他说道：「你好吗？」\n",
    context_after="\n第四行：正常叙述",
    original_text="[错误方括号内容]",
))
queue.add(ErrorRecord(               # offset ~123 (>> 50 from 28)
    error_type="long_dialogue", line_number=6, offset=123,
    original_text="「长对话开始" + "很长" * 5,
    context_before="第四行：正常叙述\n",
    context_after="\n第七行：结束",
))

tools = CorrectionToolset(text, queue)

# Test 2: ToolSpec 定义
try:
    specs = CorrectionToolset.tool_specs()
    names = [s.name for s in specs]
    assert len(specs) == 6, f"expected 6 LLM tools, got {len(specs)}"
    assert "read_lines" in names
    assert "read_offset" in names
    assert "search_text" in names
    assert "apply_fix" in names
    assert "skip_error" in names
    assert "revert_fix" in names
    assert "get_next_error" not in names  # 当前错误已由 user prompt 传入
    assert "get_progress" not in names  # LLM 不需要查看全局进度
    results.append(("ToolSpec definitions", "ok",
                    f"6 LLM tools defined: {', '.join(names)}"))
except Exception as e:
    errors.append(("ToolSpec definitions", str(e)))

# Test 3: ToolSpec 可序列化为 OpenAI 格式
try:
    specs = CorrectionToolset.tool_specs()
    for spec in specs:
        otool = spec.to_openai_tool()
        assert otool["type"] == "function"
        assert otool["function"]["name"] == spec.name
        assert len(otool["function"]["description"]) > 0
        assert "properties" in otool["function"]["parameters"]
    results.append(("ToolSpec OpenAI format", "ok", "all 6 LLM tools serializable"))
except Exception as e:
    errors.append(("ToolSpec OpenAI format", str(e)))

# Test 4: read_lines
try:
    result = tools.read_lines(2, 4)
    assert "第二行" in result
    assert "第三行" in result
    assert "第四行" in result
    assert "第一行" not in result
    results.append(("read_lines", "ok", "L2-L4 returned correctly"))
except Exception as e:
    errors.append(("read_lines", str(e)))

# Test 5: read_offset
try:
    result = tools.read_offset(31, context=50)
    assert "第三行" in result or "[错误" in result or "offset 31" in result
    results.append(("read_offset", "ok", "context around offset 31"))
except Exception as e:
    errors.append(("read_offset", str(e)))

# Test 6: search_text
try:
    result = tools.search_text("他说道", limit=5)
    assert result["total_matches"] >= 1
    assert len(result["matches"]) >= 1
    assert result["matches"][0]["line_number"] == 2
    results.append(("search_text", "ok",
                    f"found {result['total_matches']} matches"))
except Exception as e:
    errors.append(("search_text", str(e)))

# Test 7: get_next_error
try:
    result = tools.get_next_error()
    assert result["status"] == "pending"
    assert result["error_type"] == "wrong_symbol"
    assert result["error_id"].startswith("e-")
    results.append(("get_next_error", "ok",
                    f"next: {result['error_id']} ({result['error_type']})"))
except Exception as e:
    errors.append(("get_next_error", str(e)))

# Test 8: get_progress
try:
    result = tools.get_progress()
    assert result["total"] == 2
    assert result["pending"] == 2
    assert result["remaining"] == 2
    results.append(("get_progress", "ok",
                    f"total={result['total']}, pending={result['pending']}"))
except Exception as e:
    errors.append(("get_progress", str(e)))

# Test 9: apply_fix
try:
    err = queue.all()[0]
    result = tools.apply_fix(
        error_id=err.error_id,
        start_offset=err.offset,
        end_offset=err.offset + len(err.original_text),
        replacement="「错误方括号内容」"
    )
    assert result["status"] == "ok"
    assert result["action"] == "fix_applied"
    results.append(("apply_fix", "ok",
                    f"replaced '{result['original']}' -> '{result['replacement']}'"))
except Exception as e:
    errors.append(("apply_fix", str(e)))

# Test 10: skip_error
try:
    err = queue.all()[1]  # 第二个错误
    result = tools.skip_error(
        error_id=err.error_id,
        reason="This is actually a long monologue, not missing brackets"
    )
    assert result["status"] == "ok"
    assert result["action"] == "skipped"
    # 验证状态已更新
    assert queue.get(err.error_id).status == "skipped"
    results.append(("skip_error", "ok",
                    f"skipped {err.error_id}: {result['reason'][:40]}"))
except Exception as e:
    errors.append(("skip_error", str(e)))

# Test 11: get_progress 更新
try:
    result = tools.get_progress()
    assert result["total"] == 2
    assert result["skipped"] == 1  # skip_error 更新了状态
    # apply_fix 只设置了 fix_applied 字段，未改 status
    # 所以 pending 应该是 1
    assert result["pending"] == 1
    results.append(("progress after fixes", "ok",
                    f"total={result['total']}, skipped={result['skipped']}, pending={result['pending']}"))
except Exception as e:
    errors.append(("progress after fixes", str(e)))

# Test 12: revert_fix
try:
    err = queue.all()[0]
    result = tools.revert_fix(error_id=err.error_id)
    assert result["status"] == "ok"
    assert result["action"] == "reverted"
    # 验证错误状态已恢复
    assert queue.get(err.error_id).status == "pending"
    assert queue.get(err.error_id).fix_applied == ""
    results.append(("revert_fix", "ok",
                    f"reverted fix for {err.error_id}"))
except Exception as e:
    errors.append(("revert_fix", str(e)))

# Test 13: execute 分发（模拟 LLM 调用）
try:
    result = tools.execute("read_lines", {"start": 1, "end": 1})
    assert "第一行" in result
    result2 = tools.execute("get_progress", {})
    assert result2["total"] == 2
    result3 = tools.execute("nonexistent_tool", {})
    assert result3["status"] == "error"
    results.append(("execute dispatch", "ok", "tool routing works"))
except Exception as e:
    errors.append(("execute dispatch", str(e)))

# Test 14: 越界行号处理
try:
    result = tools.read_lines(999, 1000)
    # Python 切片不会对越界索引报错，会返回空
    assert result == "" or "Error" in result
    results.append(("read_lines bounds", "ok", "out-of-range handled gracefully"))
except Exception as e:
    errors.append(("read_lines bounds", str(e)))

# Test 15: 未知 error_id
try:
    result = tools.skip_error(error_id="e-9999", reason="test")
    assert result["status"] == "error"
    results.append(("unknown error_id", "ok", "graceful error handling"))
except Exception as e:
    errors.append(("unknown error_id", str(e)))

# Test 16: apply_fix 拒绝修改正文内容
try:
    err = queue.all()[0]
    result = tools.apply_fix(error_id=err.error_id, start_offset=err.offset,
                             end_offset=err.offset + len(err.original_text),
                             replacement="「正文被改掉」")
    assert result["status"] == "error"
    assert "only change dialogue wrapper symbols" in result["message"]
    results.append(("apply_fix content guard", "ok", "non-symbol content cannot change"))
except Exception as e:
    errors.append(("apply_fix content guard", str(e)))

# Test 17: current_text 属性
try:
    # apply a fix and check current_text
    err = queue.all()[0]
    tools.apply_fix(error_id=err.error_id, start_offset=err.offset,
                    end_offset=err.offset + len(err.original_text),
                    replacement="「错误方括号内容」")
    current = tools.current_text
    assert "「错误方括号内容」" in current
    assert "[错误方括号内容]" not in current
    results.append(("current_text", "ok", "in-memory text updated after fix"))
except Exception as e:
    errors.append(("current_text", str(e)))

# Print report
print("=" * 55)
print("  Stage 11 Verification Report — CorrectionToolset")
print("=" * 55)
for name, status, detail in results:
    print(f"  [OK] {name}: {detail}")
for name, detail in errors:
    print(f"  [FAIL] {name}: {detail}")
print("=" * 55)
print(f"  {len(results)} passed, {len(errors)} failed")
print("=" * 55)
