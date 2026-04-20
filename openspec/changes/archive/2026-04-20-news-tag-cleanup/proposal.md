## Why

当前每条新闻前有两个独立的方括号标签：`[🟡 社区讨论][技术突破]`，视觉上拥挤且层级不清晰。可信度标签（emoji 圆点 + 文字）和类别标签（纯文字）并排堆叠，读者需要解析两次才能获取信息，且在微信公众号 HTML 渲染后效果更差——两个方括号紧贴在一起，没有视觉区分度。

## What Changes

- **合并两个标签为一个**：将 `[🟡 社区讨论][技术突破]` 合并为 `🟡 技术突破`，用 emoji 圆点承载可信度信息，用文字承载类别信息，去掉多余的方括号
- **统一格式规范**：新格式为 `{credibility_emoji} {category}`，不再使用方括号包裹
- **更新 prompt 中的格式示例**：`tasks.yaml` 中的新闻格式说明同步更新
- **更新 models.py 中的格式化逻辑**：`WritingBrief.format_for_prompt()` 中拼接标签的代码同步更新

## Capabilities

### New Capabilities

- `news-tag-format`: 定义新闻条目标签的统一格式规范——将可信度标签（emoji）与类别标签（文字）合并为单一标签，消除双方括号冗余

### Modified Capabilities

（无现有 spec 需要修改）

## Impact

- `src/ai_trending/crew/report_writing/models.py`：`WritingBrief.format_for_prompt()` 中标签拼接逻辑
- `src/ai_trending/crew/report_writing/config/tasks.yaml`：新闻格式示例说明
- LLM 输出格式：写作层 prompt 中的格式约束需同步，确保 LLM 生成的 Markdown 使用新格式
