## Context

当前写作层（`report_writing`）使用固定的七段式结构，无论信号强度如何都输出相同格式。评分层（`trend_scoring`）输出的 `ScoredRepo` 没有读者定向字段。质量审核层（`quality_review`）的结果仅用于内部校验，从未暴露给读者。

三个功能相互独立，改动点分散在评分层、写作层、节点编排层，需要统一设计数据流。

## Goals / Non-Goals

**Goals:**
- 根据 `signal_strength` 动态选择报告叙事模板（deep-dive / standard / review）
- 在趋势洞察中为每条洞察标注读者群体标签（🧑‍💻 / 💼 / 💰）
- 在报告末尾渲染质量置信度徽章（通过率 + 主要风险摘要）

**Non-Goals:**
- 不做多版本报告分发（不同读者收到不同报告）
- 不改变现有质量审核逻辑，仅复用其输出结果
- 不引入新的外部数据源

## Decisions

### 决策 1：模板选择在节点层还是写作层 Prompt 中？

**选择：节点层（`nodes.py`）注入 `report_template` 字段到 `WritingBrief`**

理由：写作层 Prompt 已经很长，在 Prompt 中嵌入三套模板会导致 token 浪费和 LLM 混淆。在节点层根据 `signal_strength` 选择模板字符串后注入，写作层只需按模板执行，职责清晰。

备选方案：在 `tasks.yaml` 中用条件分支描述三套模板 → 被否决，LLM 对条件分支的执行不稳定。

### 决策 2：audience_tag 在评分层生成还是写作层推断？

**选择：评分层（`trend_scoring`）生成 `audience_tag`**

理由：评分层已有项目的技术细节（README、描述、story_hook），是判断受众的最佳时机。写作层只负责渲染，不应承担分类判断。

可选值：`developer`（技术实现相关）/ `product`（产品功能相关）/ `investor`（融资/市场相关）/ `general`（通用）

### 决策 3：quality_badge 在哪里构建？

**选择：`nodes.py` 的 `quality_review_node` 执行后，将结果注入 `report_content` 末尾**

理由：质量审核结果是独立的结构化数据（`QualityReviewResult`），在节点层拼接比在写作层 Prompt 中描述更可靠，且不影响写作层的字数控制。

格式设计：
```
## 本期置信度
✅ 事实核对通过率：16/18  主要风险：无 error 级问题
```

## Risks / Trade-offs

- **[风险] 三套模板维护成本**：随着时间推移，deep-dive 和 review 模板可能与 standard 模板产生风格漂移 → 缓解：在 `tasks.yaml` 中统一定义禁用词和风格约束，三套模板共享
- **[风险] audience_tag LLM 分类不稳定**：LLM 可能将大多数项目标为 `general` → 缓解：在评分层 Prompt 中明确各标签的判断标准，并设置 `general` 为兜底而非首选
- **[Trade-off] quality_badge 暴露内部质量数据**：读者可能对低通过率产生不信任 → 接受：透明度本身是信任建立的方式，低通过率时 badge 应说明原因而非隐藏

## Migration Plan

1. 评分层先增加 `audience_tag` 字段（向后兼容，默认 `general`）
2. 节点层增加 `report_template` 注入逻辑（先只实现 standard 模板，其余两套后续补充）
3. 写作层 Prompt 增加读者标签渲染指令
4. 节点层在质量审核后追加 quality_badge
5. 无需数据迁移，无 breaking change

## Open Questions

- deep-dive 模板中的"反驳观点"段落是否需要从新闻数据中提取，还是由 LLM 自行生成？（建议：先允许 LLM 自行生成，后续再约束数据来源）
- quality_badge 的通过率阈值如何定义"高/中/低"置信度？（建议：≥15/18 为高，10-14 为中，<10 为低）
