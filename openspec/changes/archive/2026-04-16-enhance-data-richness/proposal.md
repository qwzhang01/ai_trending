## Why

当前日报写作层（ReportWritingCrew）拿到的 GitHub 项目素材极度匮乏：只有星数和一句话描述，没有 README 内容、没有近期星数增长数据。评分层（TrendScoringCrew）生成的 `story_hook`、`technical_detail` 等叙事字段只能基于这一句话描述推断，导致写作层只能套模板填充，每篇日报读起来像功能列举而非真实故事。这是日报"没有亮点、没有吸引力"的根本原因（对应需求文档 TD-001 数据源过薄）。

## What Changes

- **新增 README 摘要采集**：在 GitHub 项目采集阶段，为每个入选项目抓取 README 前 1500 字符，作为写作素材注入评分层和写作层
- **新增 7 日星数增长追踪**：利用现有 `StarTracker` 的能力，将 `stars_growth_7d` 字段从"可选"变为"必填"，确保每个项目都有增长数据
- **评分层叙事字段质量提升**：在 `story_hook`、`technical_detail` 有了 README 素材后，要求评分层必须引用真实的技术细节（架构名称、具体数字、对比对象），不允许纯推断
- **写作简报传递链路补全**：`RepoBrief.readme_summary` 字段已存在但始终为空，本次确保数据从采集层流转到写作层

## Capabilities

### New Capabilities

- `github-readme-fetch`：GitHub 项目 README 内容采集能力——在趋势项目采集阶段，为每个项目异步抓取 README 原始内容并截取前 1500 字符，注入到项目数据结构中
- `star-growth-enrichment`：星数增长数据补全能力——确保 `stars_growth_7d` 在数据流全链路（采集→评分→写作简报）中有值，而非依赖可选字段

### Modified Capabilities

- `trend-scoring-narrative`：评分层叙事字段生成规则变更——在有 README 素材的前提下，`story_hook` 和 `technical_detail` 必须引用真实内容（具体架构名、数字、对比项目），禁止纯推断式描述

## Impact

- **采集层**：`crew/github_trending/fetchers.py` 或 `crew/github_trending/crew.py` 需新增 README 抓取逻辑（异步批量，超时 5s，失败降级为空字符串）
- **数据模型**：`crew/github_trending/models.py` 中项目模型新增 `readme_summary: str` 字段
- **评分层 Prompt**：`crew/trend_scoring/config/tasks.yaml` 中 `story_hook`/`technical_detail` 的生成规则需更新，要求引用 README 中的真实内容
- **写作简报构建**：`nodes.py` 中 `_build_writing_brief` 函数需将 `readme_summary` 从 GitHub 数据中提取并填入 `RepoBrief`
- **星数增长**：`crew/github_trending/star_tracker.py` 已有追踪逻辑，需确认数据是否正确流转到 `scored_repos` 的 `stars_growth_7d` 字段
- **外部依赖**：新增 GitHub raw content API 调用（`raw.githubusercontent.com`），无需额外鉴权，但需处理 404/超时
