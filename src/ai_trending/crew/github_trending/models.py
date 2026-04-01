"""GitHub Trending Crew — Pydantic 数据模型。"""

from __future__ import annotations

from pydantic import BaseModel, Field


class GitHubSearchPlan(BaseModel):
    """CrewAI 关键词规划输出。"""

    keywords: list[str] = Field(
        default_factory=list,
        description="用于 GitHub 搜索的 3-5 个英文技术关键词或短语",
    )
    search_focus: str = Field(
        default="",
        description="本次搜索应重点覆盖的技术方向",
    )


class RankedGitHubRepo(BaseModel):
    """CrewAI 趋势分析后的单个仓库评分。"""

    full_name: str = Field(description="GitHub 仓库全名，必须与候选仓库完全一致")
    trend_score: float = Field(ge=0, le=10, description="趋势代表性评分")
    innovation_score: float = Field(ge=0, le=10, description="技术前沿性评分")
    execution_score: float = Field(ge=0, le=10, description="工程落地性评分")
    ecosystem_score: float = Field(ge=0, le=10, description="社区与生态信号评分")
    representative: bool = Field(description="是否能代表最近 AI 发展趋势")
    reason: str = Field(description="简短说明，不超过60字")


class GitHubTrendRanking(BaseModel):
    """CrewAI 趋势分析输出。"""

    summary: str = Field(description="对本轮 GitHub 趋势的总体判断")
    hot_signals: list[str] = Field(
        default_factory=list,
        description="本轮最值得关注的 3-5 个技术信号",
    )
    ranked_repos: list[RankedGitHubRepo] = Field(
        default_factory=list,
        description="按重要性排序后的候选仓库",
    )


class RepoCandidate(BaseModel):
    """单个候选仓库的精简信息（供 Agent 分析使用）。"""

    full_name: str
    description: str = ""
    language: str = "未知"
    stars: int = 0
    topics: list[str] = Field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""
    html_url: str = ""
    match_count: int = 1
    heuristic_score: float = 0.0
    readme_summary: str = Field(
        default="",
        description="README 前 500 字符摘要，去除 badge、图片链接等噪音",
    )
    stars_7d_ago: int | None = Field(
        default=None,
        description="7 天前的星数快照，无历史数据时为 None",
    )
    stars_growth_7d: int | None = Field(
        default=None,
        description="近 7 天星数增长量，无历史数据时为 None",
    )


class GitHubSearchResult(BaseModel):
    """程序化 GitHub 搜索的结构化输出：候选仓库列表 + 搜索元信息。"""

    candidates: list[RepoCandidate] = Field(
        default_factory=list,
        description="经过过滤、去重、预排序后的候选仓库列表",
    )
    keywords_used: list[str] = Field(
        default_factory=list,
        description="本次实际使用的搜索关键词",
    )
    total_found: int = Field(default=0, description="过滤前的原始候选数量")
    dedup_filtered: int = Field(default=0, description="被去重缓存过滤掉的数量")


class RichRepoData(BaseModel):
    """增强版 GitHub 仓库数据，统一上游采集层的数据格式。

    包含基础信息、趋势增长、内容摘要三个维度，
    所有新增字段均有默认值，向后兼容现有下游消费方。
    """

    # --- 基础信息（与 RepoCandidate 对齐）---
    full_name: str = Field(description="仓库全名，格式 owner/repo")
    description: str = Field(default="", description="仓库简介")
    language: str = Field(default="未知", description="主要编程语言")
    stars: int = Field(default=0, description="当前 Star 总数")
    topics: list[str] = Field(default_factory=list, description="仓库标签列表")
    html_url: str = Field(default="", description="仓库 GitHub 页面 URL")
    created_at: str = Field(default="", description="仓库创建日期，格式 YYYY-MM-DD")
    updated_at: str = Field(default="", description="最后更新日期，格式 YYYY-MM-DD")

    # --- 趋势增长（来自 TASK-002 StarTracker）---
    stars_7d_ago: int | None = Field(
        default=None, description="7 天前的星数快照，无历史数据时为 None"
    )
    stars_growth_7d: int | None = Field(
        default=None, description="近 7 天星数增长量，无历史数据时为 None"
    )
    forks: int = Field(default=0, description="Fork 数")
    contributors_count: int | None = Field(
        default=None, description="贡献者数量，API 未返回时为 None"
    )
    commits_last_30d: int | None = Field(
        default=None, description="近 30 天提交数，API 未返回时为 None"
    )

    # --- 内容摘要（来自 TASK-001 README 抓取）---
    readme_summary: str = Field(
        default="", description="README 前 500 字符摘要，去除 badge 和图片链接"
    )

    @classmethod
    def from_candidate(cls, candidate: RepoCandidate) -> RichRepoData:
        """从 RepoCandidate 构建 RichRepoData，自动映射共有字段。"""
        return cls(
            full_name=candidate.full_name,
            description=candidate.description,
            language=candidate.language,
            stars=candidate.stars,
            topics=candidate.topics,
            html_url=candidate.html_url,
            created_at=candidate.created_at,
            updated_at=candidate.updated_at,
            stars_7d_ago=candidate.stars_7d_ago,
            stars_growth_7d=candidate.stars_growth_7d,
            readme_summary=candidate.readme_summary,
        )
