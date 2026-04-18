## ADDED Requirements

### Requirement: ScoredRepo 输出模型包含 lifecycle_tag 字段
`ScoredRepo` 输出模型 SHALL 新增 `lifecycle_tag: str` 字段，默认值为 `"🔵 普通"`。评分层 LLM SHALL 根据以下规则计算并填入该字段：
- `🌱 新生`：项目创建时间 < 30 天 且 stars < 2000
- `🚀 爆发`：`stars_growth_7d` 非 None 且 7日增长率（`stars_growth_7d / (stars - stars_growth_7d)`）> 20%
- `📈 稳健`：stars ≥ 5000 且 `stars_growth_7d` > 0 且不满足爆发条件
- `⚠️ 异常`：`stars_growth_7d` ≥ 1000 且项目创建时间 > 30 天 且不满足爆发条件
- `🔵 普通`：不满足以上任何条件

#### Scenario: 评分层按规则输出 lifecycle_tag
- **WHEN** 评分任务处理某项目，该项目 stars 为 3000，`stars_growth_7d` 为 800（增长率约 36%）
- **THEN** 该项目的 `lifecycle_tag` 输出为 `🚀 爆发`

#### Scenario: stars_growth_7d 为 None 时输出默认值
- **WHEN** 某项目 `stars_growth_7d` 为 None（无历史快照数据）
- **THEN** 该项目的 `lifecycle_tag` 输出为 `🔵 普通`，不尝试计算增长率
