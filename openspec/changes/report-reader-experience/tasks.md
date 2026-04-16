## 1. 模型扩展

- [ ] 1.1 `trend_scoring/models.py` — `ScoredRepo` 新增 `audience_tag: str` 字段，默认值 `"general"`
- [ ] 1.2 `report_writing/models.py` — `WritingBrief` 新增 `report_template: str` 字段，默认值 `"standard"`
- [ ] 1.3 `report_writing/models.py` — `ReportOutput` 新增 `quality_badge: str` 字段，默认空字符串

## 2. 评分层：audience_tag 生成

- [ ] 2.1 `trend_scoring/config/tasks.yaml` — 在评分指令中新增 `audience_tag` 字段说明，列出四个可选值（developer / product / investor / general）及判断标准
- [ ] 2.2 `trend_scoring/config/tasks.yaml` — 明确说明 `general` 为兜底选项，不得作为首选，鼓励 LLM 优先精确分类

## 3. 节点层：report_template 注入

- [ ] 3.1 `nodes.py` — 在 `writing_brief_node` 中，根据 `editorial_plan.signal_strength` 映射 `report_template`（red→deep-dive，yellow→standard，green→review），注入 `WritingBrief`
- [ ] 3.2 `nodes.py` — 映射逻辑缺失或未知值时，`report_template` 默认为 `standard`

## 4. 节点层：quality_badge 渲染

- [ ] 4.1 `nodes.py` — 在 `quality_review_node` 执行完成后，根据通过率阈值（≥15 高 / 10-14 中 / <10 低）选择徽章模板
- [ ] 4.2 `nodes.py` — 从 `QualityReviewResult.issues` 中提取最高 severity 的前 2 条问题，合并为不超过 30 字的摘要
- [ ] 4.3 `nodes.py` — 将渲染好的 `quality_badge` 字符串追加到 `report_content` 末尾；`QualityReviewResult` 为 None 时跳过

## 5. 写作层：模板结构和读者标签

- [ ] 5.1 `report_writing/config/tasks.yaml` — 在写作指令中新增 `{report_template}` 变量，定义三套模板结构（deep-dive / standard / review）的输出要求
- [ ] 5.2 `report_writing/config/tasks.yaml` — 在趋势洞察生成指令中，要求每条洞察开头标注读者群体标签（🧑‍💻 开发者 / 💼 产品 / 💰 投资 / 🌐 通用）
- [ ] 5.3 `report_writing/config/tasks.yaml` — 在写作简报中透传 `audience_tag` 数据，供写作层参考项目的目标读者

## 6. 验证

- [ ] 6.1 检查 `mypy` 类型检查通过（`ScoredRepo.audience_tag`、`WritingBrief.report_template`、`ReportOutput.quality_badge` 字段类型正确）
- [ ] 6.2 检查 `ruff format` 格式化通过
