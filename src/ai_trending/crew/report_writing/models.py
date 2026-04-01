"""ReportWritingCrew 数据模型 — 日报输出 + 写作简报结构化定义。"""

from __future__ import annotations

from pydantic import BaseModel, Field


# ==================== 写作简报模型（评分层→写作层） ====================


class RepoBrief(BaseModel):
    """单个仓库的写作简报 — 聚合评分层叙事字段，供写作层直接使用。"""

    name: str = Field(default="", description="项目显示名称")
    url: str = Field(default="", description="GitHub 完整 URL")
    stars: int = Field(default=0, description="Star 数")
    stars_growth_7d: int | None = Field(
        default=None, description="近 7 天 Star 增长数（来自 TASK-002 StarTracker）"
    )
    language: str = Field(default="", description="主要编程语言")
    readme_summary: str = Field(
        default="", description="README 前 500 字符摘要（来自 TASK-001）"
    )
    story_hook: str = Field(
        default="", description="故事开篇钩子，不超过 20 字（来自评分层）"
    )
    technical_detail: str = Field(
        default="", description="具体技术细节，不超过 25 字（来自评分层）"
    )
    target_audience: str = Field(
        default="", description="谁应该关注，不超过 15 字（来自评分层）"
    )
    suggested_angle: str = Field(
        default="",
        description="建议切入角度：痛点切入/成本切入/规模切入/对比切入",
    )
    one_line_reason: str = Field(
        default="", description="入选理由，不超过 30 字（来自评分层）"
    )


class NewsBrief(BaseModel):
    """单条新闻的写作简报 — 聚合评分层叙事字段，供写作层直接使用。"""

    title: str = Field(default="", description="新闻标题（保留原文，不改写）")
    url: str = Field(default="", description="新闻链接")
    source: str = Field(default="", description="来源名称")
    content_excerpt: str = Field(
        default="", description="文章正文摘要（来自 TASK-003 content_extractor）"
    )
    so_what_analysis: str = Field(
        default="",
        description="So What 分析，不超过 40 字（来自评分层）",
    )
    credibility_label: str = Field(
        default="🟡 社区讨论",
        description="可信度标签：🟢 一手信源 / 🟡 社区讨论 / 🔴 待验证",
    )
    category: str = Field(
        default="",
        description="新闻类别：大厂动态/技术突破/开源生态/投融资/行业观察/产品发布/政策监管",
    )


class WritingBrief(BaseModel):
    """写作简报 — 评分层→写作层的结构化信息传递。

    替代原有的巨大 JSON blob 传递方式，将评分层的叙事字段
    （story_hook、so_what_analysis 等）显式传递给写作层。
    """

    # 编辑决策输入
    signal_strength_suggestion: str = Field(
        default="yellow",
        description="建议的信号强度：'red'/'yellow'/'green'，基于今日数据重要性",
    )
    headline_candidate: str = Field(
        default="", description="建议的今日头条项目/新闻名称"
    )
    headline_story_hook: str = Field(
        default="", description="头条的故事钩子（来自评分层 story_hook）"
    )

    # GitHub 项目简报
    top_repos: list[RepoBrief] = Field(
        default_factory=list,
        description="推荐的 GitHub 项目列表（按综合评分从高到低，最多 5 个）",
    )

    # 新闻简报
    top_news: list[NewsBrief] = Field(
        default_factory=list,
        description="推荐的新闻列表（按影响力评分从高到低，最多 8 条）",
    )

    # 趋势判断
    trend_summary: str = Field(
        default="", description="今日趋势总结（来自评分层 DailySummary.top_trend）"
    )
    causal_explanation: str = Field(
        default="",
        description="因果解释（来自评分层 DailySummary.causal_explanation）",
    )
    data_support: str = Field(
        default="",
        description="数据支撑（来自评分层 DailySummary.data_support）",
    )
    forward_looking: str = Field(
        default="",
        description="前瞻预判（来自评分层 DailySummary.forward_looking）",
    )
    hot_directions: list[str] = Field(
        default_factory=list,
        description="3-5 个热点技术方向（来自评分层 DailySummary.hot_directions）",
    )

    def format_for_prompt(self) -> str:
        """将 WritingBrief 格式化为 Prompt 可读的文本。

        供 write_report_node 注入到 ReportWritingCrew 的 kickoff inputs 中。
        """
        lines: list[str] = []

        # 编辑决策
        signal_map = {
            "red": "🔴 重大变化日",
            "yellow": "🟡 常规更新日",
            "green": "🟢 平静日",
        }
        signal_label = signal_map.get(
            self.signal_strength_suggestion, "🟡 常规更新日"
        )
        lines.append(f"**今日信号强度建议**: {signal_label}")
        if self.headline_candidate:
            lines.append(f"**建议头条**: {self.headline_candidate}")
        if self.headline_story_hook:
            lines.append(f"**头条故事钩子**: {self.headline_story_hook}")
        lines.append("")

        # GitHub 项目简报
        if self.top_repos:
            lines.append("### 推荐 GitHub 项目")
            for i, repo in enumerate(self.top_repos, 1):
                growth = (
                    f"（+{repo.stars_growth_7d}）"
                    if repo.stars_growth_7d is not None
                    else ""
                )
                lines.append(
                    f"\n**{i}. [{repo.name}]({repo.url})** "
                    f"⭐ {repo.stars}{growth} | {repo.language}"
                )
                if repo.one_line_reason:
                    lines.append(f"  - 入选理由: {repo.one_line_reason}")
                if repo.story_hook:
                    lines.append(f"  - 故事钩子: {repo.story_hook}")
                if repo.technical_detail:
                    lines.append(f"  - 技术亮点: {repo.technical_detail}")
                if repo.target_audience:
                    lines.append(f"  - 目标读者: {repo.target_audience}")
                if repo.readme_summary:
                    lines.append(f"  - README 摘要: {repo.readme_summary}")
                if repo.suggested_angle:
                    lines.append(f"  - 建议切入角度: {repo.suggested_angle}")
            lines.append("")
            lines.append(
                "每个项目已提供：story_hook（开篇钩子）、technical_detail（技术亮点）、"
                "target_audience（目标读者）。请直接使用这些素材，不要重新编造。"
            )
            lines.append("")

        # 新闻简报
        if self.top_news:
            lines.append("### 推荐新闻")
            for i, news in enumerate(self.top_news, 1):
                lines.append(
                    f"\n**{i}. {news.title}**"
                )
                lines.append(f"  - 来源: {news.source} | {news.url}")
                if news.credibility_label:
                    lines.append(f"  - 可信度: {news.credibility_label}")
                if news.category:
                    lines.append(f"  - 类别: {news.category}")
                if news.so_what_analysis:
                    lines.append(f"  - So What 分析: {news.so_what_analysis}")
                if news.content_excerpt:
                    lines.append(f"  - 内容摘要: {news.content_excerpt}")
            lines.append("")
            lines.append(
                "每条新闻已提供：so_what_analysis（深层分析）、credibility_label（可信度）。"
                "请直接使用 so_what_analysis 的判断，不要替换为泛泛之谈。"
            )
            lines.append("")

        # 趋势判断
        lines.append("### 趋势判断")
        if self.trend_summary:
            lines.append(f"**趋势总结**: {self.trend_summary}")
        if self.causal_explanation:
            lines.append(f"**因果解释**: {self.causal_explanation}")
        if self.data_support:
            lines.append(f"**数据支撑**: {self.data_support}")
        if self.forward_looking:
            lines.append(f"**前瞻预判**: {self.forward_looking}")
        if self.hot_directions:
            lines.append(
                f"**热点方向**: {' / '.join(self.hot_directions)}"
            )

        return "\n".join(lines)


# ==================== 日报输出模型 ====================


class ReportOutput(BaseModel):
    """日报撰写 Crew 的输出模型。

    content 字段存储完整的 Markdown 日报正文，
    供 write_report_node 直接写入 report_content 状态字段。
    """

    content: str = Field(
        default="",
        description=(
            "完整的 AI 日报 Markdown 文本，包含七段式结构："
            "标题（含今日信号强度 + 今日一句话）、今日头条（1条深度解读）、"
            "GitHub 热点项目（2-4个，含星数增长上下文）、"
            "AI 热点新闻（4-6条，含可信度标签 + So What 分析）、"
            "趋势洞察（3-5条，含数据支撑）、本周行动建议（1-2条可落地任务）、"
            "上期回顾（可选，有历史追踪数据时包含）。"
            "总字数 800-2000 字，无禁用词，无感叹号。"
        ),
    )
    validation_issues: list[str] = Field(
        default_factory=list,
        description="格式校验问题列表，空列表表示通过校验。",
    )
