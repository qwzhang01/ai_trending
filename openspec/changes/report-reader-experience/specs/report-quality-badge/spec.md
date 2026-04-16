## ADDED Requirements

### Requirement: 报告末尾包含质量置信度徽章
`nodes.py` 的质量审核节点执行完成后，SHALL 将 `QualityReviewResult` 的关键数据渲染为可读段落，追加到报告内容末尾，让读者了解本期报告的置信程度。

#### Scenario: 高置信度徽章（≥15/18）
- **WHEN** 质量审核通过率 ≥ 15/18，且无 error 级问题
- **THEN** 报告末尾追加：`## 本期置信度\n✅ 高置信度（{passed}/{total}）· 无事实核对问题`

#### Scenario: 中置信度徽章（10-14/18）
- **WHEN** 质量审核通过率在 10-14/18 之间
- **THEN** 报告末尾追加：`## 本期置信度\n🟡 中置信度（{passed}/{total}）· {主要问题摘要}`

#### Scenario: 低置信度徽章（<10/18）
- **WHEN** 质量审核通过率 < 10/18，或存在 error 级问题
- **THEN** 报告末尾追加：`## 本期置信度\n⚠️ 低置信度（{passed}/{total}）· {error级问题描述}`

#### Scenario: 质量审核未执行时不追加徽章
- **WHEN** `QualityReviewResult` 为 None 或质量审核节点被跳过
- **THEN** 报告末尾不追加任何置信度内容，不影响报告正常输出

### Requirement: quality_badge 渲染逻辑在节点层实现
质量置信度徽章 SHALL 在 `nodes.py` 的 `quality_review_node` 执行完成后，由节点层代码直接拼接到 `report_content` 字符串末尾，不通过写作层 LLM 生成，确保徽章内容与审核结果严格一致。

#### Scenario: 节点层拼接而非 LLM 生成
- **WHEN** 质量审核完成，`QualityReviewResult.passed` 和 `issues` 已确定
- **THEN** 节点层代码（非 LLM）根据通过率阈值选择徽章模板并填充数据，追加到报告末尾

### Requirement: 主要问题摘要不超过 30 字
当置信度为中或低时，徽章中的问题摘要 SHALL 从 `QualityReviewResult.issues` 中提取最高 severity 的前 2 条问题描述，合并后不超过 30 字。

#### Scenario: 多个问题时取最高 severity 的前 2 条
- **WHEN** `issues` 中存在多个问题
- **THEN** 优先取 `severity=error` 的问题，其次取 `severity=warning`，最多取 2 条，合并描述不超过 30 字
