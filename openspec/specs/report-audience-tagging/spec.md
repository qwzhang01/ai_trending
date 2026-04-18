## ADDED Requirements

### Requirement: 趋势洞察每条包含读者群体标签
写作层生成的趋势洞察 Section 中，每条洞察 SHALL 在开头包含读者群体标签（🧑‍💻 开发者 / 💼 产品 / 💰 投资 / 🌐 通用），帮助读者快速定位与自己相关的内容。

#### Scenario: 技术实现类洞察标注开发者标签
- **WHEN** 洞察内容涉及技术框架、API、性能优化、开源工具等技术实现细节
- **THEN** 该条洞察开头标注 `🧑‍💻 开发者`

#### Scenario: 产品功能类洞察标注产品标签
- **WHEN** 洞察内容涉及产品功能落地、用户体验、市场需求、应用场景等
- **THEN** 该条洞察开头标注 `💼 产品`

#### Scenario: 融资市场类洞察标注投资标签
- **WHEN** 洞察内容涉及融资动态、市场规模、竞争格局、商业模式等
- **THEN** 该条洞察开头标注 `💰 投资`

#### Scenario: 通用洞察使用通用标签
- **WHEN** 洞察内容不明显偏向某一特定读者群体
- **THEN** 该条洞察开头标注 `🌐 通用`

### Requirement: ScoredRepo 包含 audience_tag 字段
`ScoredRepo` 模型 SHALL 新增 `audience_tag: str` 字段，默认值为 `general`，可选值为 `developer`、`product`、`investor`、`general`。评分层 LLM SHALL 根据项目的技术特征和应用场景填写该字段。

#### Scenario: 基础设施/工具类项目标注 developer
- **WHEN** 项目为 SDK、框架、调试工具、CLI 工具、推理引擎等面向开发者的基础设施
- **THEN** `audience_tag` 为 `developer`

#### Scenario: 应用/平台类项目标注 product
- **WHEN** 项目为面向终端用户的应用、平台或 SaaS 工具
- **THEN** `audience_tag` 为 `product`

#### Scenario: 商业化/融资相关项目标注 investor
- **WHEN** 项目背后有明确的商业化路径或融资背景
- **THEN** `audience_tag` 为 `investor`

#### Scenario: 无明显偏向时使用 general
- **WHEN** 项目特征无法明确归类到上述三类
- **THEN** `audience_tag` 为 `general`，不强制分类

### Requirement: 评分层 Prompt 包含 audience_tag 判断标准
`trend_scoring` 的 `tasks.yaml` SHALL 在评分指令中明确 `audience_tag` 的四个可选值及其判断标准，并说明 `general` 为兜底选项而非首选，鼓励 LLM 优先尝试精确分类。

#### Scenario: Prompt 约束 general 不作为首选
- **WHEN** 评分层 LLM 生成 `audience_tag`
- **THEN** 仅当项目确实无法归类时才使用 `general`，不得将 `general` 作为默认输出
