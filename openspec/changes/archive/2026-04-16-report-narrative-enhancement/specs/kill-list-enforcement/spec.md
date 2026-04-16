## MODIFIED Requirements

### Requirement: 今日一句话差异性约束
编辑 Agent 在生成「今日一句话」时，SHALL 与近 7 天的历史「今日一句话」做差异性检查，确保语义不重复。写作层 Prompt MUST 在动态数据段中列出近 7 天的历史 hook，并明确要求生成的 hook 与历史任意一条的语义相似度 < 60%。禁止使用"AI技术持续演进"、"AI持续演进"等泛化表述；MUST 包含当天数据中的至少一个具体词汇（项目名、技术名词、数字）。

#### Scenario: 今日一句话与近 7 天历史完全相同
- **WHEN** 生成的「今日一句话」与 `TOPIC_TRACKER.md` 中近 7 天任意一条完全相同
- **THEN** 写作层 Agent SHALL 重新生成，直到与历史不重复

#### Scenario: 今日一句话语义高度相似（泛化变体）
- **WHEN** 生成的「今日一句话」是历史 hook 的泛化变体（如"AI技术演进"、"AI持续发展"）
- **THEN** 写作层 Agent SHALL 基于今日具体数据（头条项目名、关键技术词、星数增长）生成有观点的判断句

#### Scenario: 今日一句话包含当天特有词汇
- **WHEN** 写作层 Prompt 中包含今日头条项目名和关键技术词
- **THEN** 生成的「今日一句话」MUST 包含其中至少一个具体词汇，不得使用完全泛化的句式

#### Scenario: Kill List 为空
- **WHEN** `get_topic_history` 返回的 Kill List 为空
- **THEN** Agent SHALL 正常执行，不做额外约束
