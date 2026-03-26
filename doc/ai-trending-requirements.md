---
title: "AI Trending — 需求文档（代码逆向）"
generated_date: "2026-03-26"
source_code: "src/ai_trending/"
files_analyzed: 18
analyzer: "doc-code2req v5.0"
---

# AI Trending — 需求文档（代码逆向）

> 📄 本文档基于代码逆向推导生成，共分析 **18** 个核心源文件。
> 数据截至：2026-03-26 | 由 CodeBuddy doc-code2req 技能自动生成

---

## 1. 项目概览

### 1.1 系统定位

**AI Trending** 是一个 **AI Agent 驱动的 AI 日报自动生成系统**，核心目标：

1. 自动发现 GitHub 热点 AI 开源项目（CrewAI 关键词规划 + GitHub Search API）
2. 自动采集 AI 领域热点新闻（多源并发抓取：HN / Reddit / newsdata.io / 知乎）
3. 由 LLM 对数据进行结构化评分（TrendScoringCrew）
4. 由 LLM 生成七段式 Markdown 日报（ReportWritingCrew）
5. 自动发布到 GitHub 仓库 + 微信公众号草稿箱

### 1.2 技术栈

| 层次 | 技术 | 版本 |
|------|------|------|
| 流程编排 | LangGraph StateGraph | ≥1.1.3 |
| Agent 框架 | CrewAI | 1.11.0 |
| LLM 调用 | LiteLLM | ≥1.80.0 |
| HTTP 请求 | requests | ≥2.31.0 |
| 配置管理 | python-dotenv | ≥1.0.0 |
| Python 版本 | Python | 3.10 ~ 3.13 |

### 1.3 已分析文件清单

| 类型 | 文件 |
|------|------|
| 入口 | `main.py` |
| 编排层 | `graph.py`, `nodes.py` |
| 基础设施 | `config.py`, `llm_client.py`, `logger.py`, `retry.py`, `metrics.py` |
| GitHub Crew | `crew/github_trending/crew.py`, `models.py`, `utils.py` |
| 新闻 Crew | `crew/new_collect/crew.py`, `fetchers.py` |
| 评分 Crew | `crew/trend_scoring/crew.py`, `models.py` |
| 日报 Crew | `crew/report_writing/crew.py`, `models.py`, `tracker.py` |
| 工具层 | `tools/github_publish_tool.py`, `tools/wechat_publish_tool.py` |
| 配置文件 | `pyproject.toml` |

---

## 2. 系统架构

### 2.1 整体数据流

```mermaid
graph TD
    A[main.py: run] --> B[LangGraph StateGraph]
    B --> C[collect_github_node]
    B --> D[collect_news_node]
    C --> E[score_trends_node]
    D --> E
    E --> F[write_report_node]
    F --> G[publish_node]
    G --> H[GitHub 仓库]
    G --> I[微信公众号草稿箱]
    G --> J[本地 reports/ 目录]
```

### 2.2 节点并行关系

```mermaid
sequenceDiagram
    participant Main
    participant LangGraph
    participant GitHub采集
    participant 新闻采集
    participant 评分
    participant 日报撰写
    participant 发布

    Main->>LangGraph: invoke(initial_state)
    par 并行执行
        LangGraph->>GitHub采集: collect_github_node
        LangGraph->>新闻采集: collect_news_node
    end
    GitHub采集-->>LangGraph: github_data
    新闻采集-->>LangGraph: news_data
    LangGraph->>评分: score_trends_node
    评分-->>LangGraph: scoring_result (JSON)
    LangGraph->>日报撰写: write_report_node
    日报撰写-->>LangGraph: report_content (Markdown)
    LangGraph->>发布: publish_node
    发布-->>LangGraph: publish_results
```

---

## 3. 功能需求

### FR-001: 系统启动与初始化

**功能描述**：系统通过 `main.py` 启动，初始化 LangGraph 状态机并执行完整的日报生成流水线。

**调用链**：

```
main.py: run()
  ↓
graph.py: get_graph() → build_graph()
  ↓
LangGraph StateGraph.compile()
  ↓
graph.invoke(initial_state)
  ↓
[collect_github_node, collect_news_node] (并行)
  ↓
score_trends_node → write_report_node → publish_node
```

**API 接口**（命令行）：

```bash
# 方式 1: 直接运行（使用当天日期）
ai_trending

# 方式 2: 带 JSON payload 触发（用于外部调度）
run_with_trigger '{"current_date": "2026-03-26", "author_name": "AI Bot"}'
```

**初始状态字段**（`nodes.py: main.py:22-32`）：

```python
initial_state = {
    "current_date": "YYYY-MM-DD",   # 当天日期，自动生成
    "author_name": "AI Trending Bot",
    "github_data": "",
    "news_data": "",
    "scoring_result": "",
    "report_content": "",
    "publish_results": [],
    "token_usage": {},
    "errors": [],
}
```

**业务规则**：
- **BR-001**: `current_date` **必须**为 `YYYY-MM-DD` 格式，由 `datetime.now().strftime("%Y-%m-%d")` 自动生成（`main.py:17`）
- **BR-002**: 系统启动时**必须**检查 `OPENAI_API_KEY` 环境变量，缺失时**立即退出**（`config.py:validate_config`）
- **BR-003**: 缺少 `GITHUB_TRENDING_TOKEN` 时，系统**允许**继续运行，但 GitHub API 速率限制为 60 次/小时（`config.py:validate_config`）

---

### FR-002: GitHub 热点项目采集

**功能描述**：通过 `GitHubTrendingOrchestrator` 编排三步流程，发现最能代表 AI 发展趋势的 3-5 个 GitHub 开源项目。

**复杂度评估**：
- 调用链深度：5 层
- 涉及外部服务：1 个（GitHub Search API）
- 业务阶段：3 个（关键词规划 → 搜索采集 → 趋势排名）

**完整调用链**：

```mermaid
graph TD
    A[collect_github_node] --> B[GitHubTrendingTool._run]
    B --> C[GitHubTrendingOrchestrator.run_as_agent]
    C --> D[GitHubTrendingOrchestrator.run]
    D --> E[Step1: KeywordPlanningCrew.kickoff]
    D --> F[Step2: _programmatic_search]
    D --> G[Step3: TrendRankingCrew.kickoff]
    F --> H[GitHub Search API]
    F --> I[DedupCache 去重]
    G --> J[_merge_rankings]
```

**拆分为 3 个子步骤**：

#### 子步骤 1：关键词规划（`crew.py:_run_keyword_planning`）

**目标**：将用户主题（如 "AI"）扩展为 3-5 个 GitHub 可检索的关键词

**调用链**：
```
GitHubTrendingOrchestrator._run_keyword_planning (crew.py:100)
  ↓
KeywordPlanningCrew().crew().kickoff(inputs={"query": query, "current_date": date})
  ↓ (LLM: light 档)
GitHubSearchPlan.keywords: list[str]
```

**业务规则**：
- **BR-010**: 关键词数量**必须**在 1-5 个之间（`crew.py:_sanitize_keywords`）
- **BR-011**: 关键词**必须**可用于 GitHub 检索（`utils.py:is_searchable_keyword`）
- **BR-012**: KeywordPlanningCrew 失败时，**必须**使用兜底关键词映射表（`TREND_KEYWORD_MAP`），**不允许**直接失败（`crew.py:_default_keywords_for_query`）
- **BR-013**: 兜底关键词策略：`{"ai": ["AI agent", "MCP", "LLM inference"], ...}`（`utils.py:TREND_KEYWORD_MAP`）

#### 子步骤 2：程序化 GitHub 搜索（`crew.py:_programmatic_search`）

**目标**：根据关键词构建多维度搜索查询，调用 GitHub Search API，聚合候选仓库

**调用链**：
```
_programmatic_search (crew.py:_build_search_queries)
  ↓ 构建查询（每个关键词生成 4 条查询）
GitHub Search API: GET /search/repositories
  ↓ 聚合去重
DedupCache("github_repos", keep_days=30)
  ↓ 基础评分
_calculate_base_score → 预排序
```

**业务规则**：
- **BR-020**: 每个关键词**必须**生成 4 条搜索查询（topic/name+desc/readme/stars）（`crew.py:_build_search_queries`）
- **BR-021**: AI 相关查询时，**额外追加** 6 条固定热点查询（MCP/AI-agent/multimodal 等）（`crew.py:_build_search_queries`）
- **BR-022**: 候选仓库**必须**经过 30 天去重窗口过滤（`DedupCache("github_repos", keep_days=30)`）
- **BR-023**: 去重后全部重复时，**降级返回全量候选**，不返回空结果（`crew.py:_programmatic_search`）
- **BR-024**: 基础评分公式：`score = min(stars/2000, 4.0) + 活跃度(2.0) + 新创建(1.5) + 热点topic(1.8) + 命中次数(0.5*n, max 1.2)`，上限 10.0（`crew.py:_calculate_base_score`）
- **BR-025**: 候选仓库**最多**取前 15 个传入 TrendRankingCrew（`crew.py:_programmatic_search`）
- **BR-026**: GitHub API 速率限制剩余 ≤ 1 时，**必须**记录警告日志（`crew.py:_call_github_api`）

#### 子步骤 3：趋势排名（`crew.py:_run_trend_ranking`）

**目标**：由 LLM 对候选仓库进行趋势分析和重排行，输出最终 3-5 个项目

**调用链**：
```
TrendRankingCrew().crew().kickoff(inputs={query, date, count, candidates_json})
  ↓ (LLM: default 档)
GitHubTrendRanking.ranked_repos: list[RankedGitHubRepo]
  ↓
_merge_rankings → 合并 CrewAI 分 + 基础分
  ↓
_select_output_count → 决定输出 3-5 个
```

**业务规则**：
- **BR-030**: 最终评分公式：`final = crew_score * 0.75 + base_score * 0.25`，其中 `crew_score = trend*0.45 + innovation*0.25 + execution*0.15 + ecosystem*0.15`（`crew.py:_calculate_final_score`）
- **BR-031**: 非代表性项目（`representative=False`）**必须**扣减 1.5 分（`crew.py:_calculate_final_score`）
- **BR-032**: 输出数量决策规则：强项目（≥7.5分）≥ requested_count → 输出 requested_count；强项目 ≥ 3 → 输出强项目数；中等项目（≥6.5分）≥ 3 → 输出中等项目数；否则输出 min(available, 3)（`crew.py:_select_output_count`）
- **BR-033**: TrendRankingCrew 失败时，**降级使用基础分排序**，不阻断流程（`crew.py:_merge_rankings`）
- **BR-034**: 最终选中的项目**必须**标记到 DedupCache，防止下次重复输出（`crew.py:_merge_rankings`）

---

### FR-003: AI 新闻采集与筛选

**功能描述**：通过 `NewsCollectCrew` 并发抓取多源 AI 新闻，由 LLM Agent 筛选出最有价值的 AI 大模型相关新闻。

**复杂度评估**：
- 调用链深度：4 层
- 涉及外部数据源：4 个（HN / Reddit / newsdata.io / 知乎）
- 业务阶段：2 个（并发抓取 → LLM 筛选）

**完整调用链**：

```mermaid
graph TD
    A[collect_news_node] --> B[AINewsTool._run]
    B --> C[NewsCollectCrew.run]
    C --> D[NewsFetcher.fetch]
    D --> E[HN RSS]
    D --> F[Reddit API]
    D --> G[newsdata.io API]
    D --> H[知乎热榜]
    C --> I[NewsCollectCrew.crew.kickoff]
    I --> J[news_analyst Agent: LLM light档]
```

**业务规则**：
- **BR-040**: 默认关键词为 `["AI", "LLM", "AI Agent", "大模型"]`（`crew.py:NewsCollectCrew.__init__`）
- **BR-041**: 4 个数据源**必须**并发抓取（`ThreadPoolExecutor`），**禁止**串行等待（`fetchers.py`）
- **BR-042**: 每条新闻**必须**包含 `title / url / score / source / summary / time` 字段（`fetchers.py`）
- **BR-043**: 本次运行内**必须**按标题去重（`fetchers.py:_dedup_by_title`）
- **BR-044**: 跨日去重使用 `DedupCache("news_urls")`，全部重复时**降级返回全量**（`fetchers.py`）
- **BR-045**: LLM 筛选失败时，**降级直接返回格式化的原始抓取结果**（`crew.py:_format_fallback`）
- **BR-046**: 新闻 Agent 使用 `light` 档 LLM（`crew.py:news_analyst`）

---

### FR-004: 趋势结构化评分

**功能描述**：`TrendScoringCrew` 对 GitHub 项目和新闻数据进行多维度量化评分，输出结构化 JSON，为日报撰写提供排序依据。

**调用链**：

```
score_trends_node (nodes.py:score_trends_node)
  ↓
TrendScoringCrew().run(github_data, news_data, current_date)
  ↓
TrendScoringCrew.crew().kickoff(inputs={...})
  ↓ (LLM: default 档)
TrendScoringOutput (Pydantic)
  ↓
json.dumps(output.model_dump()) → scoring_result (str)
```

**输出数据模型**（`trend_scoring/models.py`）：

```python
TrendScoringOutput:
  scored_repos: list[ScoredRepo]   # 按综合评分降序
  scored_news:  list[ScoredNews]   # 按影响力评分降序
  daily_summary: DailySummary      # 今日趋势洞察汇总

ScoredRepo:
  repo, name, url, stars, language, is_ai, category
  scores: {热度, 技术前沿性, 成长潜力, 综合}  # 各 0-10 分
  one_line_reason, story_hook, technical_detail
  target_audience, scenario_description

ScoredNews:
  title, url, source, category
  impact_score: float (0-10)
  so_what_analysis, credibility_label
  time_window, affected_audience

DailySummary:
  top_trend, hot_directions (3-5个)
  overall_sentiment, causal_explanation
  data_support, forward_looking
```

**业务规则**：
- **BR-050**: 评分 Agent 使用 `default` 档 LLM（`crew.py:trend_scorer`）
- **BR-051**: 优先从 `result.pydantic` 获取输出，其次从 `tasks_output[-1].pydantic`，最后从 raw 文本 JSON 解析（`crew.py:run`）
- **BR-052**: 所有解析路径失败时，**必须**返回兜底空结果 `_FALLBACK_OUTPUT`，**不允许**抛出异常（`crew.py:run`）
- **BR-053**: 评分失败时，`score_trends_node` 返回预设兜底 JSON，确保下游 `write_report_node` 仍可运行（`nodes.py:score_trends_node`）

---

### FR-005: AI 日报撰写

**功能描述**：`ReportWritingCrew` 将评分数据、GitHub 数据、新闻数据和上期回顾数据整合为规范格式的七段式 Markdown 日报。

**复杂度评估**：
- 调用链深度：4 层
- 业务阶段：4 个（上期数据追踪 → LLM 撰写 → Markdown 格式修正 → 格式校验）

**完整调用链**：

```mermaid
graph TD
    A[write_report_node] --> B[PreviousReportTracker.get_previous_report_context]
    B --> C[查找上期报告文件]
    C --> D[解析推荐项目]
    D --> E[GitHub API 查询当前 Star 数]
    A --> F[ReportWritingCrew.run]
    F --> G[crew.kickoff: report_writer Agent]
    G --> H[LLM: default 档]
    F --> I[_fix_markdown_spacing]
    F --> J[_validate_report: 18项校验]
    A --> K[保存到 reports/YYYY-MM-DD.md]
```

**拆分为 4 个子步骤**：

#### 子步骤 1：上期回顾数据追踪（`tracker.py:PreviousReportTracker`）

**目标**：从历史报告中提取推荐项目，查询当前 Star 数，生成真实追踪数据

**调用链**：
```
PreviousReportTracker.get_previous_report_context(current_date)
  ↓
_find_previous_report → 向前查找最多 14 天
  ↓
_parse_recommended_repos → 正则解析 GitHub 项目 + 上期 Star 数
  ↓
_fetch_current_stars → GitHub API: GET /repos/{owner}/{repo}
  ↓
_format_context → 生成结构化上下文字符串
```

**业务规则**：
- **BR-060**: 上期回顾数据**必须**来自真实 GitHub API 查询，**禁止** LLM 虚构（`tracker.py`）
- **BR-061**: 向前查找历史报告**最多** 14 天（`tracker.py:_MAX_LOOKBACK_DAYS = 14`）
- **BR-062**: 每次**最多**追踪 4 个项目（`tracker.py:_MAX_TRACK_REPOS = 4`）
- **BR-063**: 追踪失败时**必须**返回空字符串，**不允许**阻断主流程（`tracker.py:get_previous_report_context`）
- **BR-064**: 趋势判断规则：增长 > 500 → "增长强劲"；100-500 → "稳定增长"；0-100 → "增长放缓"；< 0 → "星数下降"（`tracker.py:_format_context`）

#### 子步骤 2：LLM 日报撰写（`crew.py:ReportWritingCrew`）

**目标**：由 LLM 基于所有输入数据撰写七段式 Markdown 日报

**调用链**：
```
ReportWritingCrew.crew().kickoff(inputs={
    github_data, news_data, scoring_result,
    current_date, previous_report_context
})
  ↓ (LLM: default 档)
ReportOutput.content: str (Markdown)
```

**业务规则**：
- **BR-070**: 日报**必须**包含七段式结构：标题行、今日头条、GitHub 热点项目、AI 热点新闻、趋势洞察、本周行动建议、上期回顾（可选）（`crew.py:_REQUIRED_SECTIONS`）
- **BR-071**: 无上期数据时，`previous_report_context` 注入 `"（无上期数据，请省略「上期回顾」Section）"`（`crew.py:run`）
- **BR-072**: 日报撰写 Agent 使用 `default` 档 LLM（`crew.py:report_writer`）

#### 子步骤 3：Markdown 格式修正（`crew.py:_fix_markdown_spacing`）

**目标**：修正 LLM 常见的 Markdown 格式问题（标题前缺空行、新闻三行被压缩等）

**业务规则**：
- **BR-080**: 新闻条目（`**[类别]** 标题 > 判断 来源：xxx`）被压缩为一行时，**必须**自动拆分为 3 行（`crew.py:_fix_news_item_lines`）
- **BR-081**: GitHub 项目字段（类别/语言/趋势信号）被压缩为一行时，**必须**自动拆分（`crew.py:_fix_github_item_fields`）
- **BR-082**: `##` 标题前**必须**有 2 个空行，`###` 标题前**必须**有 1 个空行（`crew.py:_fix_markdown_spacing`）

#### 子步骤 4：格式校验（`crew.py:_validate_report`）

**目标**：对生成的日报进行 18 项格式校验，记录问题但不阻断发布

**业务规则**（18 项校验）：
- **BR-090**: 五个必要 Section **必须**全部存在（`_REQUIRED_SECTIONS`）
- **BR-091**: 今日信号强度**必须**三选一：🔴 重大变化日 / 🟡 常规更新日 / 🟢 平静日
- **BR-092**: 新闻可信度标签**必须**使用：🟢 一手信源 / 🟡 社区讨论 / 🔴 待验证
- **BR-093**: **必须**包含 `**[今日一句话]**` 标记
- **BR-094**: **必须**包含 So What 分析关键词
- **BR-095**: **必须**包含本周行动建议（本周作业 / 讨论问题）
- **BR-096**: GitHub 项目星数**必须**包含本周增长信息（格式：`（+数字）`）
- **BR-097**: 今日头条**必须**包含信息差悬念、技术细节支撑、谁应该关注三个叙事元素
- **BR-098**: 趋势洞察**必须**包含数据或对比支撑
- **BR-099**: **必须**包含互动引导（欢迎分享 / 评论区 / 参与方式）
- **BR-100**: 上期回顾（如有）**必须**包含星数追踪和趋势验证
- **BR-101**: **必须**包含叙事风格元素（实测/增速是/发布仅/如果你在做等）
- **BR-102**: 日报总字数**必须**在 800-2000 字之间
- **BR-103**: 禁用词列表（重磅/震撼/颠覆/革命性等 20+ 个词）**一律禁止**出现
- **BR-104**: Emoji 密度**不得超过** 3 个/100 字
- **BR-105**: 行动建议**应当**包含时效性理由（为什么是这周）
- **BR-106**: **禁止**使用「相当于……的……版」句式
- **BR-107**: 格式校验问题**只记录**到 `validation_issues`，**不阻断**发布流程

---

### FR-006: 多渠道发布

**功能描述**：`publish_node` 将生成的日报并行发布到 GitHub 仓库和微信公众号草稿箱，各渠道独立容错。

**完整调用链**：

```mermaid
graph TD
    A[publish_node] --> B{report_content 是否有效?}
    B -->|无效| C[返回: 跳过发布]
    B -->|有效| D[GitHubPublishTool._run]
    B -->|有效| E[WeChatPublishTool._run]
    D --> F{GITHUB_TOKEN 是否配置?}
    F -->|否| G[_save_locally: 保存本地]
    F -->|是| H[GitHub API: PUT /repos/.../contents/...]
    E --> I{WECHAT_APP_ID 是否配置?}
    I -->|否| J[跳过微信发布]
    I -->|是| K[获取 access_token]
    K --> L[Markdown → 微信 HTML]
    L --> M[微信草稿 API: POST /draft/add]
```

**业务规则**：
- **BR-110**: 发布层**只做搬运**，**禁止**对 `report_content` 做任何 LLM 润色或内容修改（`nodes.py:publish_node`）
- **BR-111**: 单个渠道失败**不允许**影响其他渠道继续执行（`nodes.py:publish_node`）
- **BR-112**: `report_content` 为空或包含"报告生成失败"时，**必须**跳过所有发布（`nodes.py:publish_node`）
- **BR-113**: GitHub 发布时，文件路径**必须**为 `reports/{YYYY-MM-DD}.md`（`github_publish_tool.py`）
- **BR-114**: GitHub 文件已存在时，**必须**先获取 `sha` 再更新，**禁止**直接覆盖（`github_publish_tool.py`）
- **BR-115**: GitHub Token 未配置时，**降级保存到本地** `reports/` 目录（`github_publish_tool.py:_save_locally`）
- **BR-116**: 微信 `access_token` 有效期 7200 秒，**必须**自动刷新（`wechat_publish_tool.py`）
- **BR-117**: 微信 HTML **必须**使用内联 `style` 属性，**禁止**外链 CSS（`wechat_publish_tool.py`）
- **BR-118**: 微信发布成功后返回草稿 `media_id`，**需要**人工在公众号后台审核发布（`wechat_publish_tool.py`）

---

## 4. 数据需求

### 4.1 全局状态模型（TrendingState）

**代码位置**：`graph.py:TrendingState`

| 字段 | 类型 | 写入节点 | 读取节点 | 说明 |
|------|------|---------|---------|------|
| `current_date` | `str` | main.py | 所有节点 | 报告日期 YYYY-MM-DD |
| `author_name` | `str` | main.py | publish_node | 作者名称 |
| `github_data` | `str` | collect_github | score_trends, write_report | GitHub 热点项目文本 |
| `news_data` | `str` | collect_news | score_trends, write_report | 行业新闻文本 |
| `scoring_result` | `str` | score_trends | write_report | 结构化 JSON 评分 |
| `report_content` | `str` | write_report | publish | 最终 Markdown 报告 |
| `publish_results` | `Annotated[list[str], operator.add]` | publish | — | 发布结果（追加模式） |
| `token_usage` | `dict` | — | — | 累计 Token 用量 |
| `errors` | `Annotated[list[str], operator.add]` | 任意节点 | — | 错误记录（追加模式） |

### 4.2 评分数据模型

**代码位置**：`crew/trend_scoring/models.py`

```mermaid
erDiagram
    TrendScoringOutput ||--o{ ScoredRepo : scored_repos
    TrendScoringOutput ||--o{ ScoredNews : scored_news
    TrendScoringOutput ||--|| DailySummary : daily_summary

    ScoredRepo {
        str repo
        str name
        str url
        int stars
        str language
        bool is_ai
        str category
        dict scores
        str one_line_reason
        str story_hook
        str technical_detail
        str target_audience
    }

    ScoredNews {
        str title
        str url
        str source
        str category
        float impact_score
        str so_what_analysis
        str credibility_label
        str time_window
        str affected_audience
    }

    DailySummary {
        str top_trend
        list hot_directions
        str overall_sentiment
        str causal_explanation
        str data_support
        str forward_looking
    }
```

### 4.3 日报输出模型

**代码位置**：`crew/report_writing/models.py`

| 字段 | 类型 | 说明 |
|------|------|------|
| `content` | `str` | 完整 Markdown 日报，七段式结构，800-2000 字 |
| `validation_issues` | `list[str]` | 格式校验问题列表，空列表表示通过 |

### 4.4 配置数据模型

**代码位置**：`config.py`

| 配置项 | 环境变量 | 必填 | 默认值 | 说明 |
|--------|---------|------|--------|------|
| LLM 模型 | `MODEL` | ✅ | `openai/gpt-4o` | 主力模型（default 档） |
| LLM API Key | `OPENAI_API_KEY` | ✅ | — | LLM 调用密钥 |
| LLM API Base | `OPENAI_API_BASE` | ❌ | 默认 | 自定义 API 端点 |
| 轻量模型 | `MODEL_LIGHT` | ❌ | 回退到 MODEL | 轻量任务模型（light 档） |
| 工具模型 | `MODEL_TOOL` | ❌ | 回退到 MODEL_LIGHT | 工具调用模型 |
| LLM 温度 | `LLM_TEMPERATURE` | ❌ | `0.1` | 生产环境推荐低温度 |
| GitHub Token | `GITHUB_TRENDING_TOKEN` | ❌ | — | GitHub API 认证 |
| GitHub 仓库 | `GITHUB_REPORT_REPO` | ❌ | — | 报告推送目标仓库 |
| 新闻 API Key | `NEWSDATA_API_KEY` | ❌ | — | newsdata.io API 密钥 |
| 微信 AppID | `WECHAT_APP_ID` | ❌ | — | 微信公众号 AppID |
| 微信 AppSecret | `WECHAT_APP_SECRET` | ❌ | — | 微信公众号 AppSecret |
| 微信封面图 | `WECHAT_THUMB_MEDIA_ID` | ❌ | — | 封面图素材 ID |

---

## 5. 业务规则汇总

### 5.1 LLM 模型档位规则

| 档位 | 环境变量 | 适用场景 | 代码位置 |
|------|---------|---------|---------|
| `light` | `MODEL_LIGHT` | 关键词规划、新闻筛选、工具调用型 Agent | `keyword_planning/crew.py`, `new_collect/crew.py` |
| `default` | `MODEL` | 趋势分析、评分、日报撰写 | `trend_ranking/crew.py`, `trend_scoring/crew.py`, `report_writing/crew.py` |

**BR-120**: `tool_only` 档位**不存在**，纯工具调用型 Agent **必须**使用 `light` 档（项目规则）
**BR-121**: 所有 CrewAI Agent **必须**通过 `build_crewai_llm(tier)` 工厂函数获取 LLM，**禁止**直接实例化 `ChatOpenAI`（`llm_client.py`）

### 5.2 错误处理规则

| 错误级别 | 场景 | 处理方式 |
|---------|------|---------|
| L1（可忽略） | 单条仓库/新闻解析失败 | `log.warning`，跳过该条，继续处理 |
| L2（可降级） | Crew 调用失败、API 限流 | `log.error`，使用兜底值，追加到 `errors` |
| L3（致命） | LLM API Key 无效 | `log.critical`，追加到 `errors`，节点返回空 |

**BR-130**: 所有节点**必须**捕获所有异常，**禁止**让异常向上传播导致图执行中断（`nodes.py`）
**BR-131**: `errors` 字段格式**必须**为 `"{节点名}: {错误描述}"`（`nodes.py`）
**BR-132**: 兜底返回值类型**必须**与正常返回值类型一致（`nodes.py`）

### 5.3 日报内容规则

**BR-140**: 日报**必须**为七段式结构（见 FR-005）
**BR-141**: 禁用词（20+ 个）**一律禁止**出现，包括：重磅、震撼、颠覆、革命性、划时代、里程碑、历史性、强烈推荐、必看、不容错过、太强了、绝了、牛逼、未来已来、新时代、感叹号（！/!）、重新定义、拓展新边界、具有重要意义、相当于、综合评分、趋势代表性满分
**BR-142**: 日报总字数**必须**在 800-2000 字之间
**BR-143**: 「上期回顾」星数数据**必须**来自 `PreviousReportTracker` 真实查询，**禁止** LLM 虚构
**BR-144**: 无历史数据时，「上期回顾」Section **必须**省略，**禁止**输出占位符

---

## 6. 非功能需求

### NFR-001: 性能要求

**代码实现**：
- 并行采集：`graph.py` 中 `collect_github` 和 `collect_news` 并行执行（`graph.add_edge(START, "collect_github")` + `graph.add_edge(START, "collect_news")`）
- 并发抓取：`NewsFetcher` 使用 `ThreadPoolExecutor` 并发抓取 4 个数据源（`fetchers.py`）
- 去重缓存：`DedupCache` 本地文件缓存，避免重复处理（`crew/util/dedup_cache.py`）

**性能指标**：
- GitHub 搜索 API 超时：30 秒，重试 3 次（`crew.py:_call_github_api`）
- 新闻抓取超时：15-20 秒，重试 2 次（`fetchers.py`）
- GitHub API 速率限制：无 Token 时 60 次/小时，有 Token 时 5000 次/小时

### NFR-002: 安全要求

**代码实现**：
- API Key 统一从环境变量读取，**禁止**硬编码（`config.py`）
- GitHub Token 通过 `Authorization: Bearer {token}` 传递（`github_publish_tool.py`）
- 微信 AppSecret 不在日志中输出（`config.py`）

**安全标准**：
- 所有 API Key **必须**通过 `.env` 文件配置，**禁止**提交到代码仓库
- `.env` 文件**必须**在 `.gitignore` 中排除

### NFR-003: 可靠性要求

**代码实现**：
- 重试机制：`retry.py:safe_request` 提供统一的重试和超时处理
- 兜底策略：每个 Crew 都有兜底降级路径（见各 FR 的业务规则）
- 错误收集：`TrendingState.errors` 字段收集所有 L2/L3 错误
- 日志记录：`logger.py` 提供统一的结构化日志

**可靠性指标**：
- 任意单个 Crew 失败**不允许**导致整个流水线中断
- 任意单个发布渠道失败**不允许**影响其他渠道
- 报告**必须**保存到本地 `reports/` 目录（即使 GitHub 发布失败）

### NFR-004: 可维护性要求

**代码实现**：
- 分层架构：LangGraph（编排）→ CrewAI（Agent）→ Tool（工具）→ Fetcher（采集）
- 单一职责：每个节点只读取/写入自己负责的 State 字段
- 配置驱动：所有模型名称、API Key 通过环境变量配置
- 测试覆盖：`tests/unit/` 目录下有对应单元测试，使用 mock 避免真实 LLM 调用

---

## 7. 代码位置索引

### 7.1 功能模块索引

| 功能模块 | 入口文件 | 核心实现 |
|---------|---------|---------|
| 系统启动 | `main.py:run` | `graph.py:build_graph` |
| GitHub 采集 | `nodes.py:collect_github_node` | `crew/github_trending/crew.py:GitHubTrendingOrchestrator` |
| 新闻采集 | `nodes.py:collect_news_node` | `crew/new_collect/crew.py:NewsCollectCrew` |
| 趋势评分 | `nodes.py:score_trends_node` | `crew/trend_scoring/crew.py:TrendScoringCrew` |
| 日报撰写 | `nodes.py:write_report_node` | `crew/report_writing/crew.py:ReportWritingCrew` |
| 上期追踪 | `nodes.py:write_report_node` | `crew/report_writing/tracker.py:PreviousReportTracker` |
| GitHub 发布 | `nodes.py:publish_node` | `tools/github_publish_tool.py:GitHubPublishTool` |
| 微信发布 | `nodes.py:publish_node` | `tools/wechat_publish_tool.py:WeChatPublishTool` |

### 7.2 关键配置索引

| 配置项 | 文件 | 作用 |
|--------|------|------|
| LangGraph 状态 | `graph.py:TrendingState` | 全局状态字段定义 |
| LLM 三档配置 | `config.py:LLMConfig` | 模型档位和 API 配置 |
| 禁用词列表 | `crew/report_writing/crew.py:_BANNED_WORDS` | 日报内容约束 |
| 必要 Section | `crew/report_writing/crew.py:_REQUIRED_SECTIONS` | 日报结构约束 |
| 关键词映射 | `crew/github_trending/utils.py:TREND_KEYWORD_MAP` | 兜底关键词策略 |
| 去重缓存 | `crew/util/dedup_cache.py:DedupCache` | 跨日去重机制 |

---

## 8. 技术债务与改进建议

### 8.1 已识别问题

1. **`_fix_markdown_spacing` 复杂度过高**
   - 代码位置：`crew/report_writing/crew.py:_fix_markdown_spacing`（约 100 行）
   - 影响：维护困难，LLM 输出格式变化时需要频繁修改
   - 建议：将 Markdown 格式修正逻辑下沉到 `tasks.yaml` 的 Prompt 约束中，减少后处理代码

2. **`GitHubTrendingOrchestrator` 职责过重**
   - 代码位置：`crew/github_trending/crew.py`（754 行）
   - 影响：单文件过大，关键词规划/搜索/排名三个职责混在一起
   - 建议：将 `_programmatic_search` 相关方法提取到独立的 `GitHubSearcher` 类

3. **`publish_node` 串行发布**
   - 代码位置：`nodes.py:publish_node`（串行调用 GitHub + 微信）
   - 影响：发布耗时 = GitHub 耗时 + 微信耗时
   - 建议：使用 `ThreadPoolExecutor` 并发发布，符合项目规范文档的要求

4. **`wechat_publish_tool.py` 体积过大**
   - 代码位置：`tools/wechat_publish_tool.py`（22KB）
   - 影响：Markdown → 微信 HTML 转换逻辑复杂，难以测试
   - 建议：将 HTML 转换逻辑提取到独立的 `wechat_html_converter.py` 模块

### 8.2 最佳实践建议

1. **增加 `score_trends_node` → `write_report_node` 的条件分支**：当 `scoring_result` 为空时，跳过日报撰写，避免生成低质量报告
2. **`DedupCache` 持久化策略**：当前使用本地文件，建议在多实例部署时改为 Redis
3. **Token 用量追踪**：`TrendingState.token_usage` 字段已定义但未实际写入，建议在各 Crew 中补充 Token 统计

---

## 9. 附录

### 9.1 分析统计

| 指标 | 数量 |
|------|------|
| 分析文件数 | 18 个 |
| 功能需求（FR） | 6 个 |
| 业务规则（BR） | 144 条 |
| 非功能需求（NFR） | 4 个 |
| LangGraph 节点 | 5 个 |
| CrewAI Crew | 4 个 |
| 发布渠道 | 2 个 |

### 9.2 日报七段式结构速查

```markdown
# AI 日报 · YYYY-MM-DD
**[今日信号强度]** 🔴/🟡/🟢
> **[今日一句话]** {判断句，≤20字}

## 今日头条          → 1条深度解读，150-200字
## GitHub 热点项目   → 2-4个项目，含星数增长
## AI 热点新闻       → 4-6条，严格3行格式，含可信度标签+So What
## 趋势洞察          → 3-5条，含数据支撑
## 本周行动建议      → 1-2条可落地任务，含时效理由
## 上期回顾          → 可选，有历史数据时包含

*数据截至：YYYY-MM-DD | 由 AI Agent 自动生成*
```
