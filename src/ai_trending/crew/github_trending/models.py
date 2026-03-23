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
