## 1. formatter 历史出现记录

- [x] 1.1 在 `formatter.py` 的 `format_text_output` 中新增 `_get_prev_appearances` 辅助函数，读取 `output/TOPIC_TRACKER.md` 并检查项目名是否在近 7 天记录中出现
- [x] 1.2 在每个仓库输出块中追加 `历史出现: {结果}` 行（首次上榜 / 日期+位置 / 数据不可用）
- [x] 1.3 读取 TOPIC_TRACKER 失败时静默降级，不抛出异常

## 2. 写作层今日一句话约束

- [x] 2.1 在 `report_writing/config/tasks.yaml` 的动态数据段中新增"近 7 天今日一句话历史"列表，从 `style_guidance` 或新增字段传入
- [x] 2.2 在写作层 Prompt 中明确约束：今日一句话 MUST 与历史任意一条语义不同，MUST 包含今日头条项目名或关键技术词，禁止使用"AI技术持续演进"等泛化表述
- [x] 2.3 在 `report_writing/crew.py` 或 `nodes.py` 中将 `topic_tracker.get_recent_hooks()` 的结果注入到写作层 inputs

## 3. 上期行动建议验证

- [x] 3.1 在 `report_writing/tracker.py` 的 `PreviousReportTracker` 中新增 `parse_action_suggestions` 方法，从上期报告"本周行动建议"Section 解析项目名
- [x] 3.2 新增 `build_verification_context` 方法，结合 star_snapshots 数据计算增长率，生成验证结论（✓ 准确 / ~ 持平 / ✗ 偏差）
- [x] 3.3 在写作层 tasks.yaml 的"上期回顾"Section 指令中新增验证段落格式要求
- [x] 3.4 在 `nodes.py` 或 `crew.py` 中将验证结果注入到 `previous_report_context` 字段

## 4. 验证与收尾

- [x] 4.1 运行 mypy 类型检查，确保新增字段类型正确
- [x] 4.2 运行 ruff format 格式化所有修改的 Python 文件
- [x] 4.3 检查 TOPIC_TRACKER.md 中近 7 天 hook 是否在下次运行后出现差异化内容
