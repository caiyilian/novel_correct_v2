"""
Ollama 微案例裁决器。

对规则无法确定的微案例做 JSON 裁决。模型不从零生成修改，
只从 Python 给出的候选列表中选择 apply/keep/uncertain。

用法（通过 tools/run_polish_judge.py 调用）：
    python tools/run_polish_judge.py --candidates output/style_candidates.jsonl
"""

import json
import time
from typing import Any, Dict, List, Optional

from src.model.client import (
    ChatMessage,
    ModelConfig,
    OpenAICompatibleClient,
    TokenUsage,
)


# 系统提示词：约束模型只能从候选中选择
SYSTEM_PROMPT = """你是一个文本精审助手，只对修改候选做 JSON 裁决。

规则：
1. 从 candidates 列表中选择一项。
2. 不得自由改写、不得修改非目标文本。
3. 不需要修改时选择 keep，不确定时选择 uncertain。
4. 输出格式必须只有一行 JSON，不要有任何其他文字。

输出格式（仅一行 JSON，不要任何其他内容）：
{"decision": "apply|keep|uncertain", "candidate_id": "...", "reason": "简短中文理由（10字以内）"}

示例：
{"decision": "apply", "candidate_id": "c1", "reason": "中文语境改用全角"}
{"decision": "keep", "candidate_id": "keep", "reason": "无需修改"}
{"decision": "uncertain", "candidate_id": "uncertain", "reason": "无法判断"}"""


def build_case_prompt(case: dict) -> str:
    """从 case dict 构建用户提示。"""
    lines = [f"## Case: {case.get('case_id', 'unknown')}"]
    lines.append(f"Type: {case.get('case_type', 'unknown')}")
    lines.append("")

    # 上下文
    ctx_before = case.get("context_before", "")
    target = case.get("target", "")
    ctx_after = case.get("context_after", "")
    lines.append("### 上下文")
    lines.append(f"[前文] {ctx_before}")
    lines.append(f"[目标] {target}")
    lines.append(f"[后文] {ctx_after}")
    lines.append("")

    # 候选
    lines.append("### 候选列表")
    candidates = case.get("candidates", [{"id": "keep", "replacement": "keep (no change)"}])
    for c in candidates:
        lines.append(f"- id={c['id']}: {c['replacement']}")
    lines.append("")

    # 约束
    constraints = case.get("constraints", [])
    if constraints:
        lines.append("### 约束")
        for con in constraints:
            lines.append(f"- {con}")

    return "\n".join(lines)


class PolishJudge:
    """
    微案例裁决器。

    Args:
        model: ModelConfig 或 None（使用默认配置）
        mock: 如果为 True，不调 LLM，固定返回 apply 给第一个候选
    """

    def __init__(self, model: Optional[ModelConfig] = None, mock: bool = False):
        self.mock = mock
        if not mock:
            config = model or ModelConfig()
            self.client = OpenAICompatibleClient(config)
            self.model_name = config.model
        else:
            self.client = None
            self.model_name = "mock"

        self.records: List[Dict[str, Any]] = []  # 每次 judge 的记录

    def judge(self, case: dict) -> dict:
        """
        裁决一条 case。

        Args:
            case: dict 格式，必须包含 case_id, case_type, context_before,
                  target, context_after, candidates

        Returns:
            dict: {decision, candidate_id, reason, token_usage, case_id}
        """
        case_id = case.get("case_id", "unknown")

        if self.mock:
            # Mock 模式：固定返回 keep
            time.sleep(0.01)  # 模拟延迟
            result = {
                "decision": "keep",
                "candidate_id": "keep",
                "reason": "mock: 默认保留原样",
                "token_usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
                "case_id": case_id,
            }
        else:
            prompt = build_case_prompt(case)
            messages = [
                ChatMessage(role="system", content=SYSTEM_PROMPT),
                ChatMessage(role="user", content=prompt),
            ]

            chat_result = self.client.chat(messages=messages, temperature=0.0, max_tokens=1000)
            response_text = chat_result.content.strip()

            # 尝试解析 JSON
            try:
                parsed = json.loads(response_text)
                decision = parsed.get("decision", "uncertain")
                candidate_id = parsed.get("candidate_id", "uncertain")
                reason = parsed.get("reason", "")
            except (json.JSONDecodeError, ValueError):
                decision = "uncertain"
                candidate_id = "uncertain"
                reason = f"LLM 返回非 JSON: {response_text[:100]}"

            # Validate: decision 必须是合法值
            VALID_DECISIONS = {"apply", "keep", "uncertain"}
            if decision not in VALID_DECISIONS:
                violations = []
                violations.append(f"非法decision: {decision}")
                decision = "uncertain"
                candidate_id = "uncertain"
                reason = "; ".join(violations)

            # Validate: candidate_id 必须在 case 的候选列表中
            if candidate_id not in {c["id"] for c in case.get("candidates", [])}:
                if decision != "uncertain":
                    decision = "uncertain"
                    candidate_id = "uncertain"
                    reason = f"{reason}; 非法candidate_id: {candidate_id}"

            usage = chat_result.usage
            result = {
                "decision": decision,
                "candidate_id": candidate_id,
                "reason": reason,
                "token_usage": {
                    "prompt_tokens": usage.prompt_tokens,
                    "completion_tokens": usage.completion_tokens,
                    "total_tokens": usage.total_tokens,
                },
                "case_id": case_id,
            }

        self.records.append(result)
        return result

    def total_tokens(self) -> int:
        """累计 token 消耗。"""
        return sum(
            r.get("token_usage", {}).get("total_tokens", 0)
            for r in self.records
            if not self.mock
        )