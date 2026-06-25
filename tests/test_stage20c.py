"""Stage 20c verification: context budgets."""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.agent.candidates import CorrectionCandidate  # noqa: E402
from src.agent.decision import CandidateDecisionAgent  # noqa: E402
from src.agent.prompts import (  # noqa: E402
    build_user_prompt,
    context_budget_for_error_type,
)
from src.core.error_queue import ErrorQueue  # noqa: E402
from src.core.error_record import ErrorRecord  # noqa: E402
from src.core.text import TextDoc  # noqa: E402
from src.model.client import TokenUsage  # noqa: E402
from src.model.token_tracker import TokenTracker  # noqa: E402


results = []
errors = []


def check(name, condition, detail=""):
    if condition:
        results.append(f"  [OK] {name}{': ' + detail if detail else ''}")
    else:
        errors.append(f"  [FAIL] {name}{': ' + detail if detail else ''}")


def make_error(error_type: str, before: str, after: str) -> ErrorRecord:
    return ErrorRecord(
        error_type=error_type,
        line_number=1,
        offset=len(before),
        context_before=before,
        context_after=after,
        original_text="TARGET",
    )


def candidate_prompt_payload(error_type: str) -> dict:
    before = "FAR_BEFORE" + ("a" * 1500)
    after = ("b" * 1500) + "FAR_AFTER"
    text = TextDoc(before + "TARGET" + after)
    error = make_error(error_type, before, after)
    candidate = CorrectionCandidate(
        candidate_id="c1",
        error_id=error.error_id,
        error_type=error.error_type,
        start_offset=len(before),
        end_offset=len(before) + len("TARGET"),
        replacement="REPLACED",
        description="test",
    )
    agent = CandidateDecisionAgent(
        text_doc=text,
        error_queue=ErrorQueue(),
        model_client=None,
        tracker=None,
        rule_precheck=False,
    )
    prompt = agent._user_prompt(error, [candidate])
    return json.loads(prompt.split("\n\n请立即", 1)[0])


print("=" * 55)
print("  Stage 20c Verification Report — Context Budget")
print("=" * 55)

try:
    check("consecutive budget", context_budget_for_error_type("consecutive") == 200)
    check("long_dialogue budget", context_budget_for_error_type("long_dialogue") == 2000)
    check("missing_bracket budget", context_budget_for_error_type("missing_bracket") == 2000)
except Exception as exc:
    errors.append(f"  [FAIL] budget constants: {exc}")

try:
    small = candidate_prompt_payload("consecutive")
    large = candidate_prompt_payload("long_dialogue")
    small_text = json.dumps(small, ensure_ascii=False)
    large_text = json.dumps(large, ensure_ascii=False)
    check("prompt records budget", small["error"]["context_budget_chars"] == 200)
    check("long prompt records budget", large["error"]["context_budget_chars"] == 2000)
    check("small prompt trims far context", "FAR_BEFORE" not in small_text)
    check("large prompt includes far context", "FAR_BEFORE" in large_text)
    check("long prompt larger", len(large_text) > len(small_text) * 2)
except Exception as exc:
    errors.append(f"  [FAIL] candidate prompt budget: {exc}")

try:
    before = "FAR_BEFORE" + ("a" * 1500)
    after = ("b" * 1500) + "FAR_AFTER"
    small_prompt = build_user_prompt(make_error("consecutive", before, after))
    large_prompt = build_user_prompt(make_error("missing_bracket", before, after))
    check("tool prompt trims far context", "FAR_BEFORE" not in small_prompt)
    check("tool prompt expands far context", "FAR_BEFORE" in large_prompt)
except Exception as exc:
    errors.append(f"  [FAIL] tool prompt budget: {exc}")

try:
    tracker = TokenTracker(context_limit=1000)
    record = tracker.record(
        source="unit",
        error_id="e-1",
        error_type="long_dialogue",
        usage=TokenUsage(prompt_tokens=125, completion_tokens=25, total_tokens=150),
    )
    payload = tracker.to_json()
    check("token tracker context pct", record.context_window_pct == 12.5)
    check("token json context pct", payload["records"][0]["context_window_pct"] == 12.5)
except Exception as exc:
    errors.append(f"  [FAIL] token context pct: {exc}")

print()
for r in results:
    print(r)
for e in errors:
    print(e)
print(f"\n  {len(results)} passed, {len(errors)} failed")
print("=" * 55)
sys.exit(1 if errors else 0)
