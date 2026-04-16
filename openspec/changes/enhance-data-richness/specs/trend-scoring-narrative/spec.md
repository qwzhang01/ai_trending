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
