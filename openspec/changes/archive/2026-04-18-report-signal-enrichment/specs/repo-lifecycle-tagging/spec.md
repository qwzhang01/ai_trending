## ADDED Requirements

### Requirement: 评分层为每个项目计算生命周期标签
`TrendScoringCrew` 的评分任务 SHALL 根据以下规则为每个项目输出 `lifecycle_tag` 字段（字符串）：
- `🌱 新生`：项目创建时间 < 30 天 且 stars < 2000
- `🚀 爆发`：`stars_growth_7d` 非 None 且 `stars_growth_7d / (stars - stars_growth_7d) > 0.20`（7日增长率超过 20%）
- `📈 稳健`：stars ≥ 5000 且 `stars_growth_7d` > 0 且不满足爆发条件
- `⚠️ 异常`：`stars_growth_7d` ≥ 1000 且项目创建时间 > 30 天 且不满足爆发条件
- `🔵 普通`：不满足以上任何条件时的默认值

规则按上述顺序优先级依次判断，匹配第一个满足的规则即停止。

#### Scenario: 新项目低星数标记为新生
- **WHEN** 项目创建时间 < 30 天 且 stars < 2000
- **THEN** `lifecycle_tag` 为 `🌱 新生`

#### Scenario: 7日增长率超过20%标记为爆发
- **WHEN** `stars_growth_7d` 为 500，`stars` 为 3000（增长率 ≈ 20%）
- **THEN** `lifecycle_tag` 为 `🚀 爆发`

#### Scenario: 高星数稳定增长标记为稳健
- **WHEN** stars 为 8000，`stars_growth_7d` 为 200，不满足爆发条件
- **THEN** `lifecycle_tag` 为 `📈 稳健`

#### Scenario: 无增长数据时降级为普通
- **WHEN** `stars_growth_7d` 为 None
- **THEN** `lifecycle_tag` 为 `🔵 普通`，不尝试计算增长率

#### Scenario: 不满足任何条件时为普通
- **WHEN** 项目不满足新生、爆发、稳健、异常任何一个条件
- **THEN** `lifecycle_tag` 为 `🔵 普通`

### Requirement: ScoredRepo 模型包含 lifecycle_tag 字段
`ScoredRepo` 模型 SHALL 包含 `lifecycle_tag: str` 字段，默认值为 `"🔵 普通"`。

#### Scenario: 评分层正常输出 lifecycle_tag
- **WHEN** 评分任务正常执行
- **THEN** 每个 `ScoredRepo` 条目均包含非空的 `lifecycle_tag` 字段

### Requirement: lifecycle_tag 流转到 RepoBrief 和写作层
`_build_writing_brief` 函数 SHALL 从 `scored_repos` JSON 中读取 `lifecycle_tag` 字段，填入 `RepoBrief.lifecycle_tag`。写作层 `format_for_prompt()` SHALL 在项目名旁展示该标签。

#### Scenario: lifecycle_tag 正确传递到写作简报
- **WHEN** `scored_repos` 中某项目 `lifecycle_tag` 为 `🚀 爆发`
- **THEN** 对应 `RepoBrief.lifecycle_tag` 为 `🚀 爆发`，`format_for_prompt()` 输出中项目名旁显示该标签

#### Scenario: lifecycle_tag 缺失时使用默认值
- **WHEN** `scored_repos` JSON 中某项目缺少 `lifecycle_tag` 字段
- **THEN** `RepoBrief.lifecycle_tag` 使用默认值 `🔵 普通`
