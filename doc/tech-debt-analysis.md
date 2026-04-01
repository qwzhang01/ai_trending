# AI Trending — 技术债务分析报告（日报质量专项）

> 📅 分析日期：2026-04-01
> 📁 分析范围：日报生成全流水线（数据采集 → 评分 → 撰写 → 输出）
> 🎯 目的：诊断"日报质量不够吸引人"的根因，制定系统性改进方案

---

## 0. 问题总述

对近期日报（3/27、3/30、3/31）的逐段审查，结合代码层面的全链路分析，发现当前日报质量问题**不是单点 Bug，而是流水线架构层面的系统性衰减**。

核心症状：
- 信号强度永远是 🟡，从未出现 🔴 或 🟢
- "今日一句话"跨日雷同（3/27 和 3/31 都是"MCP 生态成核心方向"变体）
- 趋势洞察每条都以"核心原因是…但是…"收尾，模板感强烈
- 偶现不合理数据（3/27 报告 `openclaw/openclaw：⭐ 336763`，33 万星极不寻常）
- 偶现 LLM 虚构统计（3/31 "适配成本占开发工作量的 30% 以上"无数据来源）

**根因诊断**：5 个流水线级技术债务。

| 编号 | 问题 | 严重度 | 影响 |
|------|------|--------|------|
| TD-001 | 数据源过薄，缺乏深度信息 | 🔴 高 | 写作层"无米之炊"，被迫虚构细节 |
| TD-002 | 评分层与写作层是"两个陌生人" | 🔴 高 | 评分产出的叙事字段被序列化后丢失 |
| TD-003 | Prompt 过度约束导致模板感 | 🟡 中 | 18 条硬约束 + 3 轮自检挤压创作空间 |
| TD-004 | 无"编辑部"机制，单 Agent 全包 | 🟡 中 | 缺少选题、角度、质检分工 |
| TD-005 | 无历史上下文利用 | 🟡 中 | 无风格记忆、无话题连续性追踪 |

---

## 1. TD-001: 数据源过薄，缺乏深度信息

**严重度**: 🔴 高
**影响范围**: `crew/github_trending/fetchers.py`, `crew/new_collect/fetchers.py`
**核心问题**: 写作层拿到的原始数据信息密度过低，导致 LLM 被迫"脑补"细节

### 1.1 GitHub 数据只有星数和描述

**代码定位**: `crew/github_trending/fetchers.py`

当前 `GitHubFetcher` 只调用 `GET /search/repositories`，返回的 `RepoCandidate` 模型仅包含 9 个字段：

```python
# fetchers.py — RepoCandidate 实际字段
class RepoCandidate:
    full_name: str       # "owner/repo"
    description: str     # 一句话描述（通常 20-50 字）
    language: str        # 主语言
    stars: int           # 当前星数（快照值，无历史）
    topics: list[str]    # GitHub Topics
    created_at: str      # 创建时间
    updated_at: str      # 最后更新时间
    html_url: str        # 仓库链接
    match_count: int     # 搜索命中次数
    heuristic_score: float  # 启发式评分
```

**缺失的关键数据**：

| 缺失字段 | 对写作的影响 | GitHub API 是否可获取 |
|----------|-------------|---------------------|
| README 摘要 | 写作层无法知道项目"到底做什么"，只能看 description | ✅ `GET /repos/{owner}/{repo}/readme` |
| 7 天前星数 | 无法计算真实增长趋势，只有一个快照数字 | ✅ 需要星数历史 API 或本地持久化 |
| 最近 30 天提交数 | 无法判断项目活跃度 | ✅ `GET /repos/{owner}/{repo}/stats/commit_activity` |
| Fork 数 | 无法判断社区参与度 | ✅ 已在 Search API 响应中，但未采集 |
| 贡献者数量 | 无法判断团队规模 | ✅ `GET /repos/{owner}/{repo}/contributors` |

**直接后果**：写作层在撰写"今日头条"和"GitHub 热点项目"时，只能基于 description 和星数硬编故事。这就是为什么日报中会出现"适配成本占开发工作量的 30% 以上"这样的虚构统计——LLM 在用编造的数据填充信息空白。

### 1.2 新闻数据缺乏正文内容

**代码定位**: `crew/new_collect/fetchers.py`（596 行）

4 个数据源的摘要情况：

| 数据源 | 摘要内容 | 代码位置 |
|--------|---------|---------|
| Hacker News | **永远是空字符串 `""`** | `fetchers.py:223` — `summary=""` |
| Reddit RSS | `content[:200]`（截断 200 字符） | `fetchers.py` |
| Reddit Pullpush | `selftext[:200]` | `fetchers.py` |
| newsdata.io | `description[:300]` | `fetchers.py` |
| 知乎热榜 | `excerpt[:200]` | `fetchers.py` |

**核心问题**：
- HN 的 summary **始终为空**，意味着写作层对 HN 新闻只有标题可用
- 其他源的摘要只有 200-300 字符，通常是第一段的开头，信息量有限
- **无正文抓取**：没有对新闻链接做正文提取，丢失了最关键的信息

**直接后果**：写作层在撰写"AI 热点新闻"的 So What 分析时，只能基于标题和不完整的摘要做推断。这就是为什么 So What 分析经常是"泛泛而谈"——LLM 不知道新闻具体说了什么。

---

## 2. TD-002: 评分层与写作层是"两个陌生人"

**严重度**: 🔴 高
**影响范围**: `nodes.py:138-254`, `crew/trend_scoring/models.py`, `crew/report_writing/config/tasks.yaml`
**核心问题**: 评分层产出丰富的叙事字段，但写作层几乎不知道它们的存在

### 2.1 评分模型中的叙事字段

**代码定位**: `crew/trend_scoring/models.py`（130 行）

`ScoredRepo` 模型实际包含 14 个字段，其中 4 个是专门为写作准备的叙事字段：

```python
class ScoredRepo(BaseModel):
    # ... 基础字段省略 ...
    story_hook: str = Field(description="故事钩子，≤20字")
    technical_detail: str = Field(description="技术细节，≤25字")
    target_audience: str = Field(description="目标受众，≤15字")
    scenario_description: str = Field(description="场景描述，≤25字")
```

`ScoredNews` 模型包含 10 个字段，其中关键的叙事字段：

```python
class ScoredNews(BaseModel):
    # ... 基础字段省略 ...
    so_what_analysis: str = Field(description="So What 分析，≤40字")
```

`DailySummary` 模型提供全局趋势判断：

```python
class DailySummary(BaseModel):
    top_trend: str           # 今日最重要趋势
    hot_directions: list[str]  # 3-5 个热点方向
    overall_sentiment: str    # 整体情绪
    causal_explanation: str   # 因果解释
    data_support: str         # 数据支撑
    forward_looking: str      # 前瞻判断
```

### 2.2 信息在传递中的衰减

**代码定位**: `nodes.py:163-165`（score_trends_node）, `nodes.py:184-254`（write_report_node）

```
评分层输出 (TrendScoringOutput)
  ├── scored_repos[].story_hook = "解决了X痛点"
  ├── scored_repos[].technical_detail = "基于Y架构"
  ├── scored_repos[].target_audience = "Z开发者"
  ├── scored_news[].so_what_analysis = "意味着A"
  └── daily_summary.causal_explanation = "B导致C"
       ↓
  json.dumps(output.model_dump())  ← 序列化为巨大 JSON 字符串
       ↓
  state["scoring_result"] = "{...整个JSON...}"  ← 存入 State
       ↓
  write_report_node 读取 scoring_result
       ↓
  ReportWritingCrew.kickoff(inputs={"scoring_result": scoring_result})
       ↓
  tasks.yaml 的 description 中：
    "评分数据: {scoring_result}"  ← 作为原始 JSON 字符串注入 Prompt
```

**问题**：
1. `story_hook`、`technical_detail` 等字段被埋在巨大的 JSON blob 中，写作 Agent 需要自行解析 JSON 并理解每个字段的含义
2. `tasks.yaml` 的 Prompt 中**没有明确引用这些字段名**，写作 Agent 不知道应该优先使用 `story_hook` 作为开篇
3. 评分层花了 default 档 LLM 的 token 生成这些叙事字段，但写作层可能完全忽略它们

**直接后果**：评分层做的"预写作"工作（story_hook、so_what_analysis）被浪费，写作层自己从零开始编故事，质量不稳定。

---

## 3. TD-003: Prompt 过度约束导致模板感

**严重度**: 🟡 中
**影响范围**: `crew/report_writing/config/tasks.yaml`, `crew/report_writing/config/agents.yaml`
**核心问题**: 271 行 tasks.yaml + 79 行 agents.yaml 的约束过多，挤压了 LLM 的创作空间

### 3.1 tasks.yaml 分析

**代码定位**: `crew/report_writing/config/tasks.yaml`（271 行，~5000 字符）

当前 Prompt 结构：

```
tasks.yaml 内容分布（约 5000 字符）:
├── 输入数据注入区          (~500 字)  — {github_data}, {scoring_result} 等
├── 三轮工作流描述          (~1200 字) — 第一轮信息提取 → 第二轮判断生成 → 第三轮文案
├── 七段式结构定义          (~800 字)  — 每个 Section 的格式和字数要求
├── 18 条硬约束列表         (~1500 字) — 禁用词、禁止句式、可信度标签、Emoji 密度等
├── 3 轮自检规则           (~500 字)  — 自检1: 禁用词 → 自检2: 句式 → 自检3: 模板感
└── expected_output 描述    (~500 字)  — 输出格式要求
```

**约束过载的证据**：

| 约束类别 | 数量 | 示例 |
|----------|------|------|
| 格式硬约束 | 18 条 | Section 必须存在、信号强度三选一、新闻三行格式... |
| 禁用词列表 | 20+ 个 | 重磅、震撼、颠覆、革命性... |
| 禁止句式 | 3 个 | "相当于…的…版"、"因为需求大所以增长快"... |
| 自检规则 | 3 轮 | 每轮对照清单自检 |
| 字数限制 | 7 处 | 今日一句话 ≤20 字、头条 150-200 字、总字数 800-2000... |

**直接后果**：LLM 将大部分"注意力"分配给了"避免违反约束"，而非"如何写出有洞察力的内容"。结果就是每篇日报都在"安全区"内——不犯错，但也不出彩。

### 3.2 agents.yaml 分析

**代码定位**: `crew/report_writing/config/agents.yaml`（79 行，~3000 字符）

Agent 的 backstory（~3000 字符）中包含大量与 tasks.yaml **重复的约束**：

- backstory 中的"禁止清单"与 tasks.yaml 的禁用词列表重复
- backstory 中的"自检环节"与 tasks.yaml 的 3 轮自检重复
- backstory 中的"格式要求"与 tasks.yaml 的 18 条硬约束重复

**直接后果**：LLM 在一次调用中接收了双倍的约束信息（backstory + task description），进一步挤压了创作空间。

---

## 4. TD-004: 无"编辑部"机制，单 Agent 全包

**严重度**: 🟡 中
**影响范围**: `crew/report_writing/crew.py`, `nodes.py:write_report_node`
**核心问题**: 一个 Agent 同时负责选题判断、角度选取、文案撰写、质量自检，违反了 Agent 分工原则

### 4.1 当前写作流程

```
write_report_node
  ↓
ReportWritingCrew.kickoff()
  ↓
单个 report_writer Agent
  ├── 自行决定今日信号强度（🔴/🟡/🟢）
  ├── 自行选择今日头条（从所有数据中选 1 条）
  ├── 自行确定写作角度（痛点/成本/规模/对比）
  ├── 自行撰写全部 7 个 Section
  ├── 自行执行 3 轮格式自检
  └── 输出最终 Markdown
```

**问题**：
1. **选题判断和文案撰写不应该是同一个 Agent**——选题需要"编辑视角"（什么对读者最有价值），撰写需要"作者视角"（如何把内容写得好看）
2. **质量自检不应该由作者自己做**——人类编辑部中，校对和审稿是分开的
3. **信号强度判断被挤在撰写流程中**——应该在写作前就确定，作为写作的输入参数

**直接后果**：
- 信号强度永远是 🟡（Agent 倾向保守选择中间值）
- 选题角度单一（没有"编辑会议"来讨论不同角度）
- 质量自检形同虚设（Agent 不会否定自己的输出）

### 4.2 与 CrewAI 最佳实践的偏差

项目规范中明确：
> "判断标准：如果一段逻辑需要'理解语义'或'做判断'，就应该交给 Agent"

当前 report_writer 同时做了 4 种不同类型的判断：
- 选题判断（编辑决策）
- 角度判断（策略决策）
- 文案创作（创意工作）
- 质量评估（审核工作）

应该拆分为至少 2-3 个 Agent/Crew。

---

## 5. TD-005: 无历史上下文利用

**严重度**: 🟡 中
**影响范围**: `crew/report_writing/tracker.py`, `crew/report_writing/config/tasks.yaml`
**核心问题**: 每次生成日报都是"从零开始"，没有跨日的风格记忆和话题连续性

### 5.1 上期追踪器的局限

**代码定位**: `crew/report_writing/tracker.py`（314 行）

当前 `PreviousReportTracker` 只追踪：
- 上期推荐项目的当前星数（星数变化）

**不追踪的内容**：

| 缺失维度 | 影响 |
|----------|------|
| 上期使用的写作角度 | 导致连续两天用同样的角度写同一个话题 |
| 上期覆盖的话题类别 | 导致 MCP 连续多天霸占头条 |
| 上期的"今日一句话" | 导致跨日雷同（3/27 和 3/31 几乎一样） |
| 写作风格偏好反馈 | 无法从历史中学习哪种风格更受欢迎 |
| 报告质量评分历史 | 无法追踪质量趋势 |

### 5.2 "今日一句话"雷同的证据

```
3/27: "MCP 生态快速扩张下，企业端工具集成方式正被重新定义"
3/30: (不同话题)
3/31: "MCP 生态正从概念验证快速走向工具链整合的关键节点"
```

3/27 和 3/31 的"今日一句话"本质上说的是同一件事——MCP 生态在发展。如果写作 Agent 能看到"上次已经说过 MCP 了"，就会选择不同的角度。

### 5.3 缺失的记忆系统

当前系统中没有任何持久化的跨日上下文文件：
- 无 `STYLE_MEMORY.md`（记录什么风格效果好）
- 无 `TOPIC_TRACKER.md`（记录最近覆盖的话题）
- 无 `KILL_LIST.md`（记录最近已报道的项目/新闻）

**直接后果**：每天的日报是独立生成的"信息孤岛"，缺乏连续性和进化能力。

---

## 6. 信息衰减全链路图

```
┌─────────────────────────────────────────────────────────┐
│                    信息密度衰减链路                        │
├────────────┬────────────────┬─────────────────────────────┤
│   阶段     │  信息密度       │  衰减原因                    │
├────────────┼────────────────┼─────────────────────────────┤
│ GitHub API │  ████████ 80%  │ 只取了星数+描述，丢了README  │
│ 新闻抓取   │  ██████ 60%    │ HN摘要为空，其他截断200字    │
│ 评分层     │  ████████ 80%  │ 生成了story_hook等叙事字段   │
│ JSON序列化 │  ████ 40%      │ 叙事字段被埋在JSON blob中    │
│ 写作层     │  ██ 20%        │ Prompt未引用叙事字段名       │
│ 最终日报   │  ███ 30%       │ LLM脑补填充信息空白         │
└────────────┴────────────────┴─────────────────────────────┘
```

**关键发现**：信息密度在"JSON 序列化"和"写作层接收"两个环节出现断崖式下降。这意味着即使数据源再丰富，如果不解决 TD-002（评分→写作的信息传递），改善效果也会有限。

---

## 7. 优先级与修复建议总结

| 编号 | 技术债务 | 严重度 | 修复阶段 | 预期收益 |
|------|---------|--------|---------|---------|
| TD-001 | 数据源过薄 | 🔴 高 | Phase 1（2 周） | 消除 LLM 虚构数据的根因 |
| TD-002 | 评分→写作信息断裂 | 🔴 高 | Phase 1（2 周） | 让评分层的叙事字段真正被利用 |
| TD-003 | Prompt 过度约束 | 🟡 中 | Phase 1（1 周） | 释放创作空间，减少模板感 |
| TD-004 | 无编辑部机制 | 🟡 中 | Phase 2（3 周） | 专业化分工提升决策质量 |
| TD-005 | 无历史上下文 | 🟡 中 | Phase 3（2 周） | 消除跨日雷同，建立连续性 |

> 详细的任务拆解和实施方案见 [improvement-tasks.md](./improvement-tasks.md)。

---

*本文档基于 2026-04-01 对 `src/ai_trending/` 全链路代码审查和近期日报质量评估生成。*
