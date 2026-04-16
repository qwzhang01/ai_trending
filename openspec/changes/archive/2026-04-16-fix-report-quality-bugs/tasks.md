## 1. 修复信号强度阈值

- [x] 1.1 修改 `src/ai_trending/nodes.py` 中 `_decide_signal_strength` 函数：将 red 阈值从 9.0 改为 8.5，yellow 阈值从 7.0 改为 6.5

## 2. 强化 Kill List 执行约束（Prompt 层）

- [x] 2.1 修改 `src/ai_trending/crew/editorial_planning/config/tasks.yaml`：在决策任务描述中增加显式的 Kill List 验证步骤，要求 Agent 在输出前列出命中检查结果
- [x] 2.2 修改 `src/ai_trending/crew/editorial_planning/config/tasks.yaml`：在「今日一句话」生成步骤中增加约束，要求 Agent 列出近 7 天历史并说明本次输出的差异点
- [x] 2.3 修改 `src/ai_trending/crew/editorial_planning/config/agents.yaml`：在 backstory 中补充对 Kill List 执行的明确说明

## 3. 扩展 EditorialPlan 模型

- [x] 3.1 修改 `src/ai_trending/crew/editorial_planning/models.py`：在 `EditorialPlan` 模型中增加 `kill_list_check` 字段（`str`，默认空字符串），记录 Kill List 验证结果
- [x] 3.2 确认 `EditorialPlan.format_for_prompt()` 方法能正确输出 `kill_list_check` 字段内容（或确认该字段仅用于日志，不需要传入写作层）

## 4. 增加 Kill List 命中日志

- [x] 4.1 修改 `src/ai_trending/nodes.py` 中 `editorial_planning_node`：在 `plan` 对象返回后，读取 `kill_list_check` 字段并用 `log.info` 记录

## 5. 验证

- [x] 5.1 运行 `uv run ruff format src/ai_trending/nodes.py src/ai_trending/crew/editorial_planning/models.py` 格式化修改的 Python 文件
- [x] 5.2 检查 `output/TOPIC_TRACKER.md` 中下次运行后「今日一句话」是否与历史不重复
- [x] 5.3 检查下次运行后信号强度是否出现 green 或 red（不再永远是 yellow）
