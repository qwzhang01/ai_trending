## ADDED Requirements

### Requirement: 根据信号强度选择报告模板
`nodes.py` 中的 `writing_brief_node` SHALL 根据编辑决策中的 `signal_strength` 字段，向 `WritingBrief` 注入 `report_template` 字段，写作层 SHALL 严格按照注入的模板结构生成报告。

#### Scenario: 红色信号日使用深度解析模板
- **WHEN** `editorial_plan.signal_strength` 为 `red`
- **THEN** `WritingBrief.report_template` 为 `deep-dive`，写作层头条段落占总字数 ≥ 40%，且包含"背景"、"影响"、"局限性"三个子视角

#### Scenario: 黄色信号日使用标准七段式模板
- **WHEN** `editorial_plan.signal_strength` 为 `yellow`
- **THEN** `WritingBrief.report_template` 为 `standard`，写作层按现有七段式结构输出

#### Scenario: 绿色信号日使用趋势回顾模板
- **WHEN** `editorial_plan.signal_strength` 为 `green`
- **THEN** `WritingBrief.report_template` 为 `review`，写作层输出包含"本周整体趋势"、"上期预测验证"、"下期预判"三个核心段落，GitHub 热点项目段落可缩减至 1-2 个

### Requirement: WritingBrief 包含 report_template 字段
`WritingBrief` 模型 SHALL 新增 `report_template: str` 字段，默认值为 `standard`，可选值为 `deep-dive`、`standard`、`review`。

#### Scenario: 默认值兜底
- **WHEN** `signal_strength` 字段缺失或为未知值
- **THEN** `report_template` 使用默认值 `standard`，写作层正常执行七段式结构

### Requirement: 写作层 Prompt 包含三套模板结构说明
`write_report_task` 的 `description` SHALL 包含三套模板的结构定义，写作层 LLM SHALL 根据 `{report_template}` 变量选择对应结构执行。

#### Scenario: deep-dive 模板结构
- **WHEN** `report_template` 为 `deep-dive`
- **THEN** 写作层输出结构为：信号强度 → 今日一句话 → 今日头条（深度，含背景/影响/局限性）→ AI 热点新闻 → 趋势洞察 → 本周行动建议

#### Scenario: review 模板结构
- **WHEN** `report_template` 为 `review`
- **THEN** 写作层输出结构为：信号强度 → 今日一句话 → 本周整体趋势 → GitHub 热点（精简）→ AI 热点新闻 → 上期预测验证 → 下期预判
