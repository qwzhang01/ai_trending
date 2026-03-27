"""TrendScoringCrew 数据模型 — 趋势评分结构化输出定义。"""

from __future__ import annotations

from pydantic import BaseModel, Field


class ScoredRepo(BaseModel):
    """单个 GitHub 仓库的评分结果。"""

    repo: str = Field(
        description="GitHub 仓库全名，格式 owner/repo_name，必须与原始数据完全一致"
    )
    name: str = Field(default="", description="项目显示名称")
    url: str = Field(default="", description="GitHub 完整 URL")
    stars: int = Field(
        default=0, description="Star 数，从原始数据中读取，不得估算或虚构"
    )
    language: str = Field(default="", description="主要编程语言")
    is_ai: bool = Field(default=True, description="是否为 AI 相关项目")
    category: str = Field(
        default="",
        description="项目类别：Agent框架 / 推理框架 / 多模态 / 开发工具 / 数据处理 / 模型微调 / 评测基准 / 应用集成",
    )
    scores: dict[str, float] = Field(
        default_factory=dict,
        description="评分字典，包含 热度/技术前沿性/成长潜力/综合 四个维度，各 0-10 分",
    )
    one_line_reason: str = Field(
        default="",
        description="一句话说明，不超过 30 字，说清楚技术价值或应用场景",
    )
    story_hook: str = Field(
        default="",
        description="故事开篇钩子，不超过 20 字，制造信息差或悬念",
    )
    technical_detail: str = Field(
        default="",
        description="具体技术细节，不超过 25 字，支撑判断",
    )
    target_audience: str = Field(
        default="",
        description="谁应该关注，不超过 15 字，明确指向",
    )
    scenario_description: str = Field(
        default="",
        description="场景化描述，不超过 25 字",
    )


class ScoredNews(BaseModel):
    """单条新闻的评分结果。"""

    title: str = Field(description="新闻标题，保留原文，不改写")
    url: str = Field(default="", description="新闻链接")
    source: str = Field(default="", description="来源名称")
    category: str = Field(
        default="",
        description="新闻类别：大厂动态 / 技术突破 / 开源生态 / 投融资 / 行业观察 / 产品发布 / 政策监管",
    )
    impact_score: float = Field(
        ge=0, le=10, default=5.0, description="行业影响力评分，0-10"
    )
    impact_reason: str = Field(
        default="",
        description="一句话说明行业影响，不超过 35 字，必须是判断句",
    )
    so_what_analysis: str = Field(
        default="",
        description="So What 分析，不超过 40 字，指出新闻背后真正值得注意的点",
    )
    credibility_label: str = Field(
        default="🟡 社区讨论",
        description="可信度标签：🟢 一手信源 / 🟡 社区讨论 / 🔴 待验证",
    )
    time_window: str = Field(
        default="中期（3-12个月）",
        description="时间窗口：短期（1-3个月）/中期（3-12个月）/长期（1年以上）",
    )
    affected_audience: str = Field(
        default="开发者",
        description="受影响群体：技术决策者 / 开发者 / 投资人 / 行业观察者",
    )


class DailySummary(BaseModel):
    """今日趋势洞察汇总。"""

    top_trend: str = Field(
        default="",
        description="今天最值得关注的一个趋势，不超过 30 字，有数据支撑",
    )
    hot_directions: list[str] = Field(
        default_factory=list,
        description="3-5 个热点技术方向，每个 3-6 字",
    )
    overall_sentiment: str = Field(
        default="中性",
        description="整体情绪：积极/中性/消极",
    )
    causal_explanation: str = Field(
        default="",
        description="因果解释，不超过 50 字，说明为什么会这样",
    )
    data_support: str = Field(
        default="",
        description="数据支撑，不超过 40 字，用数据讲判断",
    )
    forward_looking: str = Field(
        default="",
        description="前瞻预判，不超过 35 字，预测下一步发展",
    )


class TrendScoringOutput(BaseModel):
    """TrendScoringCrew 的完整输出模型。"""

    scored_repos: list[ScoredRepo] = Field(
        default_factory=list,
        description="按综合评分从高到低排列的 GitHub 项目评分列表",
    )
    scored_news: list[ScoredNews] = Field(
        default_factory=list,
        description="按影响力评分从高到低排列的新闻评分列表",
    )
    daily_summary: DailySummary = Field(
        default_factory=DailySummary,
        description="今日趋势洞察汇总",
    )
