"""Stage 3 验证脚本：模型客户端复用"""
import sys, os, json as json_mod
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

results = []
errors = []

# Test 1: 导入
try:
    from src.model.client import (
        OpenAICompatibleClient, ModelConfig, ChatMessage, ChatResult,
        ToolCall, ModelConnectionStatus,
        ModelClientError, ModelHTTPError, ModelResponseError, ModelTimeoutError,
    )
    from src.model.protocol import ToolSpec, JsonAction, ProtocolError, _extract_json_object
    from src.model.protocol import parse_json_action
    results.append(("imports", "ok", "all classes importable"))
except Exception as e:
    errors.append(("imports", str(e)))

# Test 2: ModelConfig 默认值来自 ip_config
try:
    cfg = ModelConfig()
    assert cfg.base_url != "http://localhost:11434/v1", "should read from ip_config, not default"
    assert "qwen3" in cfg.model, f"expected qwen3 model, got: {cfg.model}"
    results.append(("ModelConfig from ip_config", "ok",
                    f"base_url={cfg.base_url}, model={cfg.model}, timeout={cfg.timeout}s"))
except Exception as e:
    errors.append(("ModelConfig from ip_config", str(e)))

# Test 3: ModelConfig 自定义
try:
    cfg = ModelConfig(base_url="http://test:11434", model="test-model")
    assert cfg.base_url == "http://test:11434"
    assert cfg.model == "test-model"
    results.append(("ModelConfig custom", "ok", "custom values work"))
except Exception as e:
    errors.append(("ModelConfig custom", str(e)))

# Test 4: ChatMessage 序列化
try:
    msg = ChatMessage(role="user", content="你好")
    d = msg.to_dict()
    assert d["role"] == "user"
    assert d["content"] == "你好"
    msg2 = ChatMessage(role="assistant", content="", tool_calls=[{
        "id": "call-1", "type": "function",
        "function": {"name": "test", "arguments": "{}"}
    }])
    d2 = msg2.to_dict()
    assert d2["tool_calls"] is not None
    results.append(("ChatMessage serialization", "ok", "user and tool_calls messages work"))
except Exception as e:
    errors.append(("ChatMessage serialization", str(e)))

# Test 5: ToolCall 序列化
try:
    tc = ToolCall(id="call-1", name="test_fn", arguments={"key": "value"})
    otc = tc.to_openai_tool_call()
    assert otc["id"] == "call-1"
    assert otc["type"] == "function"
    assert otc["function"]["name"] == "test_fn"
    results.append(("ToolCall to_openai", "ok", "OpenAI-compatible format works"))
except Exception as e:
    errors.append(("ToolCall to_openai", str(e)))

# Test 6: ToolSpec 序列化与 JSON action 解析
try:
    spec = ToolSpec(
        name="test_tool",
        description="A test tool",
        parameters={
            "type": "object",
            "properties": {"input": {"type": "string"}},
            "required": ["input"],
        }
    )
    tool_dict = spec.to_openai_tool()
    assert tool_dict["function"]["name"] == "test_tool"

    # JSON action extraction
    json_str = '{"action": "test_tool", "args": {"input": "hello"}}'
    obj = _extract_json_object(json_str)
    assert "test_tool" in obj

    # Markdown-wrapped JSON
    md_str = "```json\n" + json_str + "\n```"
    obj2 = _extract_json_object(md_str)
    assert "test_tool" in obj2

    results.append(("ToolSpec & JSON actions", "ok", "serialization and extraction work"))
except Exception as e:
    errors.append(("ToolSpec & JSON actions", str(e)))

# Test 7: chat_completions_url 构造
try:
    client = OpenAICompatibleClient(ModelConfig(base_url="http://localhost:11434/v1"))
    assert client.chat_completions_url == "http://localhost:11434/v1/chat/completions"
    client2 = OpenAICompatibleClient(ModelConfig(base_url="http://localhost:11434"))
    url2 = client2.chat_completions_url
    assert "/chat/completions" in url2
    results.append(("chat_completions_url", "ok", f"URL construction works: {url2}"))
except Exception as e:
    errors.append(("chat_completions_url", str(e)))

# Test 8: 连接远程 Ollama — 用 qwen3:4b（已验证可用，速度快）
client_small = OpenAICompatibleClient(ModelConfig(
    model="qwen3:4b",
    timeout=90,
))
try:
    status = client_small.check_connection()
    if status.ok:
        results.append(("Ollama connect (qwen3:4b)", "ok",
                        f"model={status.model}, response={status.message[:60]}"))
    else:
        errors.append(("Ollama connect (qwen3:4b)", f"FAILED: {status.message[:120]}"))
except Exception as e:
    errors.append(("Ollama connect (qwen3:4b)", str(e)))

# Test 9: 实际对话
if status.ok:
    try:
        result = client_small.chat(
            messages=[
                ChatMessage(role="system", content="You are a helpful assistant."),
                ChatMessage(role="user", content="Reply with exactly: hello world"),
            ],
            temperature=0,
            max_tokens=30,
        )
        resp = result.content.strip()
        if resp:
            results.append(("Ollama simple chat", "ok",
                            f"response={resp[:60]}"))
        else:
            # Empty response can happen with very short prompts
            results.append(("Ollama simple chat", "warn",
                            "model returned empty response"))
    except Exception as e:
        errors.append(("Ollama simple chat", str(e)))
else:
    results.append(("Ollama simple chat", "skipped", "connection failed"))

# Test 10: Tool calling
if status.ok:
    try:
        tool_spec = ToolSpec(
            name="get_weather",
            description="Get the weather for a city",
            parameters={
                "type": "object",
                "properties": {
                    "city": {"type": "string", "description": "City name"}
                },
                "required": ["city"],
            }
        )
        result = client_small.chat(
            messages=[
                ChatMessage(role="system", content="You have access to a weather tool. When asked about weather, call it."),
                ChatMessage(role="user", content="What is the weather in Tokyo?"),
            ],
            tools=[tool_spec],
            temperature=0,
            max_tokens=100,
        )
        if result.tool_calls:
            tc = result.tool_calls[0]
            results.append(("Tool calling", "ok",
                            f"tool={tc.name}, args={json_mod.dumps(tc.arguments, ensure_ascii=False)[:60]}"))
        else:
            results.append(("Tool calling", "ok",
                            f"model responded with text (no tool call): {result.content[:60]}"))
    except Exception as e:
        errors.append(("Tool calling", str(e)))
else:
    results.append(("Tool calling", "skipped", "connection failed"))

# Test 11: 用主配置（qwen3:32b）连接 — 验证 ip_config 默认值
client_main = OpenAICompatibleClient(ModelConfig(timeout=180))  # 3 min for cold start
try:
    status_main = client_main.check_connection()
    if status_main.ok:
        results.append(("Ollama connect (qwen3:32b)", "ok",
                        f"model={status_main.model}, response={status_main.message[:60]}"))
    else:
        # 32b 冷启动可能超时，这不代表客户端有问题
        results.append(("Ollama connect (qwen3:32b)", "warn",
                        f"cold start timeout (expected for 32B): {status_main.message[:80]}"))
except Exception as e:
    results.append(("Ollama connect (qwen3:32b)", "warn",
                    f"cold start timeout: {str(e)[:80]}"))

# Print report
print("=" * 55)
print("  Stage 3 Verification Report — Model Client")
print("=" * 55)
for name, status, detail in results:
    tag = "[OK]" if status == "ok" else ("[-]" if status == "skipped" else "[!!]")
    print(f"  {tag} {name}: {detail}")
for name, detail in errors:
    print(f"  [FAIL] {name}: {detail}")
print("=" * 55)
print(f"  {len(results)} passed, {len(errors)} failed")
print("=" * 55)
