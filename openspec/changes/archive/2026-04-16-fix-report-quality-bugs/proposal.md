## Why

日报连续 7 天「今日一句话」完全雷同（均为"AI技术持续演进"），信号强度永远停留在 🟡 常规更新日，说明两个关键机制已失效：Kill List 没有真正约束编辑 Agent 的输出，信号强度阈值设计导致 red/green 信号永远无法触发。这两个问题是纯实现层面的 bug，与数据源质量无关，修复成本低、收益高。

## What Changes

- **修复 Kill List 生效问题**：在 `editorial_planning` 的 tasks.yaml 中强化 Kill List 执行约束，要求 Agent 在输出前显式验证「今日一句话」和头条是否与 Kill List 冲突，并在 `EditorialPlan` 模型中增加 `kill_list_check` 字段记录验证结果
- **修复信号强度阈值**：调整 `_decide_signal_strength` 函数的阈值，使 yellow/red/green 三档能够根据实际数据合理分布；同时在 `editorial_planning` 的 Agent 中增加信号强度的判断说明，避免 LLM 自行覆盖
- **修复「今日一句话」重复问题**：在 `editorial_planning` 的 tasks.yaml 中增加约束：调用 `get_style_guidance` 后，必须与近 7 天的「今日一句话」做差异性检查，相似度过高时强制重写
- **增加 Kill List 执行日志**：在 `editorial_planning_node` 中记录 Kill List 命中情况，方便后续排查

## Capabilities

### New Capabilities

- `kill-list-enforcement`：编辑决策中 Kill List 的强制执行机制，包括验证逻辑和日志记录

### Modified Capabilities

（无需求层面变更，均为实现层面修复）

## Impact

- `src/ai_trending/crew/editorial_planning/config/tasks.yaml`：强化 Kill List 和「今日一句话」的约束指令
- `src/ai_trending/crew/editorial_planning/config/agents.yaml`：补充 Agent backstory 中对 Kill List 的执行说明
- `src/ai_trending/crew/editorial_planning/models.py`：`EditorialPlan` 模型增加 `kill_list_check` 字段
- `src/ai_trending/nodes.py`：`_decide_signal_strength` 阈值调整 + `editorial_planning_node` 增加日志
- 无 API 变更，无依赖变更，不影响其他 Crew
