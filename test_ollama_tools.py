"""
Ollama Tool Calling 快速验证脚本

测试服务器的 Ollama 是否能正确调用 tools。
整个过程应该 1 分钟内跑完。
"""

import json
import sys
import time
from pathlib import Path

# 加载 ip_config
def load_config():
    config = {"base_url": "http://localhost:11434", "model": "qwen3:32b"}
    for path in [Path("ip_config"), Path("../ip_config")]:
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, _, v = line.partition("=")
                    if k.strip() == "OLLAMA_BASE_URL":
                        config["base_url"] = v.strip()
                    elif k.strip() == "OLLAMA_MODEL":
                        config["model"] = v.strip()
            break
    return config


def test_tool_calling():
    cfg = load_config()
    base = cfg["base_url"].rstrip("/")
    model = cfg["model"]

    print(f"Ollama 服务器: {base}")
    print(f"模型: {model}")
    print()

    # 测试 1: 连接检查
    print("[1/5] 检查 Ollama 版本...")
    try:
        import urllib.request
        with urllib.request.urlopen(f"{base}/api/version", timeout=5) as r:
            info = json.loads(r.read())
            print(f"  Ollama 版本: {info.get('version', 'unknown')}")
    except Exception as e:
        print(f"  [FAIL] 连接失败: {e}")
        return False

    # 测试 2: 模型是否可用
    print("[2/5] 检查模型是否已拉取...")
    try:
        with urllib.request.urlopen(f"{base}/api/tags", timeout=5) as r:
            tags = json.loads(r.read())
            models = [m["name"] for m in tags.get("models", [])]
            if model in models:
                print(f"  [OK] 模型 {model} 已就绪")
            else:
                print(f"  [!!] 模型 {model} 不在列表中: {models}")
                print(f"  请先运行: ollama pull {model}")
                return False
    except Exception as e:
        print(f"  [FAIL] 获取模型列表失败: {e}")
        return False

    # 测试 3: 基本对话（不带工具）
    print("[3/5] 基本对话（无 tools）...")
    body = {
        "model": model,
        "messages": [{"role": "user", "content": "Say OK"}],
        "stream": False,
        "options": {"temperature": 0},
    }
    try:
        req = urllib.request.Request(
            f"{base}/v1/chat/completions",
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        t0 = time.time()
        with urllib.request.urlopen(req, timeout=120) as r:
            resp = json.loads(r.read())
        elapsed = time.time() - t0
        content = resp["choices"][0]["message"]["content"]
        print(f"  [OK] 响应: {repr(content[:60])} ({elapsed:.1f}s)")
    except Exception as e:
        print(f"  [FAIL] 基本对话失败: {e}")
        # 可能是冷启动，再试一次
        print(f"  可能是冷启动，等一下再试...")
        time.sleep(10)
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                resp = json.loads(r.read())
            elapsed = time.time() - t0 - 10
            content = resp["choices"][0]["message"]["content"]
            print(f"  [OK] 重试成功: {repr(content[:60])} ({elapsed:.1f}s)")
        except Exception as e2:
            print(f"  [FAIL] 重试也失败了: {e2}")
            return False

    # 测试 4: 工具调用（核心测试）
    print("[4/5] 工具调用测试...")
    tools = [
        {
            "type": "function",
            "function": {
                "name": "get_weather",
                "description": "Get the weather for a city",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "city": {"type": "string", "description": "City name"},
                    },
                    "required": ["city"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "apply_fix",
                "description": "Replace text at a specific offset range",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "error_id": {"type": "string"},
                        "start_offset": {"type": "integer", "minimum": 0},
                        "end_offset": {"type": "integer", "minimum": 0},
                        "replacement": {"type": "string"},
                    },
                    "required": ["error_id", "start_offset", "end_offset", "replacement"],
                },
            },
        },
    ]
    body2 = {
        "model": model,
        "messages": [
            {"role": "system", "content": "You have tools available. Use them when asked."},
            {"role": "user", "content": "What's the weather in Tokyo? Call the get_weather tool."},
        ],
        "tools": tools,
        "stream": False,
        "options": {"temperature": 0},
    }
    try:
        req2 = urllib.request.Request(
            f"{base}/v1/chat/completions",
            data=json.dumps(body2).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        t0 = time.time()
        with urllib.request.urlopen(req2, timeout=120) as r:
            resp2 = json.loads(r.read())
        elapsed = time.time() - t0
        msg = resp2["choices"][0]["message"]
        if "tool_calls" in msg and msg["tool_calls"]:
            tc = msg["tool_calls"][0]
            fn = tc.get("function", {})
            print(f"  [OK] 模型调用了工具: {fn.get('name')}")
            print(f"       参数: {fn.get('arguments', {})}")
            assert fn.get("name") == "get_weather", "工具名不对"
            args = json.loads(fn.get("arguments", "{}"))
            assert "city" in args, "缺少 city 参数"
            print(f"       耗时: {elapsed:.1f}s")
        else:
            content = msg.get("content", "")
            print(f"  [!!] 模型没有调用工具, 而是回复了: {content[:80]}")
            print(f"  这可能意味着你的 Ollama 版本不支持 tool calling")
            print(f"  或模型 qwen3:32b 的 function calling 能力有问题")
            return False
    except Exception as e:
        print(f"  [FAIL] 工具调用测试失败: {e}")
        return False

    # 测试 5: 模拟纠错场景的 apply_fix
    print("[5/5] 模拟纠错场景...")
    body3 = {
        "model": model,
        "messages": [
            {"role": "system", "content": (
                "你是一个纠错助手。当你发现对话符号错误时，调用 apply_fix 来修正。"
                "错误 ID: e-0001，位置 offset=0，原文 [你好]，应改为「你好」。"
            )},
            {"role": "user", "content": (
                "请修正这个错误: 在 offset 0 处，[你好] 应该改为「你好」。"
                "调用 apply_fix 工具。"
            )},
        ],
        "tools": tools,
        "stream": False,
        "options": {"temperature": 0},
    }
    try:
        req3 = urllib.request.Request(
            f"{base}/v1/chat/completions",
            data=json.dumps(body3).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        t0 = time.time()
        with urllib.request.urlopen(req3, timeout=120) as r:
            resp3 = json.loads(r.read())
        elapsed = time.time() - t0
        msg3 = resp3["choices"][0]["message"]
        if "tool_calls" in msg3 and msg3["tool_calls"]:
            tc3 = msg3["tool_calls"][0]
            fn3 = tc3.get("function", {})
            print(f"  [OK] 模型调用了 apply_fix")
            print(f"       参数: {fn3.get('arguments', {})}")
            print(f"       耗时: {elapsed:.1f}s")
        else:
            print(f"  [!!] 模型没有调用 apply_fix")
            print(f"      回复: {msg3.get('content', '')[:80]}")
            return False
    except Exception as e:
        print(f"  [FAIL] 纠错模拟失败: {e}")
        return False

    # 全部通过
    print()
    print("=" * 50)
    print("  [OK] 全部 5 项测试通过！")
    print(f"  模型 {model} 可以正常调用 tools。")
    print("  可以开始完整纠错流程了。")
    print("=" * 50)
    return True


if __name__ == "__main__":
    success = test_tool_calling()
    sys.exit(0 if success else 1)
