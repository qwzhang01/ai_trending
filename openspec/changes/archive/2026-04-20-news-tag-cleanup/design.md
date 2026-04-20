## Context

当前新闻条目格式为：
```
- [🟡 社区讨论][技术突破] DeepSeek V4 据传将发布...
```

两个方括号标签并排，存在以下问题：
1. **视觉冗余**：两对方括号紧贴，读者需要分别解析两个标签
2. **信息层级不清**：可信度（emoji 圆点）和类别（文字）是两个维度的信息，但视觉权重相同，没有主次之分
3. **微信渲染差**：在微信公众号 HTML 中，`[🟡 社区讨论][技术突破]` 渲染为纯文本，两个方括号组紧贴，视觉更拥挤

涉及的代码路径：
- `src/ai_trending/crew/report_writing/models.py`：`WritingBrief.format_for_prompt()` 中的标签拼接
- `src/ai_trending/crew/report_writing/config/tasks.yaml`：写作层 prompt 中的格式示例
- LLM 生成的 Markdown 输出（由 prompt 约束控制）

## Goals / Non-Goals

**Goals:**
- 将双标签 `[🟡 社区讨论][技术突破]` 合并为单标签 `🟡 技术突破`
- 用 emoji 圆点颜色承载可信度信息（🟢/🟡/🔴），用紧跟的文字承载类别信息
- 去掉所有方括号，减少视觉噪音
- 同步更新 prompt 中的格式示例，确保 LLM 输出新格式

**Non-Goals:**
- 不修改可信度标签的语义（🟢/🟡/🔴 含义不变）
- 不修改类别标签的枚举值（大厂动态/技术突破/投融资等不变）
- 不修改微信 HTML 渲染逻辑（标签是纯文本，无需特殊处理）
- 不修改历史报告文件

## Decisions

### 决策 1：新格式为 `{emoji} {category}`，不加方括号

**选项 A（采用）**：`🟡 技术突破`
- 优点：简洁，emoji 自带视觉区分，类别文字直接跟随，一眼可读
- 缺点：去掉方括号后，标签与标题之间的边界依赖空格，需确保格式一致

**选项 B（放弃）**：`[🟡 技术突破]`
- 保留一个方括号，减少改动
- 缺点：方括号仍然存在，视觉改善有限

**选项 C（放弃）**：用 badge 样式（如 HTML span）
- 微信公众号不支持外链 CSS，内联样式复杂度高，维护成本大

### 决策 2：修改点集中在 prompt 层，不修改数据模型

`credibility_label` 和 `category` 字段继续独立存储，只在格式化输出时合并。这样：
- 数据模型保持向后兼容
- 未来如需恢复双标签或调整格式，只需改 prompt，不需迁移数据

### 决策 3：`format_for_prompt()` 中同步更新拼接逻辑

`WritingBrief.format_for_prompt()` 中当前拼接为：
```python
label = f"[{news.credibility_label}]" if news.credibility_label else ""
cat = f"[{news.category}]" if news.category else ""
lines.append(f"\n**{i}.** {label}{cat} {news.title}")
```

改为：
```python
# 从 credibility_label 中提取 emoji（取第一个字符）
emoji = news.credibility_label.split()[0] if news.credibility_label else ""
tag = f"{emoji} {news.category}".strip() if (emoji or news.category) else ""
lines.append(f"\n**{i}.** {tag} {news.title}".strip())
```

## Risks / Trade-offs

- **LLM 输出一致性风险**：LLM 可能沿用旧格式（有历史报告作为参考）。缓解：在 prompt 中明确给出新格式示例，并在 `tasks.yaml` 中添加格式约束说明。
- **历史报告不一致**：已生成的历史报告仍使用旧格式，但这是可接受的，不需要回填。
