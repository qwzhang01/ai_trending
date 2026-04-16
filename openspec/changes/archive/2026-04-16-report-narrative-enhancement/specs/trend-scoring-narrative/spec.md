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

## MODIFIED Requirements

### Requirement: story_hook 支持对比叙事
当 `prev_appearances` 显示项目曾出现过时，评分层 LLM 生成的 `story_hook` SHOULD 包含跨日期对比视角（如"上周还在被吐槽，这周已经 Trending 第一"）。当项目为首次上榜时，`story_hook` SHOULD 包含"首次上榜"或"新晋"等标识词汇。

#### Scenario: 项目再度上榜时生成对比叙事
- **WHEN** `github_data` 中某项目 `历史出现` 字段显示曾出现过（非首次上榜）
- **THEN** 该项目的 `story_hook` 包含时间对比视角，引用上次出现的时间或位置

#### Scenario: 项目首次上榜时标识新晋
- **WHEN** `github_data` 中某项目 `历史出现` 为 `首次上榜`
- **THEN** 该项目的 `story_hook` 包含"首次"、"新晋"或"刚刚"等标识词汇（如有合适素材）
