## ADDED Requirements

### Requirement: formatter 输出包含 README 摘要
`format_text_output` 函数 SHALL 在每个仓库的输出块中包含 `readme_summary` 字段，截断到 300 字符。当 `readme_summary` 为空字符串时，SHALL 输出 `README摘要: （暂无）` 占位符，确保评分层 LLM 知晓该字段存在但无内容。

#### Scenario: README 有内容时正常输出
- **WHEN** `RepoCandidate.readme_summary` 非空
- **THEN** `format_text_output` 输出中包含 `README摘要: <前300字符>...` 行

#### Scenario: README 为空时输出占位符
- **WHEN** `RepoCandidate.readme_summary` 为空字符串
- **THEN** `format_text_output` 输出中包含 `README摘要: （暂无）` 行

### Requirement: README 摘要长度控制
`_fetch_readme_summary` 方法 SHALL 将清洗后的 README 文本截断到 **500 字符**（`RepoCandidate` 存储层），`format_text_output` 在序列化为字符串时 SHALL 进一步截断到 **300 字符**（Prompt 传递层），两层截断分别控制存储和传输开销。

#### Scenario: 存储层截断
- **WHEN** README 清洗后超过 500 字符
- **THEN** `RepoCandidate.readme_summary` 存储不超过 500 字符的内容

#### Scenario: Prompt 传递层截断
- **WHEN** `readme_summary` 超过 300 字符
- **THEN** `format_text_output` 输出的 README 摘要不超过 300 字符，末尾追加 `...`

### Requirement: README 抓取失败不阻断主流程
README 抓取 SHALL 在单个仓库失败时静默降级（`readme_summary` 保持空字符串），不抛出异常，不影响其他仓库的处理。

#### Scenario: 单个仓库 README 抓取超时
- **WHEN** 某仓库的 README API 请求超时（>10s）
- **THEN** 该仓库 `readme_summary` 为空字符串，其他仓库正常处理，主流程继续

#### Scenario: 仓库无 README（404）
- **WHEN** GitHub API 返回 404
- **THEN** 该仓库 `readme_summary` 为空字符串，不记录错误日志（仅 debug 级别）
