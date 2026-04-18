## Context

当前日报生成流水线中，新闻采集（`new_collect`）和 GitHub 项目评分（`trend_scoring`）是两条完全独立的数据流，直到写作层才汇合。编辑策划层（`editorial_planning`）负责决策头条和角度，但它只能看到项目数据，看不到新闻数据，因此无法发现"同一技术方向在新闻和 GitHub 同时爆发"这类高价值信号。

项目生命周期方面，`star_snapshots` 目录已有近 7 天的历史快照，`stars_growth_7d` 字段也已实现，但这些数据目前只用于展示增长数字，没有被转化为语义化的阶段判断。

## Goals / Non-Goals

**Goals:**
- 在编辑策划层引入新闻×项目关键词共振检测，输出 `resonance_signals` 列表
- 在评分层为每个项目计算生命周期标签（`lifecycle_tag`），传递到写作层
- 写作层在趋势洞察中优先呈现共振信号，在项目名旁展示生命周期标签

**Non-Goals:**
- 不引入外部 NLP 库做语义相似度计算，只做关键词匹配
- 不修改新闻采集流程，复用已有的新闻数据
- 不改变日报的整体七段式结构

## Decisions

### 决策 1：共振检测在编辑策划层做，而非写作层

**选择**：在 `editorial_planning` 的 task prompt 中，将新闻数据和项目数据同时传入，由 LLM 完成关键词共振检测。

**理由**：编辑策划层已经是"决策层"，负责判断信号强度和头条选择，共振检测是同类决策。写作层应该只负责"执行"，不应承担分析职责。

**替代方案**：在 `nodes.py` 中用 Python 做关键词匹配 → 被否，因为关键词提取需要语义理解（如"MCP"和"Model Context Protocol"是同一概念），LLM 更合适。

### 决策 2：生命周期标签在评分层计算，基于规则而非 LLM 判断

**生命周期标签规则：**

```
🌱 新生：项目创建 < 30 天 且 stars < 2000
🚀 爆发：stars_growth_7d / (stars - stars_growth_7d) > 20%（7日增长率超过20%）
📈 稳健：stars > 5000 且 stars_growth_7d > 0 且 不满足爆发条件
⚠️ 异常：stars_growth_7d > 1000 且 无对应新闻（由编辑策划层标注）
默认：🔵 普通（不满足以上任何条件）
```

**理由**：生命周期判断是确定性规则，不需要 LLM，在评分层的 task prompt 中用规则描述即可，LLM 按规则输出标签字符串。

### 决策 3：`resonance_signals` 作为 `EditorialPlan` 的新字段

```python
class ResonanceSignal(BaseModel):
    keyword: str          # 共振关键词，如 "MCP"
    repo_names: list[str] # 涉及的项目名
    news_titles: list[str] # 涉及的新闻标题
    strength: str         # "strong" | "moderate"

class EditorialPlan(BaseModel):
    ...
    resonance_signals: list[ResonanceSignal] = []
```

### 决策 4：新闻数据如何传入编辑策划层

当前 `editorial_planning_node` 只接收 `github_data` 和 `scored_repos`。需要在 `nodes.py` 中将 `filtered_news`（新闻筛选结果）也传入编辑策划任务的 inputs。

## Risks / Trade-offs

- **[风险] LLM 共振检测误报**：LLM 可能把不相关的关键词判断为共振 → 缓解：在 prompt 中要求 strength 字段区分强/弱共振，写作层只在 strong 时才在趋势洞察中突出展示
- **[风险] 生命周期标签计算依赖 stars_growth_7d**：若无历史快照数据则 stars_growth_7d 为 None，爆发标签无法计算 → 缓解：None 时降级为"普通"标签，不影响主流程
- **[Trade-off] 编辑策划层 prompt 变长**：加入新闻数据后 token 消耗增加约 30% → 可接受，新闻数据已经是精选的 8 条，总量可控
