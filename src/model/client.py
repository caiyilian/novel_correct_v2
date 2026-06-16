"""
OpenAI-compatible model client for talking to Ollama and other LLM backends.

Reused and adapted from opencode-novel-loop/dialoop/model_client.py.
Supports tool calling, retries, timeout handling, and config loading from ip_config.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from .protocol import ToolSpec


# ─── Config loading from ip_config ─────────────────────

def _load_ip_config() -> dict[str, str]:
    """Load configuration from ip_config file in project root."""
    config: dict[str, str] = {}
    # Search upward from this file's directory for ip_config
    search_dir = Path(__file__).resolve().parent.parent.parent  # src/model/ -> src/ -> project root
    ip_path = search_dir / "ip_config"
    if ip_path.exists():
        with open(ip_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, value = line.partition("=")
                    config[key.strip()] = value.strip()
    return config


_ip_config = _load_ip_config()

DEFAULT_BASE_URL = _ip_config.get("OLLAMA_BASE_URL", "http://localhost:11434/v1")
_DEFAULT_MODEL_RAW = _ip_config.get("OLLAMA_MODEL", "qwen3:30b")
DEFAULT_API_KEY = "ollama"
DEFAULT_MODEL = _DEFAULT_MODEL_RAW


# ─── Error types ────────────────────────────────────────


class ModelClientError(RuntimeError):
    """Base error for model client failures."""


class ModelHTTPError(ModelClientError):
    """Raised when an OpenAI-compatible endpoint returns a non-2xx response."""


class ModelResponseError(ModelClientError):
    """Raised when the endpoint response shape is not usable."""


class ModelTimeoutError(ModelClientError):
    """Raised when the model endpoint times out after retry attempts."""


# ─── Data classes ───────────────────────────────────────


@dataclass(frozen=True)
class ModelConfig:
    base_url: str = DEFAULT_BASE_URL
    api_key: str = DEFAULT_API_KEY
    model: str = DEFAULT_MODEL
    timeout: float = 120.0
    retries: int = 2
    retry_delay: float = 5.0


@dataclass(frozen=True)
class ChatMessage:
    role: str
    content: str
    name: Optional[str] = None
    tool_call_id: Optional[str] = None
    tool_calls: Optional[list[dict[str, Any]]] = None

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "role": self.role,
            "content": self.content,
        }
        if self.name:
            data["name"] = self.name
        if self.tool_call_id:
            data["tool_call_id"] = self.tool_call_id
        if self.tool_calls:
            data["tool_calls"] = self.tool_calls
        return data


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]

    def to_openai_tool_call(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "type": "function",
            "function": {
                "name": self.name,
                "arguments": json.dumps(self.arguments, ensure_ascii=False),
            },
        }


@dataclass(frozen=True)
class ChatResult:
    content: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ModelConnectionStatus:
    ok: bool
    message: str
    model: str
    base_url: str


# ─── Client ─────────────────────────────────────────────


class OpenAICompatibleClient:
    """Client for OpenAI-compatible chat completion APIs (Ollama, etc.)."""

    def __init__(self, config: Optional[ModelConfig] = None):
        self.config = config or ModelConfig()

    @property
    def chat_completions_url(self) -> str:
        base = self.config.base_url.rstrip("/")
        # Ollama uses /v1/chat/completions when configured with /v1 path
        if base.endswith("/chat/completions"):
            return base
        # If base URL is just host:port, append /v1/chat/completions
        # If base URL already has /v1, append chat/completions
        if base.endswith("/v1"):
            return f"{base}/chat/completions"
        # For Ollama native API: /api/chat
        if base.endswith("/api"):
            return f"{base}/chat"
        return f"{base}/v1/chat/completions"

    def chat(
        self,
        messages: list[ChatMessage],
        tools: Optional[list[ToolSpec]] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> ChatResult:
        body: dict[str, Any] = {
            "model": self.config.model,
            "messages": [message.to_dict() for message in messages],
            "keep_alive": "24h",  # 全天保持模型常驻
        }
        if tools:
            body["tools"] = [tool.to_openai_tool() for tool in tools]
        if temperature is not None:
            body["temperature"] = temperature
        if max_tokens is not None:
            body["max_tokens"] = max_tokens

        payload = self._post_json(self.chat_completions_url, body)
        return self._parse_chat_result(payload)

    def check_connection(self) -> ModelConnectionStatus:
        """Quick connectivity check."""
        try:
            result = self.chat(
                messages=[
                    ChatMessage(role="system", content="You are a connection checker."),
                    ChatMessage(role="user", content="Reply with OK."),
                ],
                temperature=0,
                max_tokens=8,
            )
        except ModelClientError as error:
            return ModelConnectionStatus(
                ok=False,
                message=str(error),
                model=self.config.model,
                base_url=self.config.base_url,
            )

        content = result.content.strip()
        return ModelConnectionStatus(
            ok=True,
            message=content or "connection succeeded",
            model=self.config.model,
            base_url=self.config.base_url,
        )

    # ─── Internal helpers ─────────────────────────────

    def _post_json(self, url: str, body: dict[str, Any]) -> dict[str, Any]:
        data = self._post_json_with_retries(url, body)
        try:
            payload = json.loads(data)
        except json.JSONDecodeError as error:
            raise ModelResponseError(
                f"model endpoint returned invalid JSON: {error}"
            ) from error
        if not isinstance(payload, dict):
            raise ModelResponseError(
                "model endpoint returned a non-object JSON response"
            )
        return payload

    def _parse_chat_result(self, payload: dict[str, Any]) -> ChatResult:
        choices = payload.get("choices")
        if not isinstance(choices, list) or not choices:
            raise ModelResponseError("model response missing choices")

        choice = choices[0]
        if not isinstance(choice, dict):
            raise ModelResponseError("model response choice must be an object")

        message = choice.get("message")
        if not isinstance(message, dict):
            raise ModelResponseError("model response choice missing message")

        content = message.get("content") or ""
        if not isinstance(content, str):
            raise ModelResponseError(
                "model response message content must be a string"
            )

        # qwen3 等模型将思维链放在 reasoning 字段，最终回答在 content
        # 如果 content 为空但有 reasoning，降级使用 reasoning
        if not content:
            reasoning = message.get("reasoning")
            if isinstance(reasoning, str) and reasoning.strip():
                content = reasoning

        return ChatResult(
            content=content,
            tool_calls=self._parse_tool_calls(message.get("tool_calls")),
            raw=payload,
        )

    def _parse_tool_calls(self, value: Any) -> list[ToolCall]:
        if value is None:
            return []
        if not isinstance(value, list):
            raise ModelResponseError("model response tool_calls must be a list")

        calls: list[ToolCall] = []
        for index, item in enumerate(value):
            if not isinstance(item, dict):
                raise ModelResponseError("tool call must be an object")

            function = item.get("function")
            if not isinstance(function, dict):
                raise ModelResponseError("tool call missing function object")

            name = function.get("name")
            raw_arguments = function.get("arguments") or "{}"
            if not isinstance(name, str) or not name:
                raise ModelResponseError("tool call function missing name")
            if not isinstance(raw_arguments, str):
                raise ModelResponseError(
                    "tool call function arguments must be a JSON string"
                )

            try:
                arguments = json.loads(raw_arguments)
            except json.JSONDecodeError as error:
                raise ModelResponseError(
                    f"tool call arguments are invalid JSON: {error}"
                ) from error
            if not isinstance(arguments, dict):
                raise ModelResponseError(
                    "tool call arguments must decode to an object"
                )

            calls.append(
                ToolCall(
                    id=str(item.get("id") or f"tool-call-{index}"),
                    name=name,
                    arguments=arguments,
                )
            )
        return calls

    def _post_json_with_retries(self, url: str, body: dict[str, Any]) -> str:
        attempts = max(0, self.config.retries) + 1
        for attempt in range(1, attempts + 1):
            request = urllib.request.Request(
                url=url,
                data=json.dumps(body).encode("utf-8"),
                headers={
                    "Authorization": f"Bearer {self.config.api_key}",
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
                method="POST",
            )

            try:
                with urllib.request.urlopen(
                    request, timeout=self.config.timeout
                ) as response:
                    return response.read().decode("utf-8")
            except urllib.error.HTTPError as error:
                detail = error.read().decode("utf-8", errors="replace")
                raise ModelHTTPError(
                    f"HTTP {error.code} from model endpoint: {detail}"
                ) from error
            except urllib.error.URLError as error:
                if _is_timeout_error(error.reason) and attempt < attempts:
                    self._sleep_before_retry()
                    continue
                if _is_timeout_error(error.reason):
                    raise ModelTimeoutError(
                        f"model endpoint request timed out after {attempt} attempt(s)"
                    ) from error
                raise ModelClientError(
                    f"model endpoint connection failed: {error.reason}"
                ) from error
            except TimeoutError as error:
                if attempt < attempts:
                    self._sleep_before_retry()
                    continue
                raise ModelTimeoutError(
                    f"model endpoint request timed out after {attempt} attempt(s)"
                ) from error

        raise ModelTimeoutError(
            f"model endpoint request timed out after {attempts} attempt(s)"
        )

    def _sleep_before_retry(self) -> None:
        if self.config.retry_delay > 0:
            time.sleep(self.config.retry_delay)


def _is_timeout_error(reason: Any) -> bool:
    if isinstance(reason, TimeoutError):
        return True
    return "timed out" in str(reason).lower()
