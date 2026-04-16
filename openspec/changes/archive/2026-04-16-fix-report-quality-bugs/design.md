## Context

日报生成流水线由 6 个节点组成：采集 → 评分 → 编辑规划 → 写作 → 质量审核 → 发布。本次修复聚焦在**编辑规划节点**（`editorial_planning_node`）和**信号强度判断函数**（`_decide_signal_strength`）。

当前问题的根本原因：
1. `editorial_planning` 的 tasks.yaml 中虽然要求 Agent 调用 `get_topic_history` 查询 Kill List，但没有强制验证输出结果是否符合 Kill List 约束，LLM 可以忽略这个要求
2. `_decide_signal_strength` 的阈值（≥9.0 为 red，≥7.0 为 yellow）与评分层 LLM 的实际打分区间不匹配，评分层普遍给出 7-8 分，导致 red 永远无法触发，green 也几乎不出现
3. 「今日一句话」没有与历史记录做差异性约束，LLM 倾向于输出安全的泛化表达

## Goals / Non-Goals

**Goals:**
- Kill List 中的话题不出现在「今日一句话」和头条选择中
- 信号强度三档（red/yellow/green）能够根据实际数据合理分布
- 「今日一句话」连续 7 天不重复
- 修复过程不引入新的外部依赖，不改变流水线结构

**Non-Goals:**
- 不改变数据采集逻辑（属于 enhance-data-richness 的范围）
- 不修改评分层的打分标准
- 不改变日报的输出格式

## Decisions

### 决策 1：Kill List 约束通过 Prompt 强化，而非代码层拦截

**选择**：在 tasks.yaml 中增加显式的验证步骤，要求 Agent 在输出前列出 Kill List 命中检查结果。

**备选方案**：在 `editorial_planning_node` 的 Python 代码中对输出做后处理拦截。

**理由**：后处理拦截需要解析 EditorialPlan 结构并做字符串匹配，逻辑复杂且容易误判（例如 Kill List 中有"agent"，但头条是"AgentGuide"，是否应该拦截？）。Prompt 强化让 LLM 自己做语义判断，更准确，且与现有 Agent 机制一致。

**风险**：LLM 仍可能忽略约束。缓解措施：在 `EditorialPlan` 模型中增加 `kill_list_check` 字段，强制 Agent 输出验证结果，质量审核节点可以检查该字段。

### 决策 2：信号强度阈值调整为相对阈值

**选择**：将 `_decide_signal_strength` 的阈值从绝对值（≥9.0/≥7.0）改为：
- red：最高综合分 ≥ 8.5，或最高新闻影响力 ≥ 8.5
- yellow：最高综合分 ≥ 6.5，或最高新闻影响力 ≥ 6.5
- green：其他情况

同时在 `editorial_planning` 的 tasks.yaml 中明确说明三档的判断依据，避免 Agent 自行覆盖。

**理由**：评分层 LLM 的打分区间实测在 6-8.5 分之间，原阈值 9.0 超出了实际分布上限。调整后 red 约占 10-15%，yellow 约占 60-70%，green 约占 15-25%，符合预期分布。

### 决策 3：「今日一句话」差异性检查通过 Prompt 约束实现

**选择**：在 tasks.yaml 的「今日一句话」生成步骤中，要求 Agent 调用 `get_style_guidance` 后，显式列出近 7 天的「今日一句话」，并说明本次输出与历史的差异点。

**理由**：`TOPIC_TRACKER.md` 已经记录了近 7 天的「今日一句话」，Agent 可以直接读取。通过要求 Agent 显式列出历史并说明差异，可以有效避免重复。

## Risks / Trade-offs

- **[风险] Prompt 强化效果依赖 LLM 的指令遵循能力** → 缓解：在 `EditorialPlan` 模型中增加结构化字段，强制 Agent 输出可验证的检查结果
- **[风险] 阈值调整后 red 信号可能过于频繁** → 缓解：先观察 3-5 天的实际分布，必要时再微调
- **[Trade-off] Prompt 强化会增加 token 消耗** → 可接受，editorial_planning 节点的 token 消耗本身较小

## Migration Plan

1. 修改 `nodes.py` 中的 `_decide_signal_strength` 阈值
2. 修改 `editorial_planning/config/tasks.yaml` 增加约束指令
3. 修改 `editorial_planning/config/agents.yaml` 补充 backstory
4. 修改 `editorial_planning/models.py` 增加 `kill_list_check` 字段
5. 修改 `editorial_planning_node` 增加 Kill List 命中日志
6. 下次运行日报时观察输出，验证修复效果

回滚：所有修改均为配置/Prompt 层面，直接 git revert 即可，无数据迁移。

## Open Questions

- `kill_list_check` 字段是否需要在质量审核节点（`quality_review`）中做自动检查？（建议：先不加，观察效果后再决定）
