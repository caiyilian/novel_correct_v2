"""Stage 13 验证脚本：System Prompt 精细化"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.core.error_record import ErrorRecord
from src.agent.prompts import (
    build_system_prompt, build_user_prompt,
    BASE_SYSTEM_PROMPT,
    CONSECUTIVE_PROMPT, WRONG_SYMBOL_PROMPT, UNPAIRED_PROMPT,
    LONG_DIALOGUE_PROMPT, MISSING_BRACKET_PROMPT,
)

results = []
errors = []

# Test 1: 导入
try:
    from src.agent.prompts import build_system_prompt, build_user_prompt
    results.append(("imports", "ok", "all prompt functions importable"))
except Exception as e:
    errors.append(("imports", str(e)))

# Test 2: 每种错误类型都有专用 prompt
try:
    for etype in ("consecutive", "unpaired", "wrong_symbol", "long_dialogue", "missing_bracket"):
        prompt = build_system_prompt(etype)
        assert len(prompt) > len(BASE_SYSTEM_PROMPT), \
            f"{etype}: prompt too short ({len(prompt)} <= {len(BASE_SYSTEM_PROMPT)})"
        assert "「" in prompt, f"{etype}: missing bracket char in prompt"
    results.append(("type-specific prompts", "ok",
                    "all 5 error types have dedicated prompts"))
except Exception as e:
    errors.append(("type-specific prompts", str(e)))

# Test 3: 未知错误类型使用基础 prompt
try:
    prompt = build_system_prompt("unknown_type")
    assert prompt == BASE_SYSTEM_PROMPT
    results.append(("unknown type fallback", "ok", "uses base prompt"))
except Exception as e:
    errors.append(("unknown type fallback", str(e)))

# Test 4: build_user_prompt 包含错误信息
try:
    err = ErrorRecord(
        error_id="e-0042",
        error_type="consecutive",
        line_number=7,
        offset=100,
        original_text="」错误示例」",
        context_before="前面内容",
        context_after="后面内容",
    )
    prompt = build_user_prompt(err)
    assert "e-0042" in prompt
    assert "consecutive" in prompt or "连续" in prompt
    assert "第7行" in prompt
    assert "offset 100" in prompt
    assert "」错误示例」" in prompt
    results.append(("build_user_prompt", "ok", "contains error id, type, location, text"))
except Exception as e:
    errors.append(("build_user_prompt", str(e)))

# Test 5: 每种 prompt 都包含专用的判断规则
try:
    assert "正确的交替模式" in CONSECUTIVE_PROMPT
    assert "替换为「」" in WRONG_SYMBOL_PROMPT
    assert "不成对" in UNPAIRED_PROMPT or "多余的」" in UNPAIRED_PROMPT
    assert "旁白" in LONG_DIALOGUE_PROMPT
    assert "特征词" in MISSING_BRACKET_PROMPT
    results.append(("prompt content check", "ok", "all prompts contain type-specific rules"))
except Exception as e:
    errors.append(("prompt content check", str(e)))

# Test 6: 每种 prompt 都有实际校正示例
try:
    assert "输入:" in CONSECUTIVE_PROMPT
    assert "修正:" in CONSECUTIVE_PROMPT
    assert "特征是" in WRONG_SYMBOL_PROMPT or "判断依据" in WRONG_SYMBOL_PROMPT
    assert "示例" in LONG_DIALOGUE_PROMPT
    results.append(("prompt examples", "ok", "prompts contain examples"))
except Exception as e:
    errors.append(("prompt examples", str(e)))

# Test 7: prompt 长度合理
try:
    for name, prompt in [
        ("consecutive", CONSECUTIVE_PROMPT),
        ("wrong_symbol", WRONG_SYMBOL_PROMPT),
        ("unpaired", UNPAIRED_PROMPT),
        ("long_dialogue", LONG_DIALOGUE_PROMPT),
        ("missing_bracket", MISSING_BRACKET_PROMPT),
    ]:
        length = len(prompt)
        assert 200 <= length <= 2000, f"{name}: {length} chars (expected 200-2000)"
    results.append(("prompt length", "ok", "all prompts between 200-2000 chars"))
except Exception as e:
    errors.append(("prompt length", str(e)))

# Test 8: base prompt 内容完整
try:
    assert "核心规则" in BASE_SYSTEM_PROMPT
    assert "职责范围" in BASE_SYSTEM_PROMPT
    assert "工作流程" in BASE_SYSTEM_PROMPT
    assert "注意事项" in BASE_SYSTEM_PROMPT
    assert "get_next_error" in BASE_SYSTEM_PROMPT
    assert "apply_fix" in BASE_SYSTEM_PROMPT
    assert "skip_error" in BASE_SYSTEM_PROMPT
    assert "revert_fix" in BASE_SYSTEM_PROMPT
    results.append(("base prompt", "ok", "contains rules, scope, workflow, notes"))
except Exception as e:
    errors.append(("base prompt", str(e)))

# Test 9: build_system_prompt 返回长度合理（base + 专用）
try:
    for etype in ("consecutive", "unpaired", "wrong_symbol", "long_dialogue", "missing_bracket"):
        full = build_system_prompt(etype)
        base_len = len(BASE_SYSTEM_PROMPT)
        total_len = len(full)
        # 应该比 base 长（因为加了专用），但不应超过 base 的 2 倍
        assert total_len > base_len, f"{etype}: total <= base"
        assert total_len < base_len * 2, f"{etype}: total ({total_len}) > 2x base ({base_len*2})"
    results.append(("prompt total length", "ok", "base + dedicated within 2x base"))
except Exception as e:
    errors.append(("prompt total length", str(e)))

# Test 10: User prompt 为空字段处理
try:
    err = ErrorRecord(
        error_id="e-0100",
        error_type="wrong_symbol",
        line_number=1,
        offset=0,
        original_text="[test]",
    )
    prompt = build_user_prompt(err)
    assert "e-0100" in prompt
    assert "[test]" in prompt
    results.append(("minimal error record", "ok", "handles empty context fields"))
except Exception as e:
    errors.append(("minimal error record", str(e)))

# Print report
print("=" * 55)
print("  Stage 13 Verification Report — System Prompt 精细化")
print("=" * 55)
for name, status, detail in results:
    print(f"  [OK] {name}: {detail}")
for name, detail in errors:
    print(f"  [FAIL] {name}: {detail}")
print("=" * 55)
print(f"  {len(results)} passed, {len(errors)} failed")
print("=" * 55)

# Print prompt length statistics
print()
print("  Prompt size statistics:")
print(f"    Base:          {len(BASE_SYSTEM_PROMPT):5d} chars")
print(f"    Consecutive:   {len(CONSECUTIVE_PROMPT):5d} chars")
print(f"    WrongSymbol:   {len(WRONG_SYMBOL_PROMPT):5d} chars")
print(f"    Unpaired:      {len(UNPAIRED_PROMPT):5d} chars")
print(f"    LongDialogue:  {len(LONG_DIALOGUE_PROMPT):5d} chars")
print(f"    MissingBracket:{len(MISSING_BRACKET_PROMPT):5d} chars")
