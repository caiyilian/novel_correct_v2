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
3. **LLM 只修不找** — 规则检测器定位错误，LLM 只负责判断和修正
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

## 许可

MIT
