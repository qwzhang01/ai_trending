## ADDED Requirements

### Requirement: stars_growth_7d 在 formatter 输出中可见
`format_text_output` 函数 SHALL 在每个仓库的输出块中包含 `stars_growth_7d` 字段。当值非 None 时输出 `7日增长: +{N}` 格式；当值为 None 时输出 `7日增长: （暂无历史数据）`。

#### Scenario: 有增长数据时正常输出
- **WHEN** `RepoCandidate.stars_growth_7d` 为非 None 整数
- **THEN** `format_text_output` 输出中包含 `7日增长: +{N}` 行（N 为实际增长量）

#### Scenario: 无历史数据时输出占位符
- **WHEN** `RepoCandidate.stars_growth_7d` 为 None
- **THEN** `format_text_output` 输出中包含 `7日增长: （暂无历史数据）` 行

### Requirement: stars_growth_7d 流转到 WritingBrief
`_build_writing_brief` 函数 SHALL 从 `scored_repos` JSON 中读取 `stars_growth_7d` 字段，并填入 `RepoBrief.stars_growth_7d`，确保写作层的 `format_for_prompt()` 输出中包含增长数据。

#### Scenario: 评分层中转增长数据
- **WHEN** `scored_repos` JSON 中某项目包含 `stars_growth_7d` 非 None 值
- **THEN** 对应 `RepoBrief.stars_growth_7d` 被正确填充，`format_for_prompt()` 输出中显示 `⭐ {stars}（+{N}）`

#### Scenario: 评分层无增长数据时降级
- **WHEN** `scored_repos` JSON 中某项目 `stars_growth_7d` 为 null 或缺失
- **THEN** 对应 `RepoBrief.stars_growth_7d` 为 None，`format_for_prompt()` 输出中显示 `⭐ {stars}`（无增长标注）

### Requirement: 评分层保留并传递 stars_growth_7d
`TrendScoringCrew` 的输出模型 `ScoredRepo` SHALL 包含 `stars_growth_7d: int | None` 字段，评分层 LLM SHALL 从输入的 `github_data` 中读取该字段并原样传递到输出 JSON，不得修改或丢弃。

#### Scenario: 评分层原样传递增长数据
- **WHEN** `github_data` 中某项目包含 `7日增长: +2000`
- **THEN** 评分层输出的对应 `scored_repos` 条目中 `stars_growth_7d` 为 2000
