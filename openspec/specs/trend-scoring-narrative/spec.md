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

### Requirement: ScoredRepo 输出包含 audience_tag 字段
`ScoredRepo` 输出模型 SHALL 包含 `audience_tag: str` 字段，默认值为 `general`，可选值为 `developer`、`product`、`investor`、`general`。评分层 LLM SHALL 根据项目的技术特征和应用场景判断最适合的读者群体并填写该字段。

#### Scenario: 基础设施/工具类项目标注 developer
- **WHEN** 项目为 SDK、框架、调试工具、CLI 工具、推理引擎等面向开发者的基础设施
- **THEN** 评分层输出的 `audience_tag` 为 `developer`

#### Scenario: 应用/平台类项目标注 product
- **WHEN** 项目为面向终端用户的应用、平台或 SaaS 工具，核心价值在于产品功能而非技术实现
- **THEN** 评分层输出的 `audience_tag` 为 `product`

#### Scenario: 商业化/融资相关项目标注 investor
- **WHEN** 项目背后有明确的商业化路径、融资背景，或其价值主要体现在市场机会层面
- **THEN** 评分层输出的 `audience_tag` 为 `investor`

#### Scenario: 无明显偏向时使用 general
- **WHEN** 项目特征无法明确归类到 developer / product / investor 任一类别
- **THEN** 评分层输出的 `audience_tag` 为 `general`，`general` 为兜底选项，不得作为首选

### Requirement: 评分层 Prompt 明确 audience_tag 判断标准
`trend_scoring` 的 `tasks.yaml` 评分指令 SHALL 包含 `audience_tag` 四个可选值的判断标准说明，并明确指出 `general` 为兜底而非首选，鼓励 LLM 优先尝试精确分类。

#### Scenario: Prompt 中包含分类判断标准
- **WHEN** 评分层 LLM 处理某个项目
- **THEN** LLM 能依据 Prompt 中的标准判断 audience_tag，而非随机输出或默认 general
