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
    lifecycle_tag: str = Field(
        default="🔵 普通",
        description="项目生命周期标签：🌱 新生 / 🚀 爆发 / 📈 稳健 / ⚠️ 异常 / 🔵 普通（来自评分层）",
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
    report_template: str = Field(
        default="standard",
        description="报告模板类型：'deep-dive'（深度分析）/ 'standard'（标准）/ 'review'（回顾），由 signal_strength 映射决定",
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
        """将 WritingBrief 格式化为高信噪比的 Prompt 文本。

        原则：只输出写作层真正需要的核心素材，去掉 url、language、
        content_excerpt 等低价值字段，降低 LLM 注意力稀释。
        目标：输出控制在 ~2000 tokens 以内。
        """
        lines: list[str] = []

        # 编辑决策摘要（信号强度 + 头条建议）
        signal_map = {
            "red": "🔴 重大变化日",
            "yellow": "🟡 常规更新日",
            "green": "🟢 平静日",
        }
        signal_label = signal_map.get(self.signal_strength_suggestion, "🟡 常规更新日")
        lines.append(f"**今日信号强度建议**: {signal_label}")
        if self.headline_candidate:
            lines.append(f"**建议头条**: {self.headline_candidate}")
        if self.headline_story_hook:
            lines.append(f"**头条故事钩子**: {self.headline_story_hook}")
        lines.append("")

        # GitHub 项目简报（只保留核心写作素材，去掉 url/language/content_excerpt）
        if self.top_repos:
            lines.append("### 推荐 GitHub 项目")
            for i, repo in enumerate(self.top_repos, 1):
                growth = (
                    f"（+{repo.stars_growth_7d}）"
                    if repo.stars_growth_7d is not None
                    else ""
                )
                # 去掉 url 和 language：写作层只需名称和数据，url 发布层才用
                lines.append(
                    f"\n**{i}. {repo.name}** {repo.lifecycle_tag} ⭐ {repo.stars}{growth}"
                )
                if repo.one_line_reason:
                    lines.append(f"  入选: {repo.one_line_reason}")
                if repo.story_hook:
                    lines.append(f"  钩子: {repo.story_hook}")
                if repo.technical_detail:
                    lines.append(f"  技术: {repo.technical_detail}")
                if repo.target_audience:
                    lines.append(f"  受众: {repo.target_audience}")
                # readme_summary 截断到 100 字，避免太长
                if repo.readme_summary:
                    summary = repo.readme_summary[:100].rstrip()
                    lines.append(
                        f"  README: {summary}…"
                        if len(repo.readme_summary) > 100
                        else f"  README: {summary}"
                    )
                if repo.suggested_angle:
                    lines.append(f"  角度: {repo.suggested_angle}")
            lines.append("")
            lines.append(
                "请直接使用上方的钩子/技术/受众素材写作，不要编造新的数字或描述。"
            )
            lines.append("")

        # 新闻简报（去掉 url 和 content_excerpt，只保留标题+来源+标签+so_what）
        if self.top_news:
            lines.append("### 推荐新闻")
            for i, news in enumerate(self.top_news, 1):
                # 从 credibility_label 中提取 emoji（取第一个字符），与 category 合并为单标签
                emoji = (
                    news.credibility_label.split()[0] if news.credibility_label else ""
                )
                tag = (
                    f"{emoji} {news.category}".strip()
                    if (emoji or news.category)
                    else ""
                )
                prefix = f"{tag} " if tag else ""
                lines.append(f"\n**{i}.** {prefix}{news.title}")
                lines.append(f"  来源: {news.source}")
                if news.so_what_analysis:
                    lines.append(f"  So What: {news.so_what_analysis}")
            lines.append("")
            lines.append("新闻请直接使用上方 So What 分析，不要替换为泛泛之谈。")
            lines.append("")

        # 趋势判断
        trend_parts: list[str] = []
        if self.trend_summary:
            trend_parts.append(f"主趋势: {self.trend_summary}")
        if self.causal_explanation:
            trend_parts.append(f"因果: {self.causal_explanation}")
        if self.data_support:
            trend_parts.append(f"数据: {self.data_support}")
        if self.forward_looking:
            trend_parts.append(f"前瞻: {self.forward_looking}")
        if self.hot_directions:
            trend_parts.append(f"热点方向: {' / '.join(self.hot_directions)}")
        if trend_parts:
            lines.append("### 趋势判断")
            lines.extend(trend_parts)

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
    quality_badge: str = Field(
        default="",
        description="质量徽章字符串，由 quality_review_node 根据通过率生成并追加到报告末尾；为空时不追加。",
    )
