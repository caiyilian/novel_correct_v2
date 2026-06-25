"""Stage 20a verification: TokenUsage parsing."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.model.client import (  # noqa: E402
    ChatResult,
    ModelConfig,
    OpenAICompatibleClient,
    TokenUsage,
)


results = []
errors = []


def check(name, condition, detail=""):
    if condition:
        results.append(f"  [OK] {name}{': ' + detail if detail else ''}")
    else:
        errors.append(f"  [FAIL] {name}{': ' + detail if detail else ''}")


def payload_with(extra):
    payload = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": "ok",
                }
            }
        ]
    }
    payload.update(extra)
    return payload


print("=" * 55)
print("  Stage 20a Verification Report — TokenUsage")
print("=" * 55)

client = OpenAICompatibleClient(ModelConfig(heartbeat_interval=None))

try:
    result = client._parse_chat_result(
        payload_with({"prompt_eval_count": 123, "eval_count": 45})
    )
    check("ollama native usage type", isinstance(result.usage, TokenUsage))
    check(
        "ollama native token totals",
        result.usage.prompt_tokens == 123
        and result.usage.completion_tokens == 45
        and result.usage.total_tokens == 168,
        str(result.usage),
    )
except Exception as exc:
    errors.append(f"  [FAIL] ollama native usage: {exc}")

try:
    result = client._parse_chat_result(
        payload_with({
            "usage": {
                "prompt_tokens": 200,
                "completion_tokens": 30,
                "total_tokens": 230,
            }
        })
    )
    check(
        "openai usage fields",
        result.usage.prompt_tokens == 200
        and result.usage.completion_tokens == 30
        and result.usage.total_tokens == 230,
        str(result.usage),
    )
except Exception as exc:
    errors.append(f"  [FAIL] openai usage fields: {exc}")

try:
    result = client._parse_chat_result(
        payload_with({
            "usage": {
                "prompt_tokens": "7",
                "completion_tokens": "5",
            }
        })
    )
    check(
        "usage total fallback",
        result.usage.prompt_tokens == 7
        and result.usage.completion_tokens == 5
        and result.usage.total_tokens == 12,
        str(result.usage),
    )
except Exception as exc:
    errors.append(f"  [FAIL] usage total fallback: {exc}")

try:
    result = client._parse_chat_result(payload_with({}))
    check("missing usage defaults", result.usage == TokenUsage(), str(result.usage))
except Exception as exc:
    errors.append(f"  [FAIL] missing usage defaults: {exc}")

try:
    result = ChatResult(content="ok")
    check("ChatResult default usage", result.usage == TokenUsage(), str(result.usage))
except Exception as exc:
    errors.append(f"  [FAIL] ChatResult default usage: {exc}")

print()
for r in results:
    print(r)
for e in errors:
    print(e)
print(f"\n  {len(results)} passed, {len(errors)} failed")
print("=" * 55)
sys.exit(1 if errors else 0)
