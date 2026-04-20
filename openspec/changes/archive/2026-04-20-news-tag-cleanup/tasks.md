## 1. 修改 format_for_prompt 标签拼接逻辑

- [x] 1.1 修改 `src/ai_trending/crew/report_writing/models.py` 中 `WritingBrief.format_for_prompt()` 的标签拼接代码：将 `[{credibility_label}][{category}]` 改为从 `credibility_label` 提取 emoji 后与 `category` 合并为 `{emoji} {category}`

## 2. 更新 prompt 格式示例

- [x] 2.1 修改 `src/ai_trending/crew/report_writing/config/tasks.yaml`：将七段式结构示例中的新闻格式说明从 `[可信度标签][类别] 标题` 更新为 `🟡 类别 标题`，确保 LLM 生成新格式

## 3. 格式化与验证

- [x] 3.1 运行 `uv run ruff format src/ai_trending/crew/report_writing/models.py` 格式化修改后的文件
