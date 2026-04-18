## ADDED Requirements

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
