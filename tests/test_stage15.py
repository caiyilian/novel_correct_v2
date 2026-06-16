"""Stage 15 验证脚本：候选修复 + LLM 只做判断"""
import json
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.agent.candidates import CandidateGenerator
from src.agent.decision import CandidateDecisionAgent
from src.core.error_queue import ErrorQueue
from src.core.error_record import ErrorRecord
from src.core.progress import ProgressTracker
from src.core.text import TextDoc
from src.model.client import ChatResult, ToolCall
from src.verifier.agent import CorrectionVerifier


results = []
errors = []


class MockDecisionClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.call_count = 0
        self.prompts = []
        self.tool_names_per_call = []

    def chat(self, messages, tools=None, temperature=None, max_tokens=None):
        self.call_count += 1
        self.prompts.append(messages[-1].content)
        self.tool_names_per_call.append([tool.name for tool in (tools or [])])
        content = self.responses.pop(0) if self.responses else self._apply_first()
        if isinstance(content, ChatResult):
            return content
        return ChatResult(content=content, raw={})

    @staticmethod
    def _apply_first():
        return json.dumps(
            {"decision": "apply", "choice_id": "c1", "reason": "候选合理"},
            ensure_ascii=False,
        )


def make_tracker(queue, name="candidate.txt"):
    tmpdir = tempfile.mkdtemp()
    tracker = ProgressTracker(name, checkpoint_dir=tmpdir)
    tracker.init_checkpoint(queue)
    return tracker, tmpdir


# Test 1: wrong_symbol 候选保留正文，只替换包裹符号
try:
    text = TextDoc("[你好]结束")
    error = ErrorRecord(
        error_id="e-wrong",
        error_type="wrong_symbol",
        line_number=1,
        offset=0,
        original_text="[你好]",
    )
    candidates = CandidateGenerator().generate(text, error)
    assert candidates
    assert candidates[0].replacement == "「你好」"
    assert candidates[0].start_offset == 0
    assert candidates[0].end_offset == 4
    results.append(("wrong_symbol candidates", "ok", candidates[0].replacement))
except Exception as exc:
    errors.append(("wrong_symbol candidates", str(exc)))


# Test 2: consecutive 候选不让模型构造 offset
try:
    text = TextDoc("」他说道。」我很好」")
    offset = text.text.find("。") + 1
    error = ErrorRecord(
        error_id="e-consecutive",
        error_type="consecutive",
        line_number=1,
        offset=offset,
        original_text=text.text[max(0, offset - 5):offset + 6],
    )
    candidates = CandidateGenerator().generate(text, error)
    assert any(c.start_offset == offset and c.replacement == "「" for c in candidates)
    results.append(("consecutive candidates", "ok", f"{len(candidates)} candidates"))
except Exception as exc:
    errors.append(("consecutive candidates", str(exc)))


# Test 3: missing_bracket 候选包裹冒号后的台词
try:
    text = TextDoc("他说道：你好啊")
    error = ErrorRecord(
        error_id="e-missing",
        error_type="missing_bracket",
        line_number=1,
        offset=0,
        original_text=text.text,
    )
    candidate = CandidateGenerator().generate(text, error)[0]
    assert candidate.original(text) == "你好啊"
    assert candidate.replacement == "「你好啊」"
    results.append(("missing_bracket candidates", "ok", candidate.replacement))
except Exception as exc:
    errors.append(("missing_bracket candidates", str(exc)))


# Test 4: decision agent 应用候选并修改 TextDoc
try:
    text = TextDoc("[你好]结束")
    queue = ErrorQueue([
        ErrorRecord(
            error_id="e-apply",
            error_type="wrong_symbol",
            line_number=1,
            offset=0,
            original_text="[你好]",
        )
    ])
    tracker, tmpdir = make_tracker(queue, "apply.txt")
    client = MockDecisionClient([
        json.dumps({"decision": "apply", "choice_id": "c1", "reason": "是对话"}, ensure_ascii=False)
    ])
    agent = CandidateDecisionAgent(text, queue, client, tracker, verifier=CorrectionVerifier())
    result = agent.run_all()[0]
    assert result.verdict == "pass"
    assert text.text == "「你好」结束"
    assert queue.get("e-apply").status == "fixed"
    assert client.call_count == 1
    shutil.rmtree(tmpdir)
    results.append(("decision apply", "ok", text.text))
except Exception as exc:
    errors.append(("decision apply", str(exc)))


# Test 5: invalid JSON 后重试一次
try:
    text = TextDoc("[你好]结束")
    queue = ErrorQueue([
        ErrorRecord(
            error_id="e-retry",
            error_type="wrong_symbol",
            line_number=1,
            offset=0,
            original_text="[你好]",
        )
    ])
    tracker, tmpdir = make_tracker(queue, "retry.txt")
    client = MockDecisionClient([
        "我觉得应该修",
        json.dumps({"decision": "apply", "choice_id": "c1", "reason": "重试后选择"}, ensure_ascii=False),
    ])
    agent = CandidateDecisionAgent(
        text,
        queue,
        client,
        tracker,
        verifier=CorrectionVerifier(),
        max_decision_retries=2,
    )
    result = agent.run_all()[0]
    assert result.verdict == "pass"
    assert client.call_count == 2
    assert text.text == "「你好」结束"
    shutil.rmtree(tmpdir)
    results.append(("decision retry", "ok", f"calls={client.call_count}"))
except Exception as exc:
    errors.append(("decision retry", str(exc)))


# Test 6: choose_candidate 工具调用同样只选择候选
try:
    text = TextDoc("[你好]结束")
    queue = ErrorQueue([
        ErrorRecord(
            error_id="e-tool",
            error_type="wrong_symbol",
            line_number=1,
            offset=0,
            original_text="[你好]",
        )
    ])
    tracker, tmpdir = make_tracker(queue, "tool.txt")
    client = MockDecisionClient([
        ChatResult(content="", tool_calls=[
            ToolCall(
                id="t1",
                name="choose_candidate",
                arguments={"choice_id": "c1", "reason": "工具选择候选"},
            )
        ], raw={})
    ])
    agent = CandidateDecisionAgent(text, queue, client, tracker, verifier=CorrectionVerifier())
    result = agent.run_all()[0]
    assert result.verdict == "pass"
    assert text.text == "「你好」结束"
    assert "choose_candidate" in client.tool_names_per_call[0]
    assert "apply_fix" not in client.tool_names_per_call[0]
    shutil.rmtree(tmpdir)
    results.append(("decision tool call", "ok", text.text))
except Exception as exc:
    errors.append(("decision tool call", str(exc)))


# Test 7: skip 决策不修改文本
try:
    text = TextDoc("[注]结束")
    queue = ErrorQueue([
        ErrorRecord(
            error_id="e-skip",
            error_type="wrong_symbol",
            line_number=1,
            offset=0,
            original_text="[注]",
        )
    ])
    tracker, tmpdir = make_tracker(queue, "skip.txt")
    client = MockDecisionClient([
        json.dumps({"decision": "skip", "choice_id": "", "reason": "注释不是对话"}, ensure_ascii=False)
    ])
    agent = CandidateDecisionAgent(text, queue, client, tracker, verifier=CorrectionVerifier())
    result = agent.run_all()[0]
    assert result.verdict == "uncertain"
    assert text.text == "[注]结束"
    assert queue.get("e-skip").status == "skipped"
    shutil.rmtree(tmpdir)
    results.append(("decision skip", "ok", result.reason))
except Exception as exc:
    errors.append(("decision skip", str(exc)))


print("=" * 55)
print("  Stage 15 Verification Report — Candidate Decision")
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
