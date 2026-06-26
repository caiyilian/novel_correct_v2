# Issue #69 后续方案：规则收尾 + Ollama 受约束润色

> 针对 [#69](https://github.com/caiyilian/novel_correct_v2/issues/69) 的复现、分析与后续实施建议。

## 1. 复现结论

在最新 `master` 上执行：

```powershell
python tools\compare_dialogues.py output\corrected_第1卷.txt data\answer_第1卷.txt
python tools\verify_against_answer.py output\corrected_第1卷.txt data\answer_第1卷.txt
python main.py data\ori_story\第1卷.txt --report
```

得到的关键结果与 #69 基本一致：

| 指标 | 复现结果 |
| --- | --- |
| 修正文件对话数 | 1358 |
| 修正文件空对话 | 12 |
| 答案文件对话数 | 1349 |
| 答案文件空对话 | 0 |
| 非标准符号残留 | 0 |
| `「」` 配平 | 1359 / 1359，配平 |
| 忽略空白答案匹配率 | 97.59% |
| LLM 调用 | 0 |

补充观察：

- `tools/compare_dialogues.py` 使用栈式 `「」` 提取器，会把嵌套对话也作为独立段统计；这比简单正则更接近当前工具口径。
- 去掉空对话后，修正文件的非空对话段少于答案文件，说明问题不只是“多了 12 个空段”，还包含若干分段错位。
- 对对话内容做轻量标点/少量字词归一后，拼接后的对话文本相似度约 96.95%；尾部问题集中在风格、分段和少量语义字词，不是结构性崩坏。
- 本地 `main.py --report` 的 Correction Report 部分可能被最近一次运行的其它文件污染；实时硬指标仍来自目标 corrected 文件。这提示后续需要让报告按 novel 作用域读取，而不是只读全局 `output/correction_report.json`。

## 2. 问题拆解

### 2.1 空 `「」` artifact

空对话多出现在类似：

```text
……做到了。「」
……咱也一样。「」
……损失。「」
```

这类位置通常不是独立台词，而是规则在修复孤立 `]`、拆分长对话或补齐不配平符号时，为了满足局部候选/全局配平，生成了空闭合片段。

这类问题适合先用确定性规则处理，因为判断条件很硬：

- `「」` 内部为空或仅空白；
- 删除后不破坏全文 quote balance，或可同步删除相邻多余空白；
- 删除后 `DetectorPipeline` 不新增 `wrong_symbol` / `unpaired` / `consecutive`。

### 2.2 标点风格不一致

修正文件保留原文半角标点，答案文件更像人工整理后的全角出版风格：

- `?` -> `？`
- `!` -> `！`
- `.` / `·` -> `。` 或 `，`
- `~` -> `～`

这类改动大部分可规则化，但不能一刀切。例如 `.` 在英文网址、小数、缩写中不能改；`·` 有时是间隔号，有时是 OCR 误识别句号。

建议把它拆成两层：

1. 确定性标点规范化：只处理中文上下文中的 `?`、`!`、`~` 等低风险项。
2. 高风险项交给 Ollama 判断：`.`、`·`、`,`、冒号等需要上下文判断的符号。

### 2.3 对话分段粒度不同

答案文件有时会把连续短台词合并成一个 `「」`，修正文件则倾向保留原始分段。这个差异不能简单按“段数接近答案”作为目标，因为其它卷未必有答案文件。

后续应先把它作为评估维度，而不是默认修复动作：

- 识别 merge/split 候选；
- 只在高置信情况下生成候选；
- 由 Ollama 判断“是否确实是同一人连续话语、是否应该合并/拆分”；
- Verifier 限制改动范围和 quote balance。

### 2.4 少量语义字词差异

例如：

- `恩` vs `嗯`
- `它` vs `祂`
- `梢` vs `稍`
- `绍皮` vs `貂皮`

这些已超出符号纠错范畴，规则很容易误杀。它们适合进入“语义微修”队列，但必须要求模型从固定候选中选择，不允许自由改写整段。

## 3. 总体建议

我赞同 #69 中“是时候让 Ollama 出场”的判断，但不建议让 Ollama 做全文 polish。

推荐边界是：

> Python 继续负责检测、生成候选、应用补丁、验证硬指标；Ollama 只负责对少量高价值、规则无法确定的候选做 JSON 裁决。

这样能保留当前管线的最大优势：

- 全文结构、offset、quote balance 都由 Python 控制；
- LLM 不接触大范围重写，避免引入新错；
- token 成本可通过 Stage 20a-c 的 TokenTracker 量化；
- 每个 LLM 决策都能落到 checkpoint 和审计日志。

## 4. 推荐实施阶段

### Stage 24a：质量基线与报告作用域修复

目标：先把当前评估工具和报告口径稳定下来，避免继续基于污染的 `output/correction_report.json` 做判断。

改动建议：

- `main.py --report` 按 novel 名称读取对应 checkpoint / corrected 文件，不依赖上一次全局输出。
- `tools/compare_dialogues.py` 增加 `--json` 输出，记录：
  - total / empty / nonempty；
  - exact / punctuation-only / content-diff；
  - merge/split 候选位置；
  - 空 `「」` 的 line/offset/context。
- 新增或扩展测试，保证报告不会被其它临时文件运行污染。

验收：

- 对第 1 卷运行 `--report` 时 Correction Summary 与第 1 卷 checkpoint 对齐。
- `compare_dialogues --json` 可稳定输出空对话位置和差异统计。

### Stage 24b：确定性清理空 `「」`

目标：不调用 LLM，先清理最明确的 artifact。

候选规则：

- 删除内容为空或仅空白的 `「」`；
- 如果形态为 `。「」`、`。「 」`、`。「」\n`，只删除空对话本身和必要空白，不改前文内容；
- 删除后必须满足：
  - `「」` 仍配平；
  - 非标准符号仍为 0；
  - `DetectorPipeline` 不新增 `unpaired` / `consecutive`；
  - `verify_against_answer` 匹配率不下降。

验收：

- 第 1 卷空 `「」` 从 12 降为 0。
- quote balance 仍通过。
- 答案匹配率不下降。

### Stage 24c：确定性标点规范化候选

目标：建立“可审计的标点候选生成器”，不要直接大范围替换。

建议新增工具：

```text
tools/generate_style_candidates.py
```

候选类型：

- 中文字符之间的 `?` -> `？`
- 中文字符之间的 `!` -> `！`
- 连续 `~` -> 同数量或压缩后的 `～`
- 明显句末的 `.` -> `。`

每条候选记录：

- file offset；
- 原字符和候选字符；
- 前后上下文；
- 风险等级；
- 是否可规则自动应用。

验收：

- 能输出候选 JSONL。
- 低风险候选可自动应用并通过 Verifier。
- 高风险候选只进入待审队列，不自动改。

### Stage 25a：Ollama 微案例裁决器

目标：只让 Ollama 处理规则无法确定的边缘 case。

新增组件建议：

```text
src/agent/polish_judge.py
tools/run_polish_judge.py
```

输入不是全文，而是一条候选：

```json
{
  "case_id": "style-000123",
  "case_type": "punctuation | word_choice | dialogue_merge | empty_dialogue",
  "context_before": "...",
  "target": "...",
  "context_after": "...",
  "candidates": [
    {"id": "keep", "replacement": "..."},
    {"id": "c1", "replacement": "..."}
  ],
  "constraints": [
    "只能选择候选之一",
    "不得自由改写",
    "不得改变非目标文本",
    "不确定则选择 keep"
  ]
}
```

输出必须是 JSON：

```json
{
  "decision": "apply | keep | uncertain",
  "candidate_id": "c1",
  "reason": "简短中文理由"
}
```

模型建议：

- 默认使用当前项目已配置的本地 Ollama 模型。
- 优先高准确模型，例如 qwen3:32b；如果速度压力大，再评估较小模型。
- temperature 固定 0。
- 每条 case 独立调用，便于 checkpoint 和重试。

验收：

- mock LLM 测试覆盖 apply / keep / malformed JSON。
- 真实 Ollama 小样本运行能产生 `output/polish_decisions.jsonl`。
- TokenTracker 记录每条 polish 调用。

### Stage 25b：受约束应用与 Verifier

目标：LLM 只做裁决，实际改文仍由 Python 执行。

应用流程：

1. Python 读取候选。
2. Ollama 返回 candidate_id。
3. Python 应用精确 offset patch。
4. Verifier 校验：
   - quote balance 不变或更好；
   - 非标准符号不增加；
   - 不新增连续 `「」`；
   - 单次 patch diff 不超过候选范围；
   - 答案匹配率不下降（仅第 1 卷可用）。
5. 失败则回滚并记录。

验收：

- 所有 LLM 决策均可追溯到候选、上下文、token usage。
- 拒绝/回滚有明确原因。
- 第 1 卷硬指标保持全绿。

### Stage 25c：分段差异分析，不默认自动修

目标：先把 merge/split 问题变成可审计报告。

建议：

- 基于 `compare_dialogues.py` 增加 alignment 模式。
- 输出疑似：
  - corrected 多一段；
  - answer 多一段；
  - corrected 两段合并后接近 answer 一段；
  - answer 两段合并后接近 corrected 一段。
- 对第 1 卷可以用答案文件评估；其它卷只能作为人工/LLM 辅助审阅。

验收：

- 报告能列出 8-10 个主要分段差异位置。
- 不自动改正文，除非后续单独开阶段确认规则。

## 5. 风险控制

必须禁止的做法：

- 禁止让 Ollama 输出整章/全文替换文本。
- 禁止没有 offset 的自由改写。
- 禁止把答案文件作为生产输入直接喂给模型；答案只能用于第 1 卷评估和校准。
- 禁止 LLM 对低置信内容强行 apply；不确定时必须 keep / uncertain。

建议默认策略：

- 规则能确定的继续规则做。
- LLM 只处理少量候选。
- 每次改动都可回滚。
- 每个阶段都用第 1 卷答案文件量化，但不要把答案依赖写死进主流程。

## 6. 推荐优先级

我建议先做：

1. Stage 24a：报告作用域和差异 JSON 化。
2. Stage 24b：空 `「」` 确定性清理。
3. Stage 24c：标点候选生成。
4. Stage 25a/b：Ollama 微案例裁决与受约束应用。
5. Stage 25c：分段差异只做报告，不急着自动修。

这样可以把“规则明确能解决的问题”和“确实需要语义判断的问题”分开，避免为了最后 1% 的质量，把当前已经稳定的 99% 管线重新暴露给全文生成风险。
