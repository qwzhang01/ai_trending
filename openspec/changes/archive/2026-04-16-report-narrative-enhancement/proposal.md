## Why

当前日报的叙事质量存在三个明显问题：**今日一句话连续 7 天完全相同**（"AI技术持续演进"），**头条缺乏跨日期对比**导致每篇报告像孤立的快照而非连续叙事，以及**从未验证上期行动建议的准确性**，读者无法建立对报告的信任感。这三个问题叠加，使报告读起来像模板填充而非有观点的分析。

## What Changes

- **今日一句话强约束**：写作层必须生成当天特有的判断句，禁止使用泛化表述；引入历史去重校验，与近 7 天任意一句话相似度 > 60% 则强制重写
- **对比叙事机制**：头条项目描述中引入跨日期对比视角（如"上周还在被吐槽，这周已经 Trending 第一"），需要从 star_snapshots 和 TOPIC_TRACKER 中读取历史数据
- **上期预测验证段落**：在报告末尾新增"上期验证"Section，对上期"本周行动建议"中提到的项目进行星数追踪和预测准确性评估

## Capabilities

### New Capabilities

- `report-previous-verification`: 上期行动建议验证机制——从 star_snapshots 读取历史星数，对比上期建议项目的实际变化，生成验证结论（✓ 准确 / ✗ 偏差）

### Modified Capabilities

- `kill-list-enforcement`: 扩展今日一句话的去重约束，增加相似度检测规则，确保每日一句话具有当天特异性
- `trend-scoring-narrative`: 评分层新增 `historical_context` 字段，从 star_snapshots 提取项目的历史星数轨迹，供写作层生成对比叙事

## Impact

- `src/ai_trending/crew/report_writing/` — 写作层 tasks.yaml 增加今日一句话约束和上期验证段落指令
- `src/ai_trending/crew/report_writing/models.py` — ReportOutput 或 WritingBrief 新增 previous_verification 字段
- `src/ai_trending/crew/trend_scoring/` — 评分层 models.py 新增 historical_context 字段，formatter.py 读取 star_snapshots 填充历史数据
- `src/ai_trending/crew/report_writing/tracker.py` — 今日一句话相似度校验逻辑
- `output/TOPIC_TRACKER.md` — 今日一句话历史记录（已有，作为去重数据源）
- `output/star_snapshots/` — 历史星数快照（已有，作为验证数据源）
