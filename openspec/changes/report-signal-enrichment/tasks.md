## 1. 模型扩展

- [ ] 1.1 在 `trend_scoring/models.py` 的 `ScoredRepo` 模型中新增 `lifecycle_tag: str` 字段，默认值 `"🔵 普通"`
- [ ] 1.2 在 `editorial_planning/models.py` 中新增 `ResonanceSignal` 模型（keyword / repo_names / news_titles / strength 字段）
- [ ] 1.3 在 `editorial_planning/models.py` 的 `EditorialPlan` 模型中新增 `resonance_signals: list[ResonanceSignal]` 字段，默认空列表
- [ ] 1.4 在 `report_writing/models.py` 的 `RepoBrief` 模型中新增 `lifecycle_tag: str` 字段，默认值 `"🔵 普通"`

## 2. 评分层：生命周期标签计算

- [ ] 2.1 在 `trend_scoring/config/tasks.yaml` 的评分任务 prompt 中新增生命周期标签计算规则（5条规则按优先级顺序：新生/爆发/稳健/异常/普通）
- [ ] 2.2 在评分任务 prompt 中明确要求 LLM 在每个项目的输出 JSON 中填入 `lifecycle_tag` 字段

## 3. 编辑策划层：共振检测

- [ ] 3.1 在 `nodes.py` 的 `editorial_planning_node` 函数中，将 `filtered_news` 格式化为字符串并加入 inputs（key: `news_data`）
- [ ] 3.2 在 `editorial_planning/config/tasks.yaml` 的编辑策划任务 prompt 中新增共振检测步骤：要求 LLM 对比新闻关键词和项目关键词，输出 `resonance_signals`
- [ ] 3.3 在编辑策划任务 prompt 中定义共振强度规则（strong: ≥2条新闻，moderate: 1条新闻）

## 4. 写作层：数据传递与展示

- [ ] 4.1 在 `nodes.py` 的 `_build_writing_brief` 函数中，从 `scored_repos` JSON 读取 `lifecycle_tag` 字段并填入 `RepoBrief.lifecycle_tag`
- [ ] 4.2 在 `report_writing/models.py` 的 `RepoBrief.format_for_prompt()` 方法中，在项目名旁展示 `lifecycle_tag`（格式：`项目名 lifecycle_tag ⭐ stars`）
- [ ] 4.3 在 `report_writing/config/tasks.yaml` 的写作任务 prompt 中，新增共振信号使用规范：当 `editorial_plan` 中存在 `strength == "strong"` 的共振信号时，趋势洞察第一条使用 📡 格式呈现

## 5. 验证

- [ ] 5.1 运行 `mypy` 类型检查，确认新增字段无类型错误
- [ ] 5.2 检查 `editorial_planning_node` 的 inputs 中 `news_data` 字段是否正确传入（打印或日志确认）
- [ ] 5.3 运行 `ruff format` 格式化所有修改的文件
