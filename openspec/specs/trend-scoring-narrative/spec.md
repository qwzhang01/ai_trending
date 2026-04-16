## MODIFIED Requirements

### Requirement: story_hook 必须引用真实技术内容
当 `readme_summary` 非空时，评分层 LLM 生成的 `story_hook` MUST 从 README 摘要中引用至少一个具体的技术名词、架构名称、数字或对比对象。禁止使用纯推断式模板句（如"和X不同，Y支持..."这类无数据支撑的描述）。当 `readme_summary` 为空时，允许基于描述推断，但 `story_hook` 中 MUST 包含项目描述中的至少一个具体词汇。

#### Scenario: 有 README 时引用真实内容
- **WHEN** `github_data` 中某项目 `README摘要` 非空且包含具体技术描述
- **THEN** 该项目的 `story_hook` 包含 README 中出现的至少一个具体技术名词或数字，不使用纯推断式句式

#### Scenario: 无 README 时允许推断但需有具体词汇
- **WHEN** `github_data` 中某项目 `README摘要` 为 `（暂无）`
- **THEN** 该项目的 `story_hook` 基于项目描述生成，但必须包含描述中的至少一个具体词汇，不得使用完全泛化的句式（如"这个项目解决了AI领域的痛点"）

### Requirement: technical_detail 必须来自真实数据
`technical_detail` 字段 MUST 包含从 README 或项目描述中提取的具体技术细节（架构名称、算法、数字、对比项目名），字数不超过 25 字。禁止使用"支持多种功能"、"采用先进技术"等无实质内容的描述。

#### Scenario: 从 README 提取技术细节
- **WHEN** README 摘要中包含具体的技术实现描述（如架构名、算法名、性能数字）
- **THEN** `technical_detail` 引用该具体内容，不超过 25 字

#### Scenario: 无具体技术细节时的降级处理
- **WHEN** README 和描述均无具体技术细节可引用
- **THEN** `technical_detail` 输出项目的核心功能定位（不超过 25 字），并避免使用"先进"、"强大"等形容词

### Requirement: 评分层输出包含 readme_summary 字段
`ScoredRepo` 输出模型 SHALL 包含 `readme_summary: str` 字段（默认空字符串），评分层 LLM SHALL 从输入的 `github_data` 中读取对应项目的 README 摘要并原样填入，供写作层直接使用，不得改写或截断。

#### Scenario: 评分层原样传递 README 摘要
- **WHEN** `github_data` 中某项目包含非空 `README摘要`
- **THEN** 评分层输出的对应 `scored_repos` 条目中 `readme_summary` 与输入内容一致（允许截断到 300 字以内）

#### Scenario: 无 README 时传递空字符串
- **WHEN** `github_data` 中某项目 `README摘要` 为 `（暂无）`
- **THEN** 评分层输出的对应 `scored_repos` 条目中 `readme_summary` 为空字符串 `""`

## ADDED Requirements

### Requirement: formatter 输出项目历史出现记录
`format_text_output` 函数 SHALL 在每个仓库的输出块中包含 `prev_appearances` 字段，记录该项目在近 7 天 TOPIC_TRACKER 中的出现历史。当项目首次出现时输出 `历史出现: 首次上榜`；当项目曾出现过时输出 `历史出现: {日期}({位置}), ...` 格式。

#### Scenario: 项目首次出现在 Trending
- **WHEN** 当前项目名在 `TOPIC_TRACKER.md` 近 7 天记录中未出现
- **THEN** `format_text_output` 输出中包含 `历史出现: 首次上榜` 行

#### Scenario: 项目曾作为头条出现
- **WHEN** 当前项目名在 `TOPIC_TRACKER.md` 近 7 天记录中作为头条出现过
- **THEN** `format_text_output` 输出中包含 `历史出现: {日期}(头条)` 行

#### Scenario: 项目曾作为热点出现
- **WHEN** 当前项目名在 `TOPIC_TRACKER.md` 近 7 天关键词中出现过
- **THEN** `format_text_output` 输出中包含 `历史出现: {日期}(热点)` 行

#### Scenario: TOPIC_TRACKER 读取失败
- **WHEN** `TOPIC_TRACKER.md` 文件不存在或解析失败
- **THEN** `prev_appearances` 降级为 `历史出现: 数据不可用`，不抛出异常，不影响其他字段

### Requirement: story_hook 支持对比叙事
当 `prev_appearances` 显示项目曾出现过时，评分层 LLM 生成的 `story_hook` SHOULD 包含跨日期对比视角（如"上周还在被吐槽，这周已经 Trending 第一"）。当项目为首次上榜时，`story_hook` SHOULD 包含"首次上榜"或"新晋"等标识词汇。

#### Scenario: 项目再度上榜时生成对比叙事
- **WHEN** `github_data` 中某项目 `历史出现` 字段显示曾出现过（非首次上榜）
- **THEN** 该项目的 `story_hook` 包含时间对比视角，引用上次出现的时间或位置

#### Scenario: 项目首次上榜时标识新晋
- **WHEN** `github_data` 中某项目 `历史出现` 为 `首次上榜`
- **THEN** 该项目的 `story_hook` 包含"首次"、"新晋"或"刚刚"等标识词汇（如有合适素材）
