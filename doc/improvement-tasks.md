# AI Trending — 日报质量改进任务清单

> 📅 创建日期：2026-04-01
> 📎 关联文档：[tech-debt-analysis.md](./tech-debt-analysis.md) | [ai-trending-requirements.md](./ai-trending-requirements.md)
> 🏷️ 任务状态：⬜ 待开始 | 🔄 进行中 | ✅ 已完成 | ⏸️ 暂缓
> 🎯 目标：系统性提升日报信息密度和阅读体验

---

## 任务总览

三阶段优化，每阶段聚焦不同层次的改进：

| 阶段 | 主题 | 核心收益 | 预估工时 | 关联 TD |
|------|------|---------|---------|---------|
| **Phase 1** | 数据增厚 + 信息传递优化 | 消除 LLM 虚构，激活评分叙事字段 | 32h | TD-001, TD-002, TD-003 |
| **Phase 2** | Agent 协作重构 | 专业化分工，提升选题和质量 | 24h | TD-004 |
| **Phase 3** | 记忆系统建设 | 消除跨日雷同，建立连续性 | 12h | TD-005 |

**总预估工时：68 小时（约 3-4 周全力投入）**

---

## Phase 1：数据增厚 + 信息传递优化（2 周）

> 目标：让写作层拥有足够的信息密度，不再需要 LLM 虚构细节

---

### TASK-001: GitHub 数据增厚 — README 摘要

**优先级**: 🔴 P1
**预估工时**: 6h
**关联 TD**: TD-001
**状态**: ✅ 已完成（2026-04-01）

#### 目标

在 `GitHubFetcher` 中增加 README 内容抓取，提供项目"到底做什么"的关键信息。

#### 涉及文件

| 文件 | 改动类型 | 说明 |
|------|---------|------|
| `crew/github_trending/fetchers.py` | 修改 | 新增 `_fetch_readme_summary()` 方法 |
| `crew/github_trending/models.py` | 修改 | `RepoCandidate` 新增 `readme_summary` 字段 |
| `tests/unit/crew/test_github_trending.py` | 修改 | 新增 README 抓取测试 |

#### 实施方案

1. **新增 GitHub README API 调用**

   ```python
   # fetchers.py — 新增方法
   def _fetch_readme_summary(self, full_name: str) -> str:
       """获取仓库 README 的前 500 字符摘要。"""
       resp = safe_request(
           "GET",
           f"https://api.github.com/repos/{full_name}/readme",
           headers={"Accept": "application/vnd.github.raw+json"},
           timeout=10,
           max_retries=1,
           operation_name=f"readme({full_name})",
       )
       if resp is None:
           return ""
       content = resp.text[:2000]  # 限制读取量
       # 提取前 500 字符的有效内容（去除badge、链接等）
       return self._clean_readme(content)[:500]
   ```

2. **并发抓取 README**（在候选仓库确定后，对 top-15 并发抓取）

   ```python
   # 在 _programmatic_search 返回候选后
   with ThreadPoolExecutor(max_workers=5) as executor:
       futures = {
           executor.submit(self._fetch_readme_summary, repo.full_name): repo
           for repo in candidates[:15]
       }
       for future in as_completed(futures, timeout=30):
           repo = futures[future]
           try:
               repo.readme_summary = future.result()
           except Exception:
               repo.readme_summary = ""
   ```

3. **更新 `RepoCandidate` 模型**

   ```python
   class RepoCandidate(BaseModel):
       # ... 现有字段 ...
       readme_summary: str = Field(default="", description="README 前 500 字符摘要")
   ```

#### API 速率影响评估

- 每次运行额外消耗：~15 次 README API 调用
- 有 Token 时速率限制：5000 次/小时 → 影响可忽略
- 无 Token 时速率限制：60 次/小时 → 需控制在总调用数的 25% 以内

#### 验收标准

- [x] `RepoCandidate` 中 `readme_summary` 字段非空率 ≥ 80%
- [x] README 摘要已去除 badge 图片、链接标记等噪音
- [x] 单次 README 抓取超时不阻塞其他仓库的抓取
- [x] 单元测试覆盖：README 返回正常、返回 404、超时 三种场景

---

### TASK-002: GitHub 数据增厚 — 星数增长趋势

**优先级**: 🔴 P1
**预估工时**: 4h
**关联 TD**: TD-001
**状态**: ✅ 已完成（2026-04-01）

#### 目标

提供仓库近 7 天的星数增长数据，让写作层能使用"发布仅 1 周星数增长 2000+"这样的真实描述。

#### 方案选择

| 方案 | 实现 | 优缺点 |
|------|------|--------|
| A. 调用星数历史 API | GitHub Stars History 不是官方 API | ❌ 依赖第三方，不稳定 |
| **B. 本地持久化星数快照** | 每日运行时记录星数到本地文件 | ✅ 简单可靠，7 天后有完整趋势 |
| C. 调用 Stargazers API 分页 | `GET /repos/{owner}/{repo}/stargazers` | ❌ 大仓库分页代价高 |

**推荐方案 B**：在 `output/star_snapshots/` 目录中记录每日星数快照。

#### 涉及文件

| 文件 | 改动类型 | 说明 |
|------|---------|------|
| `crew/github_trending/star_tracker.py` | 新建 | 星数快照持久化和增长计算 |
| `crew/github_trending/fetchers.py` | 修改 | 搜索完成后调用 star_tracker 记录快照 |
| `crew/github_trending/models.py` | 修改 | `RepoCandidate` 新增 `stars_7d_ago`, `stars_growth_7d` |

#### 实施方案

```python
# star_tracker.py — 核心逻辑
class StarTracker:
    """本地星数快照追踪器。"""
    
    SNAPSHOT_DIR = Path("output/star_snapshots")
    
    def record_snapshot(self, repos: list[RepoCandidate], date: str) -> None:
        """记录当日星数快照。"""
        snapshot = {repo.full_name: repo.stars for repo in repos}
        path = self.SNAPSHOT_DIR / f"{date}.json"
        path.write_text(json.dumps(snapshot, indent=2))
    
    def get_growth(self, full_name: str, current_stars: int, days: int = 7) -> int | None:
        """计算 N 天增长量，无历史数据时返回 None。"""
        target_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        snapshot_path = self.SNAPSHOT_DIR / f"{target_date}.json"
        if not snapshot_path.exists():
            return None
        historical = json.loads(snapshot_path.read_text())
        prev_stars = historical.get(full_name)
        if prev_stars is None:
            return None
        return current_stars - prev_stars
```

#### 验收标准

- [x] 每次运行后 `output/star_snapshots/{date}.json` 文件被创建
- [x] 运行 7 天后，`stars_growth_7d` 字段开始产出真实增长数据
- [x] 无历史数据时 `stars_growth_7d = None`，不影响后续流程
- [x] 快照文件超过 30 天自动清理

---

### TASK-003: 新闻数据增厚 — 正文摘要提取

**优先级**: 🔴 P1
**预估工时**: 6h
**关联 TD**: TD-001
**状态**: ✅ 已完成（2026-04-01）

#### 目标

对新闻链接做正文提取，获取前 300 字符的正文内容，特别解决 HN 摘要永远为空的问题。

#### 涉及文件

| 文件 | 改动类型 | 说明 |
|------|---------|------|
| `crew/new_collect/fetchers.py` | 修改 | 新增 `_extract_article_content()` 方法 |
| `crew/new_collect/content_extractor.py` | 新建 | 正文提取工具（基于 `readability-lxml` 或 `trafilatura`） |
| `pyproject.toml` | 修改 | 新增依赖 `trafilatura` |

#### 实施方案

```python
# content_extractor.py — 正文提取器
import trafilatura

def extract_article_content(url: str, max_chars: int = 500) -> str:
    """从 URL 提取正文内容的前 N 个字符。
    
    使用 trafilatura 库，支持大多数新闻网站的正文提取。
    失败时返回空字符串，不抛出异常。
    """
    try:
        downloaded = trafilatura.fetch_url(url)
        if not downloaded:
            return ""
        text = trafilatura.extract(downloaded, include_comments=False)
        if not text:
            return ""
        return text[:max_chars].strip()
    except Exception:
        return ""
```

```python
# fetchers.py — 在 fetch() 的去重之后、返回之前，对 summary 为空的条目补充正文
def _enrich_empty_summaries(self, items: list[dict]) -> list[dict]:
    """对 summary 为空的新闻条目，尝试提取正文摘要。"""
    empty_items = [item for item in items if not item.get("summary")]
    if not empty_items:
        return items
    
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = {
            executor.submit(extract_article_content, item["url"]): item
            for item in empty_items[:10]  # 最多补充 10 条
        }
        for future in as_completed(futures, timeout=30):
            item = futures[future]
            try:
                item["summary"] = future.result()
            except Exception:
                pass
    
    return items
```

#### 性能与安全约束

- 正文提取最多处理 10 条（避免过多 HTTP 请求）
- 单条提取超时 10 秒
- 全部提取超时 30 秒
- 不提取需要登录的网站内容

#### 验收标准

- [x] HN 新闻的 summary 非空率从 0% 提升到 ≥ 60%
- [x] 正文提取失败不影响原有数据（保持空字符串）
- [x] 新增依赖 `trafilatura` 已添加到 `pyproject.toml`
- [x] 单元测试覆盖：正常提取、超时、URL 无效 三种场景

---

### TASK-004: 评分→写作 信息传递优化 — Writing Brief

**优先级**: 🔴 P1
**预估工时**: 8h
**关联 TD**: TD-002
**状态**: ✅ 已完成（2026-04-01）

#### 目标

在评分 JSON 和写作 Prompt 之间引入"Writing Brief"中间格式，将评分层的叙事字段显式传递给写作层。

#### 核心思路

```
当前链路:
  TrendScoringOutput → json.dumps() → 巨大JSON字符串 → 写作Prompt

改进链路:
  TrendScoringOutput → WritingBrief (结构化中间格式) → 写作Prompt
```

#### 涉及文件

| 文件 | 改动类型 | 说明 |
|------|---------|------|
| `crew/report_writing/models.py` | 修改 | 新增 `WritingBrief` 模型 |
| `nodes.py:write_report_node` | 修改 | 构建 WritingBrief 替代原始 JSON |
| `crew/report_writing/config/tasks.yaml` | 修改 | Prompt 显式引用 Brief 字段 |

#### WritingBrief 模型设计

```python
# crew/report_writing/models.py — 新增
class WritingBrief(BaseModel):
    """写作简报 — 评分层→写作层的结构化信息传递。"""
    
    # 编辑决策输入
    signal_strength_suggestion: str = Field(
        description="建议的信号强度：'red'/'yellow'/'green'，基于今日数据重要性"
    )
    headline_candidate: str = Field(
        description="建议的今日头条项目/新闻名称"
    )
    headline_story_hook: str = Field(
        description="头条的故事钩子（来自评分层 story_hook）"
    )
    
    # GitHub 项目简报
    top_repos: list[RepoBrief] = Field(default_factory=list)
    
    # 新闻简报
    top_news: list[NewsBrief] = Field(default_factory=list)
    
    # 趋势判断
    trend_summary: str = Field(
        description="今日趋势总结（来自评分层 DailySummary）"
    )
    causal_explanation: str = Field(
        description="因果解释（来自评分层 DailySummary）"
    )


class RepoBrief(BaseModel):
    """单个仓库的写作简报。"""
    name: str
    url: str
    stars: int
    stars_growth_7d: int | None = None
    language: str
    readme_summary: str = ""          # 来自 TASK-001
    story_hook: str = ""              # 来自评分层
    technical_detail: str = ""        # 来自评分层
    target_audience: str = ""         # 来自评分层
    suggested_angle: str = ""         # 建议切入角度
    one_line_reason: str = ""         # 入选理由


class NewsBrief(BaseModel):
    """单条新闻的写作简报。"""
    title: str
    url: str
    source: str
    content_excerpt: str = ""         # 来自 TASK-003
    so_what_analysis: str = ""        # 来自评分层
    credibility_label: str = ""       # 来自评分层
    category: str = ""
```

#### 节点层构建 Brief 逻辑

```python
# nodes.py — write_report_node 中
def _build_writing_brief(scoring_output: TrendScoringOutput, 
                          github_data: str, 
                          news_data: str) -> WritingBrief:
    """从评分输出构建写作简报，显式传递叙事字段。"""
    brief = WritingBrief(
        signal_strength_suggestion=_decide_signal_strength(scoring_output),
        headline_candidate=scoring_output.scored_repos[0].name if scoring_output.scored_repos else "",
        headline_story_hook=scoring_output.scored_repos[0].story_hook if scoring_output.scored_repos else "",
        top_repos=[
            RepoBrief(
                name=repo.name,
                url=repo.url,
                stars=repo.stars,
                story_hook=repo.story_hook,
                technical_detail=repo.technical_detail,
                target_audience=repo.target_audience,
                one_line_reason=repo.one_line_reason,
            )
            for repo in scoring_output.scored_repos[:5]
        ],
        top_news=[
            NewsBrief(
                title=news.title,
                url=news.url,
                source=news.source,
                so_what_analysis=news.so_what_analysis,
                credibility_label=news.credibility_label,
                category=news.category,
            )
            for news in scoring_output.scored_news[:8]
        ],
        trend_summary=scoring_output.daily_summary.top_trend,
        causal_explanation=scoring_output.daily_summary.causal_explanation,
    )
    return brief
```

#### tasks.yaml Prompt 改造

```yaml
# 改造前：
# "评分数据: {scoring_result}"  ← 巨大 JSON blob

# 改造后：显式引用 Brief 字段
write_report:
  description: >
    ## 写作简报

    **今日信号强度建议**: {signal_strength_suggestion}
    **建议头条**: {headline_candidate}
    **头条故事钩子**: {headline_story_hook}

    ### 推荐 GitHub 项目
    {top_repos_formatted}
    每个项目已提供：story_hook（开篇钩子）、technical_detail（技术亮点）、
    target_audience（目标读者）。请直接使用这些素材，不要重新编造。

    ### 推荐新闻
    {top_news_formatted}
    每条新闻已提供：so_what_analysis（深层分析）、credibility_label（可信度）。
    请直接使用 so_what_analysis 的判断，不要替换为泛泛之谈。

    ### 趋势判断
    {trend_summary}
    因果解释：{causal_explanation}
```

#### 验收标准

- [x] `WritingBrief` 模型定义完整，包含所有叙事字段
- [x] `write_report_node` 通过 `_build_writing_brief()` 构建 Brief
- [x] tasks.yaml Prompt 显式引用 `story_hook`、`so_what_analysis` 等字段名
- [x] 日报中 GitHub 项目描述能体现 README 摘要中的具体信息
- [x] 日报中新闻 So What 分析不再是泛泛的推测

---

### TASK-005: Prompt 精简 — 从"约束清单"到"质量标准"

**优先级**: 🟡 P2
**预估工时**: 4h
**关联 TD**: TD-003
**状态**: ✅ 已完成（2026-04-01）

#### 目标

将 tasks.yaml 从 271 行/5000 字符精简到 ~150 行/3000 字符以内，去除重复约束，将硬约束改为质量标准。

#### 改造策略

| 现状 | 改为 |
|------|------|
| 18 条硬约束逐条列出 | 保留 5 条核心约束，其余移到 `_validate_report` 后置校验 |
| 3 轮自检规则 | 删除（交给 QualityReviewCrew，Phase 2） |
| agents.yaml 中重复的禁止清单 | 删除，backstory 只描述能力和风格 |
| 每个 Section 的详细格式说明 | 精简为示例驱动（给一个好的段落示例） |

#### 涉及文件

| 文件 | 改动类型 | 说明 |
|------|---------|------|
| `crew/report_writing/config/tasks.yaml` | 重写 | 从 271 行精简到 ~150 行 |
| `crew/report_writing/config/agents.yaml` | 修改 | 去除重复约束，精简 backstory |

#### 精简后的 Prompt 结构

```yaml
write_report:
  description: >
    # 写作简报（来自评分层）
    {writing_brief}

    # 写作目标
    基于以上简报，撰写一篇 AI 日报。
    
    ## 质量标准（非格式清单）
    1. 每段话必须回答"这对读者意味着什么"
    2. 用具体数据说话，不编造统计数字
    3. 直接使用简报中提供的 story_hook 和 so_what_analysis
    4. 用叙事语言讲数据，不填表格
    5. 控制在 800-2000 字
    
    ## 段落示例（参考风格，不要照搬）
    > Anthropic 发布 Claude Code — 终端里的 AI 编程搭档。与 Cursor 这类 IDE 插件不同，
    > Claude Code 直接跑在终端中，用自然语言操作文件系统和 git，相当于给命令行装了个
    > 会编程的副驾驶。发布 48 小时内 GitHub 星数突破 8000，HN 讨论帖超过 500 条回复。
    > 如果你日常用 vim + terminal 开发，这个工具值得在这周试一下。
    
    ## 七段式结构
    [简要的结构要求，不需要逐字段规定格式]
    
  expected_output: >
    完整的 Markdown 日报，800-2000 字，七段式结构。
```

#### 验收标准

- [x] tasks.yaml 行数 ≤ 150 行
- [x] agents.yaml backstory 不超过 1000 字符
- [x] 去除所有与 tasks.yaml 重复的约束
- [x] 保留的核心约束 ≤ 5 条
- [x] 生成的日报通过 `_validate_report` 的 18 项后置校验（校验逻辑不变）

---

### TASK-006: 增强数据模型 — RichRepoData & RichNewsData

**优先级**: 🟡 P2
**预估工时**: 4h
**关联 TD**: TD-001, TD-002
**前置依赖**: TASK-001, TASK-002, TASK-003
**状态**: ✅ 已完成（2026-04-01）

#### 目标

定义增强后的数据模型，统一上游采集层的数据格式，为后续 Phase 2 的 Agent 协作提供基础。

#### 涉及文件

| 文件 | 改动类型 | 说明 |
|------|---------|------|
| `crew/github_trending/models.py` | 修改 | 新增 `RichRepoData` 模型 |
| `crew/new_collect/models.py` | 新建 | 新增 `RichNewsData` 模型 |

#### 模型设计

```python
# crew/github_trending/models.py — 增强版仓库数据
class RichRepoData(BaseModel):
    """增强版 GitHub 仓库数据，包含趋势和内容信息。"""
    
    # 基础信息（现有）
    full_name: str
    description: str
    language: str
    stars: int
    topics: list[str] = Field(default_factory=list)
    html_url: str
    
    # 增强信息（新增）
    readme_summary: str = Field(default="", description="README 前 500 字符摘要")
    stars_7d_ago: int | None = Field(default=None, description="7 天前的星数")
    stars_growth_7d: int | None = Field(default=None, description="近 7 天星数增长")
    commits_last_30d: int | None = Field(default=None, description="近 30 天提交数")
    forks: int = Field(default=0, description="Fork 数")
    contributors_count: int | None = Field(default=None, description="贡献者数量")
    
    # 元数据
    created_at: str = ""
    updated_at: str = ""


# crew/new_collect/models.py — 增强版新闻数据
class RichNewsData(BaseModel):
    """增强版新闻数据，包含正文摘要。"""
    
    # 基础信息（现有）
    title: str
    url: str = ""
    score: int = 0
    source: str = ""
    summary: str = ""
    time: str = ""
    
    # 增强信息（新增）
    content_excerpt: str = Field(default="", description="正文前 300 字符摘要")
```

#### 验收标准

- [x] `RichRepoData` 所有字段有 `description`
- [x] `RichNewsData` 所有字段有 `description`
- [x] 新模型兼容现有下游消费方（向后兼容，新增字段有默认值）

---

## Phase 2：Agent 协作重构（3 周）

> 目标：从"单 Agent 全包"转变为"编辑部协作"模式

---

### TASK-007: 新建 EditorialPlanningCrew — 编辑部选题会

**优先级**: 🟡 P2
**预估工时**: 10h
**关联 TD**: TD-004
**状态**: ✅ 已完成（2026-04-01）

#### 目标

在 `write_report_node` 之前新增一个"编辑部选题"步骤，由专门的 Agent 负责：
- 决定今日信号强度（🔴/🟡/🟢）
- 选择今日头条
- 为每个项目/新闻分配写作角度
- 生成 Kill List（排除不值得写的内容）

#### 涉及文件

| 文件 | 改动类型 | 说明 |
|------|---------|------|
| `crew/editorial_planning/` | 新建 | 整个子 Crew 模块 |
| `crew/editorial_planning/crew.py` | 新建 | EditorialPlanningCrew（@CrewBase） |
| `crew/editorial_planning/models.py` | 新建 | EditorialPlan 输出模型 |
| `crew/editorial_planning/config/agents.yaml` | 新建 | 编辑策划 Agent 配置 |
| `crew/editorial_planning/config/tasks.yaml` | 新建 | 选题规划 Task 配置 |
| `nodes.py` | 修改 | 新增 `editorial_planning_node` |
| `graph.py` | 修改 | 在 score_trends → write_report 之间插入新节点 |

#### 目录结构

```
crew/editorial_planning/
├── __init__.py
├── crew.py                # EditorialPlanningCrew
├── models.py              # EditorialPlan, HeadlineDecision, AngleAssignment
└── config/
    ├── agents.yaml        # editorial_planner Agent
    └── tasks.yaml         # plan_editorial Task
```

#### EditorialPlan 输出模型

```python
class EditorialPlan(BaseModel):
    """编辑部选题规划输出。"""
    
    signal_strength: str = Field(
        description="今日信号强度：'red'/'yellow'/'green'"
    )
    signal_reason: str = Field(
        description="信号强度判断理由，≤30字"
    )
    headline: HeadlineDecision = Field(
        description="今日头条决策"
    )
    repo_angles: list[AngleAssignment] = Field(
        default_factory=list,
        description="每个项目的写作角度分配"
    )
    news_angles: list[AngleAssignment] = Field(
        default_factory=list,
        description="每条新闻的写作角度分配"
    )
    kill_list: list[str] = Field(
        default_factory=list,
        description="排除的内容名称及原因"
    )
    today_hook: str = Field(
        description="今日一句话建议，≤20字"
    )


class HeadlineDecision(BaseModel):
    """头条选择决策。"""
    chosen_item: str = Field(description="选定的头条项目/新闻名称")
    reason: str = Field(description="选择理由")
    angle: str = Field(description="建议的叙事角度")


class AngleAssignment(BaseModel):
    """内容角度分配。"""
    item_name: str = Field(description="项目/新闻名称")
    angle: str = Field(description="分配的切入角度：痛点/成本/规模/对比")
    key_point: str = Field(description="这条内容最值得强调的一点")
```

#### LangGraph 流程变更

```
当前: score_trends → write_report → publish
改后: score_trends → editorial_planning → write_report → publish
```

```python
# graph.py — 新增节点
graph.add_node("editorial_planning", editorial_planning_node)
graph.add_edge("score_trends", "editorial_planning")
graph.add_edge("editorial_planning", "write_report")
```

#### Agent 配置

```yaml
# config/agents.yaml
editorial_planner:
  role: >
    AI 日报主编
  goal: >
    基于今日数据做出编辑决策：选定头条、分配角度、排除低价值内容、
    判断信号强度。你的决策将直接指导写作者的工作。
  backstory: >
    你是一位经验丰富的科技媒体主编，擅长从海量信息中识别最有新闻价值的内容。
    你的判断标准：什么信息能让读者在 3 秒内决定继续读下去。
    你倾向于选择有信息差的内容，而非众所周知的大厂动态。
```

#### 验收标准

- [x] `EditorialPlanningCrew` 可独立运行并输出 `EditorialPlan`
- [x] `editorial_planning_node` 正确插入到 LangGraph 图中
- [x] 信号强度不再永远是 🟡（至少在输入数据差异大时能区分）
- [x] 每个项目有不同的写作角度（不再全用同一角度）
- [x] Kill List 能有效过滤低价值内容
- [x] Crew 失败时有兜底策略（返回默认 Plan）
- [x] 使用 `light` 档 LLM（编辑决策是分类任务，不需要 default 档）

---

### TASK-008: 重构 ReportWritingCrew — 接收 EditorialPlan

**优先级**: 🟡 P2
**预估工时**: 6h
**关联 TD**: TD-004
**前置依赖**: TASK-004, TASK-007
**状态**: ✅ 已完成（2026-04-01）

#### 目标

改造 `ReportWritingCrew`，从"自行决定一切"变为"根据编辑部的 Plan 执行写作"。

#### 涉及文件

| 文件 | 改动类型 | 说明 |
|------|---------|------|
| `crew/report_writing/crew.py` | 修改 | `run()` 接收 `EditorialPlan` 参数 |
| `crew/report_writing/config/tasks.yaml` | 修改 | Prompt 引用 Plan 中的编辑决策 |
| `nodes.py:write_report_node` | 修改 | 传递 Plan 给 Crew |

#### 核心改动

```python
# crew/report_writing/crew.py — run() 签名变更
def run(self,
        writing_brief: WritingBrief,
        editorial_plan: EditorialPlan,
        current_date: str,
        previous_report_context: str = "",
) -> str:
    """基于写作简报和编辑决策撰写日报。"""
    ...
```

```yaml
# tasks.yaml — 注入编辑决策
write_report:
  description: >
    ## 编辑决策（由主编确定，请严格执行）
    信号强度: {signal_strength} ({signal_reason})
    今日头条: {headline_chosen_item}
    头条角度: {headline_angle}
    今日一句话: {today_hook}
    
    ## 写作简报
    {writing_brief}
    
    ## 写作要求
    按照编辑决策撰写日报。你不需要自行判断信号强度和头条选择，
    这些已经由主编决定。你只需要专注于：
    1. 把故事讲好
    2. 让每段话有信息增量
    3. 用具体数据而非空洞形容
```

#### 验收标准

- [x] 写作层不再自行决定信号强度（使用 Plan 中的决策）
- [x] 写作层不再自行选择头条（使用 Plan 中的 headline）
- [x] 每个项目使用 Plan 分配的角度
- [x] Kill List 中的内容不出现在日报中

---

### TASK-009: 新建 QualityReviewCrew — 质量审核

**优先级**: 🟢 P3
**预估工时**: 8h
**关联 TD**: TD-004
**状态**: ✅ 已完成（2026-04-01）

#### 目标

在 `write_report_node` 输出后、`publish_node` 之前，增加一个 LLM 质量审核步骤，替代当前 `_validate_report` 的纯规则校验。

#### 涉及文件

| 文件 | 改动类型 | 说明 |
|------|---------|------|
| `crew/quality_review/` | 新建 | 整个子 Crew 模块 |
| `nodes.py` | 修改 | 新增 `quality_review_node` |
| `graph.py` | 修改 | 在 write_report → publish 之间插入 |

#### LangGraph 流程变更

```
当前: score_trends → write_report → publish
Phase 2 最终: score_trends → editorial_planning → write_report → quality_review → publish
```

#### QualityReviewCrew 职责

1. 检查是否有 LLM 虚构的统计数据（无来源的百分比、金额等）
2. 检查是否有内容与提供的数据不符
3. 检查叙事风格是否符合"克制、精准"要求
4. 生成修改建议（但不自行修改内容）

#### 审核输出模型

```python
class QualityReviewResult(BaseModel):
    """质量审核结果。"""
    passed: bool = Field(description="是否通过审核")
    issues: list[QualityIssue] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)

class QualityIssue(BaseModel):
    """单个质量问题。"""
    severity: str = Field(description="严重程度：'error'/'warning'/'info'")
    location: str = Field(description="问题位置（Section 名称）")
    description: str = Field(description="问题描述")
    suggestion: str = Field(description="修改建议")
```

#### 验收标准

- [x] QualityReviewCrew 能检测出虚构统计数据（如"占 30% 以上"无来源）
- [x] 审核结果记录到 `TrendingState.quality_review`
- [x] 审核失败**不阻断**发布（只记录 warning）
- [x] 使用 `light` 档 LLM（审核是分类/比对任务）

---

## Phase 3：记忆系统建设（2 周）

> 目标：让日报有"记忆"，消除跨日雷同，建立风格进化能力

---

### TASK-010: 话题连续性追踪 — TOPIC_TRACKER.md

**优先级**: 🟡 P2
**预估工时**: 6h
**关联 TD**: TD-005
**状态**: ✅ 已完成（2026-04-01）

#### 目标

建立话题追踪机制，记录最近 7 天覆盖的话题，避免连续多天报道相同主题。

#### 涉及文件

| 文件 | 改动类型 | 说明 |
|------|---------|------|
| `crew/report_writing/topic_tracker.py` | 新建 | 话题追踪器 |
| `output/TOPIC_TRACKER.md` | 自动生成 | 话题追踪记录文件 |
| `nodes.py:write_report_node` | 修改 | 写作完成后更新追踪记录 |
| `crew/editorial_planning/config/tasks.yaml` | 修改 | 注入近期话题供编辑参考 |

#### TOPIC_TRACKER.md 格式

```markdown
# 话题追踪记录

## 最近 7 天覆盖话题

| 日期 | 头条话题 | 覆盖关键词 | 今日一句话 |
|------|---------|-----------|-----------|
| 2026-03-31 | MCP 工具链整合 | MCP, Agent, 工具链 | MCP生态正从概念验证走向工具链整合 |
| 2026-03-30 | Claude Code 发布 | Claude, 编程助手 | AI编程工具从辅助走向主导 |
| 2026-03-27 | MCP 生态扩张 | MCP, 企业工具 | MCP生态快速扩张 |

## Kill List（近 3 天已深度报道）
- MCP（已连续 2 天作为头条，建议本期降级或跳过）
- Claude Code（已报道，除非有重大更新）
```

#### 核心实现

```python
class TopicTracker:
    """话题连续性追踪器。"""
    
    TRACKER_PATH = Path("output/TOPIC_TRACKER.md")
    MAX_DAYS = 7
    
    def get_recent_topics(self) -> list[dict]:
        """获取最近 7 天的话题记录。"""
        ...
    
    def get_kill_list(self, days: int = 3) -> list[str]:
        """获取近 N 天已深度报道的话题，建议本期降级。"""
        ...
    
    def record_today(self, date: str, headline: str, 
                     keywords: list[str], hook: str) -> None:
        """记录今日话题。"""
        ...
```

#### 验收标准

- [x] 每次运行后 `TOPIC_TRACKER.md` 自动更新
- [x] `editorial_planning_node` 能读取近期话题并传入 Prompt
- [x] 连续两天不再使用相同的头条话题
- [x] "今日一句话"不再跨日雷同
- [x] 追踪记录超过 7 天自动清理

---

### TASK-011: 风格记忆系统 — STYLE_MEMORY.md

**优先级**: 🟢 P3
**预估工时**: 6h
**关联 TD**: TD-005
**状态**: ✅ 已完成（2026-04-01）

#### 目标

建立写作风格记忆系统，记录什么样的表达效果好、什么样的表达应该避免。

#### 涉及文件

| 文件 | 改动类型 | 说明 |
|------|---------|------|
| `output/STYLE_MEMORY.md` | 自动生成 | 风格记忆文件 |
| `crew/report_writing/style_memory.py` | 新建 | 风格记忆管理器 |
| `crew/report_writing/config/tasks.yaml` | 修改 | 注入风格记忆 |

#### STYLE_MEMORY.md 格式

```markdown
# 写作风格记忆

## ✅ 效果好的表达（可复用的模式）
- "发布 48 小时内星数突破 8000" — 用时间窗口 + 数据制造紧迫感
- "相当于给命令行装了个会编程的副驾驶" — 用类比降低理解门槛
- "如果你日常用 vim + terminal 开发" — 用场景锚定目标读者

## ❌ 效果差的表达（应避免的模式）
- "核心原因是…但是…" — 连续 3 天使用，已产生模板感
- "MCP 生态正在…" — 连续 2 天使用同样的开头

## 📊 质量趋势
- 3/27: 校验通过 15/18 项，主要问题：信号强度单一
- 3/30: 校验通过 16/18 项
- 3/31: 校验通过 14/18 项，主要问题：趋势洞察模板感
```

#### 核心实现

```python
class StyleMemory:
    """写作风格记忆管理器。"""
    
    MEMORY_PATH = Path("output/STYLE_MEMORY.md")
    
    def get_style_guidance(self) -> str:
        """获取风格指导文本，注入到写作 Prompt 中。"""
        ...
    
    def record_quality_result(self, date: str, 
                              validation_issues: list[str],
                              good_patterns: list[str] = None) -> None:
        """记录质量结果，更新风格记忆。"""
        ...
    
    def detect_repeated_patterns(self, content: str) -> list[str]:
        """检测内容中是否有近期重复使用的表达模式。"""
        ...
```

#### 验收标准

- [x] 每次运行后 `STYLE_MEMORY.md` 自动更新
- [x] 写作 Prompt 中注入风格记忆指导
- [x] 连续使用 3 次以上的表达模式会被标记为"应避免"
- [x] 质量趋势可追踪

---

## 实施路线图

```
Phase 1（Week 1-2）: 数据增厚 + 信息传递
  ├── TASK-001: GitHub README 摘要抓取 (6h)
  ├── TASK-002: 星数增长趋势追踪 (4h)
  ├── TASK-003: 新闻正文摘要提取 (6h)
  ├── TASK-004: WritingBrief 中间格式 (8h)     ← 核心改动
  ├── TASK-005: Prompt 精简 (4h)
  └── TASK-006: 增强数据模型 (4h)

Phase 2（Week 3-5）: Agent 协作重构
  ├── TASK-007: EditorialPlanningCrew (10h)     ← 核心改动
  ├── TASK-008: ReportWritingCrew 改造 (6h)
  └── TASK-009: QualityReviewCrew (8h)

Phase 3（Week 6-7）: 记忆系统
  ├── TASK-010: 话题连续性追踪 (6h)
  └── TASK-011: 风格记忆系统 (6h)
```

### 依赖关系

```
TASK-001 (README) ──┐
TASK-002 (星数)  ──┤
TASK-003 (新闻)  ──┼──→ TASK-006 (数据模型) ──→ TASK-004 (WritingBrief)
                    │
TASK-005 (Prompt) ──┘
                              
TASK-004 (Brief) ──→ TASK-007 (Editorial) ──→ TASK-008 (Writing改造)
                                            ──→ TASK-009 (QualityReview)

TASK-007 (Editorial) ──→ TASK-010 (话题追踪)
TASK-008 (Writing改造) ──→ TASK-011 (风格记忆)
```

---

## 风险评估

| 任务 | 风险 | 缓解措施 |
|------|------|---------|
| TASK-001 | README API 调用增加 GitHub 速率消耗 | 只对 top-15 候选抓取，有 Token 时影响可忽略 |
| TASK-003 | 部分网站反爬导致正文提取失败 | 使用 `trafilatura` 已内置多种策略；失败时保持空字符串 |
| TASK-004 | WritingBrief 改动影响面大，涉及多个文件 | 先保留旧 JSON 传递路径作为兜底 |
| TASK-005 | Prompt 精简后日报格式可能退化 | `_validate_report` 后置校验不变，格式问题仍可检出 |
| TASK-007 | 新 Crew 增加 LLM 调用成本 | 使用 light 档，每次仅增加 ~2K tokens |
| TASK-009 | 质量审核可能误判正常内容 | 审核只记录 warning，不阻断发布 |
| TASK-010/011 | 持久化文件在多实例部署时冲突 | 当前单实例运行，未来迁移到数据库 |

---

## 预期效果

| 指标 | 当前 | Phase 1 后 | Phase 2 后 | Phase 3 后 |
|------|------|-----------|-----------|-----------|
| 信号强度多样性 | 全部 🟡 | 🟡 为主 | 三种均衡分布 | 三种均衡分布 |
| "今日一句话"雷同率 | ~30% | ~30% | ~10% | ~5% |
| 虚构统计出现频率 | ~20% | ~5% | ~5% | ~5% |
| 趋势洞察模板感 | 高 | 中 | 低 | 低 |
| LLM Token 消耗增加 | 基准 | +10% | +25% | +30% |

---

*本文档随项目迭代更新，每完成一个 Task 后请更新状态标记。*
