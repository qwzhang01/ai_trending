## Why

当前日报在**结构和读者体验**层面存在三个问题：每天报告结构完全一致，读者看了 3 天就能预判下一段内容，缺乏惊喜感；所有读者收到同一份报告，但开发者、产品经理、投资人关注点截然不同；质量审核数据（passed/18）从未对外呈现，读者无法感知报告的置信度。这三个问题使报告的**复读价值**和**精准度**偏低。

## What Changes

- **报告模板多样化**：根据信号强度（🔴/🟡/🟢）选择不同的叙事结构——红色信号日采用深度解析模式（头条占 50% 篇幅，含背景+影响+反驳观点），绿色信号日采用趋势回顾模式（本周整体趋势+上期预测验证+下期预判），黄色信号日保持现有七段式结构
- **读者分层标签**：在趋势洞察 Section 中为每条洞察添加适合人群标签（🧑‍💻 开发者 / 💼 产品 / 💰 投资），帮助读者快速定位与自己相关的内容
- **质量置信度可视化**：在报告末尾新增"本期置信度"小节，展示质量审核通过率和主要风险点，让读者知晓报告的可信程度

## Capabilities

### New Capabilities

- `report-template-selector`: 信号强度驱动的报告模板选择机制——根据编辑决策中的 signal_strength 字段，在写作层选择对应的叙事结构模板（deep-dive / standard / review）
- `report-audience-tagging`: 读者分层标签机制——在趋势洞察生成时，为每条洞察自动标注最相关的读者群体标签
- `report-quality-badge`: 质量置信度徽章——将 QualityReviewResult 中的通过率和主要问题摘要渲染为报告末尾的可读段落

### Modified Capabilities

- `trend-scoring-narrative`: 评分层在生成 story_hook 时，需同时标注该项目最适合的读者群体（audience_tag 字段），供写作层的读者分层标签使用

## Impact

- `src/ai_trending/crew/report_writing/config/tasks.yaml` — 写作层 Prompt 增加模板选择逻辑和读者标签指令
- `src/ai_trending/crew/report_writing/models.py` — WritingBrief 新增 report_template 字段；ReportOutput 新增 quality_badge 字段
- `src/ai_trending/crew/trend_scoring/models.py` — ScoredRepo 新增 audience_tag 字段（可选值：developer / product / investor / general）
- `src/ai_trending/crew/trend_scoring/config/tasks.yaml` — 评分层 Prompt 增加 audience_tag 生成指令
- `src/ai_trending/nodes.py` — 在 writing_brief 构建阶段根据 signal_strength 注入 report_template，在报告生成后注入 quality_badge
