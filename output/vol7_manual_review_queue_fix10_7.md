# 第7卷 Fix 10-7 人工审核队列

- 已安全拆分 1 处连包对话：`您的预算是？` / `两枚崔尼银币。`。
- 剩余 4 处涉及答案侧额外文本或 OCR 文本差异，不能自动插入或替换。

## vol7_gap_manual_001

- 答案对齐：`？ + 啊，艾里亚丝！`
- 当前对齐：`艾里亚丝！`
- OCR anchor offset：844
- 原因：Answer has extra punctuation/text not present in OCR corrected dialogue; auto-fix would add answer-side text.

```text
蒙上一层污垢，但离远一点看，那模样还挺像只小羊的。 
 
    她的名字是艾里亚丝。 
 
    艾里亚丝说她不知道自己的年纪多大，但身高比卡拉斯高了一些。 
 
    因为觉得不服气，所以卡拉斯认定艾里亚丝大他两岁。 
 
    「艾里亚丝！」 
 
    听到卡拉斯呼唤自己的名字，艾里亚丝总算抬起了头。 
 
    「我们不是约好，在中午前要爬过四座山丘吗？」 
 
    虽然卡拉斯到现在还搞不太懂艾里亚丝的思绪，但掌握到了几个事实。 
 
    其中一个事实是，就算拜
```

## vol7_gap_manual_002

- 答案对齐：`啊，好的。 + 你在这里休息。`
- 当前对齐：`在这里休息！`
- OCR anchor offset：19843
- 原因：Answer split uses substantially different text; no existing OCR fragment can be wrapped safely.

```text
己为什么感到无趣。 
 
    「那么，咱的行李在那边，帮咱搬一下呗。」 
 
    「啊，好的。」 
 
    看见艾里亚丝准备站起身子，卡拉斯阻止她说： 
 
    「你在这里休息。」 
 
    「可是……」 
 
    「在这里休息！」 
 
    听到卡拉斯语气有些强硬地反覆说道，艾里亚丝一脸惊讶，胆怯地点了点头。 
 
    赫萝一副享受著卡拉斯与艾里亚丝的互动似地，愉快地说了句：「往这边。」然后迈步走了出去。 
 
    「呵呵，其实没必要那么凶呗。」 
 

```

## vol7_gap_manual_003

- 答案对齐：`咦？ + 抱歉。`
- 当前对齐：`抱、抱歉什么？`
- OCR anchor offset：64790
- 原因：Answer split uses different wording; auto-fix would replace or add OCR text.

```text

    「抱歉。」 
 
    「咦？」 
 
    卡拉斯想著是不是自己听错时，赫萝重复一遍说： 
 
    「抱歉。」 
 
    卡拉斯一脸呆然地杵在原地不动。他一边抱著痛苦地靠在他身上的艾里亚丝，一边反问： 
 
    「抱、抱歉什么？」 
 
    「咱可能没办法救汝等。」 
 
    「怎──」 
 
    卡拉斯说到一半停了下来。 
 
    他并不是因为看见艾里亚丝瘫软在地，也不是因为看见赫萝一脸悲痛地咬著嘴唇，才停止说下去。 
 
    而是他感觉到一股
```

## vol7_gap_manual_004

- 答案对齐：`抱、抱歉什么？ + 咱可能没办法救汝等。`
- 当前对齐：`咱可能没办法救汝等。`
- OCR anchor offset：64807
- 原因：This is downstream alignment after the previous source/text mismatch, not a safe standalone wrapper fix.

```text
 「咦？」 
 
    卡拉斯想著是不是自己听错时，赫萝重复一遍说： 
 
    「抱歉。」 
 
    卡拉斯一脸呆然地杵在原地不动。他一边抱著痛苦地靠在他身上的艾里亚丝，一边反问： 
 
    「抱、抱歉什么？」 
 
    「咱可能没办法救汝等。」 
 
    「怎──」 
 
    卡拉斯说到一半停了下来。 
 
    他并不是因为看见艾里亚丝瘫软在地，也不是因为看见赫萝一脸悲痛地咬著嘴唇，才停止说下去。 
 
    而是他感觉到一股不知名的强烈寒气，从地面猛烈地爬上双脚，
```
