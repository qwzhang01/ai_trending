## ADDED Requirements

### Requirement: Kill List 强制执行
编辑 Agent 在生成编辑决策时，SHALL 在输出前显式验证头条选择和「今日一句话」是否与 Kill List 冲突，并将验证结果记录在 `kill_list_check` 字段中。

#### Scenario: 头条候选在 Kill List 中
- **WHEN** 编辑 Agent 选定的头条项目名称出现在 Kill List 中
- **THEN** Agent SHALL 重新选择头条，并在 `kill_list_check` 中说明原因

#### Scenario: 今日一句话与 Kill List 话题高度重叠
- **WHEN** 「今日一句话」包含 Kill List 中标记为"近3天出现4次"的关键词
- **THEN** Agent SHALL 重写「今日一句话」，使其不包含该关键词

#### Scenario: Kill List 为空
- **WHEN** `get_topic_history` 返回的 Kill List 为空
- **THEN** Agent SHALL 正常执行，不做额外约束

#### Scenario: kill_list_check 字段记录
- **WHEN** 编辑决策生成完成
- **THEN** `EditorialPlan.kill_list_check` 字段 SHALL 包含：已检查的 Kill List 条目数、命中条目（如有）、最终决策说明

### Requirement: 今日一句话差异性约束
编辑 Agent 在生成「今日一句话」时，SHALL 与近 7 天的历史「今日一句话」做差异性检查，确保语义不重复。写作层 Prompt MUST 在动态数据段中列出近 7 天的历史 hook，并明确要求生成的 hook 与历史任意一条的语义相似度 < 60%。禁止使用"AI技术持续演进"、"AI持续演进"等泛化表述；MUST 包含当天数据中的至少一个具体词汇（项目名、技术名词、数字）。

#### Scenario: 今日一句话与近 7 天历史完全相同
- **WHEN** 生成的「今日一句话」与 `TOPIC_TRACKER.md` 中近 7 天任意一条完全相同
- **THEN** 写作层 Agent SHALL 重新生成，直到与历史不重复

#### Scenario: 今日一句话语义高度相似（泛化变体）
- **WHEN** 生成的「今日一句话」是历史 hook 的泛化变体（如"AI技术演进"、"AI持续发展"）
- **THEN** 写作层 Agent SHALL 基于今日具体数据（头条项目名、关键技术词、星数增长）生成有观点的判断句

#### Scenario: 今日一句话包含当天特有词汇
- **WHEN** 写作层 Prompt 中包含今日头条项目名和关键技术词
- **THEN** 生成的「今日一句话」MUST 包含其中至少一个具体词汇，不得使用完全泛化的句式

#### Scenario: Kill List 为空
- **WHEN** `get_topic_history` 返回的 Kill List 为空
- **THEN** Agent SHALL 正常执行，不做额外约束

### Requirement: 信号强度阈值合理分布
`_decide_signal_strength` 函数 SHALL 使用调整后的阈值，使三档信号在实际数据中能够合理分布。

#### Scenario: 高分项目触发 red 信号
- **WHEN** 最高综合评分 ≥ 8.5 或最高新闻影响力 ≥ 8.5
- **THEN** 信号强度 SHALL 为 "red"（🔴 重大变化日）

#### Scenario: 中等分数触发 yellow 信号
- **WHEN** 最高综合评分 ≥ 6.5 或最高新闻影响力 ≥ 6.5，且不满足 red 条件
- **THEN** 信号强度 SHALL 为 "yellow"（🟡 常规更新日）

#### Scenario: 低分触发 green 信号
- **WHEN** 最高综合评分 < 6.5 且最高新闻影响力 < 6.5
- **THEN** 信号强度 SHALL 为 "green"（🟢 平静日）
