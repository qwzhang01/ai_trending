## ADDED Requirements

### Requirement: 新闻条目使用合并标签格式
每条新闻 SHALL 使用 `{credibility_emoji} {category}` 的合并标签格式，不使用双方括号标签。

可信度 emoji 映射：
- `🟢` → 一手信源
- `🟡` → 社区讨论
- `🔴` → 待验证

#### Scenario: 有可信度标签和类别标签时合并输出
- **WHEN** 新闻条目同时具有 `credibility_label`（如 `🟡 社区讨论`）和 `category`（如 `技术突破`）
- **THEN** 输出格式为 `🟡 技术突破 {新闻标题}`，不出现方括号

#### Scenario: 只有可信度标签时仅输出 emoji
- **WHEN** 新闻条目有 `credibility_label` 但 `category` 为空
- **THEN** 输出格式为 `🟡 {新闻标题}`，不出现方括号

#### Scenario: 两个标签均为空时直接输出标题
- **WHEN** 新闻条目的 `credibility_label` 和 `category` 均为空
- **THEN** 输出格式为 `{新闻标题}`，无任何前缀标签

### Requirement: prompt 中的格式示例与新格式一致
写作层 `tasks.yaml` 中的新闻格式说明 SHALL 使用新格式示例，不出现双方括号格式。

#### Scenario: tasks.yaml 中的格式示例使用新格式
- **WHEN** 写作层 prompt 中描述新闻条目格式
- **THEN** 示例格式为 `🟡 技术突破 标题` 而非 `[🟡 社区讨论][技术突破] 标题`

### Requirement: format_for_prompt 输出新格式
`WritingBrief.format_for_prompt()` SHALL 将 `credibility_label` 中的 emoji 与 `category` 合并为单一标签输出。

#### Scenario: format_for_prompt 正确提取 emoji 并合并
- **WHEN** `credibility_label` 为 `🟡 社区讨论`，`category` 为 `投融资`
- **THEN** `format_for_prompt()` 输出该条新闻时前缀为 `🟡 投融资`，不含方括号
