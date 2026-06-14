"""
FreeTheAI API 测试脚本
测试免费 API 是否可用，以及工具调用是否正常
"""

import json
import time
import sys
import io
import urllib.request
import urllib.error
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

RATE_LIMIT_SECONDS = 7


def load_free_api_config():
    config = {
        "base_url": "https://api.freetheai.xyz/v1",
        "api_key": "",
        "model": "bbl/gemini-2.5-flash"
    }
    config_path = Path("free_api_config")
    if config_path.exists():
        for line in config_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                key, value = key.strip(), value.strip()
                if key == "FREE_API_BASE_URL":
                    config["base_url"] = value
                elif key == "FREE_API_KEY":
                    config["api_key"] = value
                elif key == "FREE_API_MODEL":
                    config["model"] = value
    return config


def api_call(config, body, timeout=30, max_retries=3):
    last_error = None
    for attempt in range(max_retries):
        try:
            request = urllib.request.Request(
                url=f"{config['base_url']}/chat/completions",
                data=json.dumps(body).encode("utf-8"),
                headers={
                    "Authorization": f"Bearer {config['api_key']}",
                    "Content-Type": "application/json",
                    "Accept": "application/json"
                },
                method="POST"
            )
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            last_error = e
            if e.code == 429:
                wait = RATE_LIMIT_SECONDS * (attempt + 1)
                print(f"  [429] Rate limited, waiting {wait}s (attempt {attempt+1}/{max_retries})")
                time.sleep(wait)
            else:
                detail = e.read().decode("utf-8", errors="replace")
                print(f"  [HTTP {e.code}] {detail[:200]}")
                return None
        except Exception as e:
            last_error = e
            print(f"  [Error] {e}")
            if attempt < max_retries - 1:
                time.sleep(RATE_LIMIT_SECONDS)
    print(f"  Failed after {max_retries} attempts: {last_error}")
    return None


def test_basic_call(config):
    print(f"[1/3] Basic chat call...")
    print(f"  Model: {config['model']}")

    body = {
        "model": config["model"],
        "temperature": 0,
        "max_tokens": 64,
        "messages": [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Reply with one word: OK"}
        ]
    }

    result = api_call(config, body)
    if result and "choices" in result:
        content = result["choices"][0]["message"]["content"]
        print(f"  OK! Response: {content[:100]}")
        return True
    print(f"  FAILED")
    return False


def test_tool_calling(config):
    print(f"\n[2/3] Tool calling...")

    body = {
        "model": config["model"],
        "temperature": 0,
        "max_tokens": 128,
        "messages": [
            {"role": "system", "content": "When tools are available, call the requested function instead of replying with normal text."},
            {"role": "user", "content": "Call the ping tool with value hello_world."}
        ],
        "tools": [
            {
                "type": "function",
                "function": {
                    "name": "ping",
                    "description": "Echoes the provided value.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "value": {"type": "string", "description": "A value to echo."}
                        },
                        "required": ["value"]
                    }
                }
            }
        ],
        "tool_choice": {"type": "function", "function": {"name": "ping"}}
    }

    result = api_call(config, body)
    if result and "choices" in result:
        message = result["choices"][0]["message"]
        if message.get("tool_calls"):
            tc = message["tool_calls"][0]
            print(f"  OK! Tool: {tc['function']['name']}, Args: {tc['function']['arguments']}")
            return True
        else:
            print(f"  No tool call, got text: {message.get('content', '')[:100]}")
            return False
    print(f"  FAILED")
    return False


def test_correction_tools(config):
    print(f"\n[3/3] Correction tools...")

    body = {
        "model": config["model"],
        "temperature": 0,
        "max_tokens": 256,
        "messages": [
            {"role": "system", "content": "You are a novel text correction expert. Analyze the bracket error and call the appropriate tool. Do NOT reply with text, only call tools."},
            {"role": "user", "content": "Error detected at offset 0-5: [hello] should be fixed. The original text segment is: [hello] world. Call apply_fix with error_id=e-001, start_offset=0, end_offset=7, replacement='「hello」 world'"}
        ],
        "tools": [
            {
                "type": "function",
                "function": {
                    "name": "apply_fix",
                    "description": "Apply a correction to the text",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "error_id": {"type": "string"},
                            "start_offset": {"type": "integer"},
                            "end_offset": {"type": "integer"},
                            "replacement": {"type": "string"}
                        },
                        "required": ["error_id", "start_offset", "end_offset", "replacement"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "skip_error",
                    "description": "Skip this error",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "error_id": {"type": "string"},
                            "reason": {"type": "string"}
                        },
                        "required": ["error_id", "reason"]
                    }
                }
            }
        ],
        "tool_choice": "auto"
    }

    result = api_call(config, body)
    if result and "choices" in result:
        message = result["choices"][0]["message"]
        if message.get("tool_calls"):
            tc = message["tool_calls"][0]
            print(f"  OK! Tool: {tc['function']['name']}")
            print(f"  Args: {tc['function']['arguments']}")
            return True
        else:
            print(f"  No tool call, got text: {message.get('content', '')[:200]}")
            return False
    print(f"  FAILED")
    return False


def main():
    print("=" * 55)
    print("  FreeTheAI API Test")
    print("=" * 55)
    print()

    config = load_free_api_config()

    basic_ok = test_basic_call(config)
    time.sleep(RATE_LIMIT_SECONDS)

    tool_ok = test_tool_calling(config)
    time.sleep(RATE_LIMIT_SECONDS)

    correction_ok = test_correction_tools(config)

    print()
    print("=" * 55)
    print("  Results")
    print("=" * 55)
    print(f"  Basic chat:    {'PASS' if basic_ok else 'FAIL'}")
    print(f"  Tool calling:  {'PASS' if tool_ok else 'N/A'}")
    print(f"  Correction:    {'PASS' if correction_ok else 'N/A'}")

    if tool_ok and correction_ok:
        print("\n  Full tool calling support - can run correction pipeline!")
    elif basic_ok:
        print("\n  Basic chat only - will use simplified correction mode")
    print()


if __name__ == "__main__":
    main()
