## Requirements

### Requirement: 编辑策划层接收新闻数据作为输入
`editorial_planning_node` SHALL 将 `filtered_news`（新闻筛选结果）作为额外输入传入编辑策划任务，使 LLM 能够同时看到项目数据和新闻数据。

#### Scenario: 新闻数据正常传入
- **WHEN** `editorial_planning_node` 执行时 `filtered_news` 非空
- **THEN** 编辑策划任务的 inputs 中包含 `news_data` 字段，内容为格式化后的新闻列表

#### Scenario: 新闻数据为空时降级
- **WHEN** `filtered_news` 为空或不存在
- **THEN** `news_data` 传入空字符串，编辑策划任务正常执行，`resonance_signals` 输出为空列表

### Requirement: 编辑策划层输出共振信号列表
`EditorialPlan` 模型 SHALL 包含 `resonance_signals: list[ResonanceSignal]` 字段（默认空列表）。`ResonanceSignal` 包含 `keyword`、`repo_names`、`news_titles`、`strength`（"strong" | "moderate"）四个字段。

#### Scenario: 检测到强共振信号
- **WHEN** 同一关键词（或语义等价词）同时出现在 ≥1 个 GitHub 项目名/描述 和 ≥2 条新闻标题中
- **THEN** 对应 `ResonanceSignal.strength` 为 "strong"，`repo_names` 和 `news_titles` 列出所有涉及项目和新闻

#### Scenario: 检测到中等共振信号
- **WHEN** 同一关键词同时出现在 ≥1 个 GitHub 项目 和 1 条新闻中
- **THEN** 对应 `ResonanceSignal.strength` 为 "moderate"

#### Scenario: 无共振时输出空列表
- **WHEN** 新闻和项目之间无明显关键词重叠
- **THEN** `resonance_signals` 为空列表 `[]`

### Requirement: 写作层在趋势洞察中呈现强共振信号
写作任务 SHALL 在趋势洞察 Section 中，对 `strength` 为 "strong" 的共振信号优先生成一条洞察，格式为：`📡 **[关键词] 今日共振**：[项目名] 同时出现在 GitHub Trending 和新闻热点，[分析句]`。

#### Scenario: 有强共振信号时优先展示
- **WHEN** `editorial_plan.resonance_signals` 中存在 `strength == "strong"` 的信号
- **THEN** 趋势洞察第一条为该共振信号的分析，包含 📡 标识

#### Scenario: 无强共振信号时正常输出
- **WHEN** `resonance_signals` 为空或全为 "moderate"
- **THEN** 趋势洞察按原有逻辑生成，不强制插入共振信号条目
