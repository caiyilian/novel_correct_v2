"""Stage 20b verification: TokenTracker and LLM call logging."""

import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.agent.decision import CandidateDecisionAgent  # noqa: E402
from src.agent.loop import CorrectionAgent  # noqa: E402
from src.core.error_queue import ErrorQueue  # noqa: E402
from src.core.error_record import ErrorRecord  # noqa: E402
from src.core.progress import ProgressTracker  # noqa: E402
from src.core.text import TextDoc  # noqa: E402
from src.model.client import ChatResult, TokenUsage, ToolCall  # noqa: E402
from src.model.token_tracker import TokenTracker  # noqa: E402


results = []
errors = []


def check(name, condition, detail=""):
    if condition:
        results.append(f"  [OK] {name}{': ' + detail if detail else ''}")
    else:
        errors.append(f"  [FAIL] {name}{': ' + detail if detail else ''}")


class DecisionMockClient:
    def chat(self, **kwargs):
        return ChatResult(
            content='{"decision":"apply","choice_id":"c1","reason":"ok"}',
            usage=TokenUsage(prompt_tokens=11, completion_tokens=5, total_tokens=16),
        )


class ToolMockClient:
    def __init__(self, error_id):
        self.error_id = error_id

    def chat(self, **kwargs):
        return ChatResult(
            content="",
            tool_calls=[
                ToolCall(
                    id="call-1",
                    name="skip_error",
                    arguments={"error_id": self.error_id, "reason": "not an error"},
                )
            ],
            usage=TokenUsage(prompt_tokens=7, completion_tokens=3, total_tokens=10),
        )


def make_wrong_symbol_queue() -> ErrorQueue:
    queue = ErrorQueue()
    queue.add(
        ErrorRecord(
            error_type="wrong_symbol",
            line_number=1,
            offset=0,
            context_before="",
            context_after="\u4f60\u597d]\n",
            original_text="[",
        )
    )
    return queue


print("=" * 55)
print("  Stage 20b Verification Report — TokenTracker")
print("=" * 55)

try:
    tracker = TokenTracker(context_limit=100)
    record = tracker.record(
        source="unit",
        error_id="e-1",
        error_type="wrong_symbol",
        usage=TokenUsage(prompt_tokens=25, completion_tokens=5, total_tokens=30),
    )
    check("record created", record.total_tokens == 30, str(record))
    check("context pct", record.context_window_pct == 25.0, str(record))
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "token_usage.json"
        tracker.save(path)
        payload = json.loads(path.read_text(encoding="utf-8"))
        check("save json", payload["total_tokens"] == 30, str(payload))
        check("record fields", payload["records"][0]["source"] == "unit")
except Exception as exc:
    errors.append(f"  [FAIL] tracker direct usage: {exc}")

try:
    with tempfile.TemporaryDirectory() as tmp:
        text = TextDoc("[\u4f60\u597d]\n")
        queue = make_wrong_symbol_queue()
        tracker = TokenTracker()
        agent = CandidateDecisionAgent(
            text_doc=text,
            error_queue=queue,
            model_client=DecisionMockClient(),
            tracker=ProgressTracker("decision.txt", checkpoint_dir=tmp),
            rule_precheck=False,
            llm_fallback=True,
            token_tracker=tracker,
        )
        result = agent.run_all()[0]
        check("decision agent applied", result.verdict == "pass", result.reason)
        check("decision usage recorded", tracker.total_tokens == 16, str(tracker.to_json()))
        check("decision source", tracker.records[0].source == "candidate_decision")
except Exception as exc:
    errors.append(f"  [FAIL] decision agent token logging: {exc}")

try:
    with tempfile.TemporaryDirectory() as tmp:
        text = TextDoc("[\u4f60\u597d]\n")
        queue = make_wrong_symbol_queue()
        tracker = TokenTracker()
        error_id = queue.pending()[0].error_id
        agent = CorrectionAgent(
            text_doc=text,
            error_queue=queue,
            model_client=ToolMockClient(error_id),
            tracker=ProgressTracker("tool.txt", checkpoint_dir=tmp),
            token_tracker=tracker,
        )
        result = agent.run_all()[0]
        check("tool agent skipped", result.verdict == "uncertain", result.reason)
        check("tool usage recorded", tracker.total_tokens == 10, str(tracker.to_json()))
        check("tool source", tracker.records[0].source == "correction_agent")
except Exception as exc:
    errors.append(f"  [FAIL] tool agent token logging: {exc}")

try:
    empty = TokenTracker()
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "token_usage.json"
        empty.save(path)
        payload = json.loads(path.read_text(encoding="utf-8"))
        check("empty tracker save", payload["total_records"] == 0, str(payload))
except Exception as exc:
    errors.append(f"  [FAIL] empty tracker save: {exc}")

print()
for r in results:
    print(r)
for e in errors:
    print(e)
print(f"\n  {len(results)} passed, {len(errors)} failed")
print("=" * 55)
sys.exit(1 if errors else 0)
