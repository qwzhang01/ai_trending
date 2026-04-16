## ADDED Requirements

### Requirement: 上期行动建议验证段落
报告写作层 SHALL 在"上期回顾"Section 中新增"行动建议验证"子段落，对上期"本周行动建议"中提到的项目进行星数追踪和预测准确性评估。

#### Scenario: 上期建议项目星数增长超过 10%
- **WHEN** 上期"本周行动建议"中提到的项目，当前星数较上期增长 > 10%
- **THEN** 报告中该项目验证结果标记为 ✓ 准确，并显示增长数字

#### Scenario: 上期建议项目星数无明显变化
- **WHEN** 上期建议项目当前星数较上期变化在 -10% ~ +10% 之间
- **THEN** 报告中该项目验证结果标记为 ~ 持平，并显示实际变化

#### Scenario: 上期建议项目星数下降
- **WHEN** 上期建议项目当前星数较上期下降 > 10%
- **THEN** 报告中该项目验证结果标记为 ✗ 偏差，并简要说明可能原因

#### Scenario: 无法获取上期建议数据
- **WHEN** 上期报告不存在或"本周行动建议"Section 解析失败
- **THEN** 跳过验证段落，不输出空 Section，不影响主流程

### Requirement: PreviousReportTracker 支持行动建议解析
`PreviousReportTracker` SHALL 新增 `parse_action_suggestions` 方法，从上期报告的"本周行动建议"Section 中解析被推荐的项目名称，并结合 star_snapshots 数据计算增长率。

#### Scenario: 成功解析行动建议中的项目名
- **WHEN** 上期报告包含"本周行动建议"Section 且其中提到了 GitHub 项目名
- **THEN** `parse_action_suggestions` 返回项目名列表，每项包含项目名和上期星数

#### Scenario: 行动建议中无明确项目名
- **WHEN** 上期"本周行动建议"只有泛化建议（无具体项目名）
- **THEN** `parse_action_suggestions` 返回空列表，不报错
