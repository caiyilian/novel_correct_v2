"""
Protocol definitions for LLM tool calling.

Reused and adapted from opencode-novel-loop/dialoop/protocol.py.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any


class ProtocolError(ValueError):
    """Raised when model protocol data cannot be parsed or validated."""


@dataclass(frozen=True)
class ToolSpec:
    """Specification for a tool/function the LLM can call."""
    name: str
    description: str
    parameters: dict[str, Any]

    def to_openai_tool(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


@dataclass(frozen=True)
class JsonAction:
    """A parsed JSON-mode action from the LLM."""
    action: str
    args: dict[str, Any]


def _extract_json_object(text: str) -> str:
    """Extract the first JSON object `{...}` from a model response."""
    stripped = text.strip()
    # Remove markdown code fences
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if len(lines) >= 3 and lines[-1].strip() == "```":
            stripped = "\n".join(lines[1:-1]).strip()
            if stripped.startswith("json"):
                stripped = stripped[4:].strip()

    if stripped.startswith("{") and stripped.endswith("}"):
        return stripped

    start = stripped.find("{")
    end = stripped.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ProtocolError("model output does not contain a JSON object")
    return stripped[start: end + 1]


def parse_json_action(text: str, known_actions: set[str]) -> JsonAction:
    """Parse a JSON action object from model output."""
    try:
        payload = json.loads(_extract_json_object(text))
    except json.JSONDecodeError as error:
        raise ProtocolError(f"invalid JSON action: {error}") from error

    if not isinstance(payload, dict):
        raise ProtocolError("JSON action must be an object")

    action = payload.get("action")
    args = payload.get("args", {})
    if not isinstance(action, str) or not action:
        raise ProtocolError("JSON action must include a non-empty string `action`")
    if not isinstance(args, dict):
        raise ProtocolError("JSON action `args` must be an object")

    if action not in known_actions:
        raise ProtocolError(f"unknown JSON action: {action}")

    return JsonAction(action=action, args=args)
