## Context

当前日报系统已完成两轮优化（fix-report-quality-bugs、enhance-data-richness），数据采集层已具备 README 摘要和 7 日星数增长数据。但叙事层仍存在三个未解决的问题：

1. **今日一句话无差异化约束**：`topic_tracker.py` 记录了历史 hook，但写作层 Prompt 没有强制要求与历史不同，导致 LLM 倾向于生成最安全的泛化表述
2. **头条叙事缺乏时间维度**：`formatter.py` 已输出 `stars_growth_7d`，但没有输出项目的"历史出现记录"，写作层无法生成"上周还在被吐槽，这周 Trending 第一"这类对比叙事
3. **上期验证机制缺失**：`tracker.py`（PreviousReportTracker）已能追踪上期项目的星数变化，但没有对"本周行动建议"的预测准确性做结构化评估

## Goals / Non-Goals

**Goals:**
- 今日一句话必须包含当天特有的判断词汇，与近 7 天任意一条相似度 < 60%
- 头条项目描述支持跨日期对比叙事（需要 formatter 输出项目的历史出现记录）
- 报告末尾新增"上期验证"Section，对上期行动建议的项目进行星数追踪和预测评估

**Non-Goals:**
- 不改变报告的整体七段式结构
- 不引入新的外部 API 或数据源（复用 star_snapshots 和 TOPIC_TRACKER）
- 不修改质量审核层的评分逻辑

## Decisions

### 决策 1：今日一句话相似度校验放在哪一层？

**选择：写作层 Prompt 约束 + topic_tracker 提供历史数据**

- 方案 A：在 `topic_tracker.py` 中实现相似度计算，写作前先校验
- 方案 B：在写作层 Prompt 中列出近 7 天 hook，要求 LLM 自行判断差异性
- **选择方案 B**：实现简单，无需引入相似度算法依赖；LLM 对语义相似度的判断比字符串匹配更准确；且 topic_tracker 已经把历史 hook 传给了写作层

### 决策 2：历史出现记录如何传递给写作层？

**选择：在 formatter.py 中新增 `prev_appearances` 字段**

- 从 `output/TOPIC_TRACKER.md` 读取近 7 天记录，检查当前项目名是否出现过
- 输出格式：`历史出现: 2026-04-14(头条), 2026-04-12(热点)` 或 `历史出现: 首次上榜`
- 这样写作层可以直接生成"首次上榜"或"再度上榜"的对比叙事

### 决策 3：上期验证的数据来源

**选择：复用 PreviousReportTracker + 新增行动建议解析**

- `tracker.py` 已能追踪上期项目的当前星数
- 新增：从上期报告的"本周行动建议"Section 中解析被推荐的项目名
- 对比：上期推荐时的星数 vs 当前星数，计算增长率
- 评估标准：增长 > 10% 为 ✓ 准确，< 0% 为 ✗ 偏差，其余为 ~ 持平

## Risks / Trade-offs

- **[风险] TOPIC_TRACKER 解析脆弱** → 缓解：formatter 读取失败时降级为"首次上榜"，不阻断主流程
- **[风险] 上期报告格式不一致导致解析失败** → 缓解：行动建议解析失败时跳过验证段落，不输出空 Section
- **[Trade-off] 方案 B 依赖 LLM 判断相似度** → LLM 可能判断不准，但比字符串匹配更能识别语义相似（"AI持续演进" vs "AI技术演进"）；可在后续迭代中加字符串兜底
