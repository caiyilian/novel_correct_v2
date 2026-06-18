# novel_correct_v2

> OCR 纠错 v2 版 — 将小说中所有对话包裹符号统一为「」，为后续说话人标注和 TTS 有声书合成打好基础。

## 定位

整个小说转语音大项目中的第一道关卡：

```
novel_correct_v2 (纠错) → opencode-novel-loop (说话人标注) → novel-voice-cast (TTS 有声书)
```

## 设计原则

1. **质量 > 一切** — 不追求速度，只追求准确率
2. **统一「」** — 所有对话包裹符号（`""` `[]` `【】` 等）统一为「」
3. **规则先行** — 规则检测器定位错误，候选生成器先给出可验证修复
4. **一次一个** — 每轮只处理一个错误，逐个修正，逐个验证
5. **宁跳过，不错改** — 不确定就跳过，绝不强行修改

## 快速开始

```bash
# 安装依赖
pip install -r requirements.txt

# 配置 Ollama 服务器
# 编辑 ip_config 中的服务器地址和模型名

# 检测小说中的错误
python main.py data/ori_story/第1卷.txt --detect

# 检测 + 修正
python main.py data/ori_story/第1卷.txt

# 使用旧的 tool-calling Agent 实验模式
python main.py data/ori_story/第1卷.txt --agent-tool-mode

# 从 checkpoint 恢复
python main.py data/ori_story/第1卷.txt --resume

# 批量处理
python main.py --batch data/ori_story/
```

## 详细方案

见 [`开发方案.md`](开发方案.md)。

## 依赖

- Python 3.10+
- Ollama 服务（可本地或远程部署）
- qwen3:30b 或任意支持 tool calling 的模型

## 纠错模式

默认纠错路径是“规则生成候选修复，规则预检优先决策”。程序负责生成
offset 和 replacement，并自动应用能降低检测错误数的候选。
无法通过规则预检确认的候选默认跳过，避免小模型长时间推理或挂起。

如果需要让强模型继续判断规则预检无法确定的候选，可加
`--llm-decision-fallback`。

旧的 `apply_fix` tool-calling Agent 仍保留为实验模式，可用
`--agent-tool-mode` 启用。

## 许可

MIT
