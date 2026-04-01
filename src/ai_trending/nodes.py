"""LangGraph 节点实现 — 每个节点是流水线中的一个独立步骤.

节点职责:
  - collect_github_node: 调用 GitHubTrendingTool 抓取热门项目（工具内部使用 CrewAI 规划与分析）
  - collect_news_node:   触发 NewsCollectCrew（多源抓取 + CrewAI Agent LLM 筛选）
  - score_trends_node:   调用 TrendScoringCrew 结构化评分（Agent 机制，JSON 输出）
  - editorial_planning_node: 调用 EditorialPlanningCrew 做编辑选题规划
  - write_report_node:   调用 ReportWritingCrew 撰写 Markdown 日报
  - quality_review_node: 调用 QualityReviewCrew 质量审核（不阻断发布）
  - publish_node:        调用 publish tools 推送到各渠道

设计原则:
  - 每个节点只读取需要的 state 字段，写入自己负责的字段
  - 节点层禁止直接调用 LLM，所有 LLM 判断必须封装为 CrewAI Crew
  - GitHub 采集的 CrewAI 编排下沉到工具内部，节点只负责接线
  - 评分节点调用 TrendScoringCrew（Agent 机制，结构化 Pydantic 输出）
  - 报告撰写节点调用 ReportWritingCrew（Agent 机制，格式规范强约束）
"""

from __future__ import annotations

from typing import Any

from ai_trending.logger import get_logger

log = get_logger("nodes")


# ==================== 工具函数 ====================


def _merge_token_usage(
    prev: dict[str, int],
    new: dict[str, int],
    node_name: str,
) -> dict[str, int]:
    """将本次节点的 token 用量累加到全局 token_usage 字典。

    Args:
        prev:      State 中已有的 token_usage（可能为空 {}）
        new:       本次 Crew 调用返回的 token 用量
        node_name: 节点名称，用于记录各节点分项用量

    Returns:
        合并后的 token_usage 字典，包含：
          - prompt_tokens:       累计 prompt token 数
          - completion_tokens:   累计 completion token 数
          - total_tokens:        累计总 token 数
          - successful_requests: 累计成功请求次数
          - by_node:             各节点分项用量 {node_name: {total_tokens, ...}}
    """
    merged: dict[str, Any] = {
        "prompt_tokens": prev.get("prompt_tokens", 0) + new.get("prompt_tokens", 0),
        "completion_tokens": prev.get("completion_tokens", 0)
        + new.get("completion_tokens", 0),
        "total_tokens": prev.get("total_tokens", 0) + new.get("total_tokens", 0),
        "successful_requests": prev.get("successful_requests", 0)
        + new.get("successful_requests", 0),
    }
    # 保留各节点分项用量，方便排查哪个节点消耗最多
    by_node: dict[str, Any] = dict(prev.get("by_node") or {})
    by_node[node_name] = {
        "prompt_tokens": new.get("prompt_tokens", 0),
        "completion_tokens": new.get("completion_tokens", 0),
        "total_tokens": new.get("total_tokens", 0),
        "successful_requests": new.get("successful_requests", 0),
    }
    merged["by_node"] = by_node
    return merged


def _decide_signal_strength(scored_repos: list, scored_news: list) -> str:
    """根据评分数据判断今日信号强度。

    规则：
    - red:    有项目综合分 >= 9.0，或有新闻影响力分 >= 9.0
    - yellow: 有项目综合分 >= 7.0，或有新闻影响力分 >= 7.0
    - green:  其他情况（平静日）
    """
    max_repo_score = 0.0
    for repo in scored_repos:
        scores = getattr(repo, "scores", None) or {}
        overall = scores.get("综合", scores.get("overall", 0.0))
        if overall > max_repo_score:
            max_repo_score = overall

    max_news_score = 0.0
    for news in scored_news:
        impact = getattr(news, "impact_score", 0.0) or 0.0
        if impact > max_news_score:
            max_news_score = impact

    if max_repo_score >= 9.0 or max_news_score >= 9.0:
        return "red"
    if max_repo_score >= 7.0 or max_news_score >= 7.0:
        return "yellow"
    return "green"


# 切入角度轮转列表，供 _build_writing_brief 为每个项目分配不同角度
_CUT_ANGLES = ["痛点切入", "规模切入", "对比切入", "成本切入"]


def _build_writing_brief(
    scoring_result_json: str,
    github_data: str,
    news_data: str,
) -> "WritingBrief":
    """从评分 JSON 构建写作简报，显式传递叙事字段给写作层。

    Args:
        scoring_result_json: TrendScoringOutput 的 JSON 字符串
        github_data:         GitHub 原始数据（用于补充 README 等信息）
        news_data:           新闻原始数据（用于补充 content_excerpt 等信息）

    Returns:
        WritingBrief 实例，包含结构化的写作素材
    """
    import json

    from ai_trending.crew.report_writing.models import (
        NewsBrief,
        RepoBrief,
        WritingBrief,
    )

    # 解析评分 JSON
    try:
        scoring_data = json.loads(scoring_result_json) if scoring_result_json else {}
    except (json.JSONDecodeError, TypeError):
        log.warning("[_build_writing_brief] scoring_result JSON 解析失败，使用空数据")
        scoring_data = {}

    scored_repos_raw = scoring_data.get("scored_repos", [])
    scored_news_raw = scoring_data.get("scored_news", [])
    daily_summary = scoring_data.get("daily_summary", {})

    # 构建 RepoBrief 列表（最多 5 个）
    top_repos: list[RepoBrief] = []
    for i, repo_data in enumerate(scored_repos_raw[:5]):
        angle = _CUT_ANGLES[i % len(_CUT_ANGLES)]
        top_repos.append(
            RepoBrief(
                name=repo_data.get("name", repo_data.get("repo", "")),
                url=repo_data.get("url", ""),
                stars=repo_data.get("stars", 0),
                stars_growth_7d=repo_data.get("stars_growth_7d"),
                language=repo_data.get("language", ""),
                readme_summary=repo_data.get("readme_summary", ""),
                story_hook=repo_data.get("story_hook", ""),
                technical_detail=repo_data.get("technical_detail", ""),
                target_audience=repo_data.get("target_audience", ""),
                suggested_angle=angle,
                one_line_reason=repo_data.get("one_line_reason", ""),
            )
        )

    # 构建 NewsBrief 列表（最多 8 条）
    top_news: list[NewsBrief] = []
    for news_data_item in scored_news_raw[:8]:
        top_news.append(
            NewsBrief(
                title=news_data_item.get("title", ""),
                url=news_data_item.get("url", ""),
                source=news_data_item.get("source", ""),
                content_excerpt=news_data_item.get("content_excerpt", ""),
                so_what_analysis=news_data_item.get("so_what_analysis", ""),
                credibility_label=news_data_item.get(
                    "credibility_label", "🟡 社区讨论"
                ),
                category=news_data_item.get("category", ""),
            )
        )

    # 判断信号强度
    # 使用简化版：从 raw dict 中提取分数
    max_repo_score = 0.0
    for repo_data in scored_repos_raw:
        scores = repo_data.get("scores", {})
        overall = scores.get("综合", scores.get("overall", 0.0))
        if overall > max_repo_score:
            max_repo_score = overall

    max_news_score = 0.0
    for news_data_item in scored_news_raw:
        impact = news_data_item.get("impact_score", 0.0)
        if impact > max_news_score:
            max_news_score = impact

    if max_repo_score >= 9.0 or max_news_score >= 9.0:
        signal = "red"
    elif max_repo_score >= 7.0 or max_news_score >= 7.0:
        signal = "yellow"
    else:
        signal = "green"

    # 头条候选：取评分最高的项目
    headline_candidate = ""
    headline_story_hook = ""
    if top_repos:
        headline_candidate = top_repos[0].name
        headline_story_hook = top_repos[0].story_hook

    brief = WritingBrief(
        signal_strength_suggestion=signal,
        headline_candidate=headline_candidate,
        headline_story_hook=headline_story_hook,
        top_repos=top_repos,
        top_news=top_news,
        trend_summary=daily_summary.get("top_trend", ""),
        causal_explanation=daily_summary.get("causal_explanation", ""),
        data_support=daily_summary.get("data_support", ""),
        forward_looking=daily_summary.get("forward_looking", ""),
        hot_directions=daily_summary.get("hot_directions", []),
    )
    return brief


# ==================== 节点实现 ====================


def collect_github_node(state: dict[str, Any]) -> dict[str, Any]:
    """节点 1: GitHub 热门项目数据采集.

    直接调用 GitHubTrendingTool，由工具内部使用 CrewAI 完成关键词规划、趋势分析和重排行。
    """
    current_date = state.get("current_date", "")
    log.info(f"[collect_github] 开始采集 GitHub 热门 AI 项目 ({current_date})")

    try:
        from ai_trending.tools.github_trending_tool import GitHubTrendingTool

        tool = GitHubTrendingTool()
        github_summary = tool._run(query="AI", top_n=5)

        if not github_summary or github_summary.startswith("未能"):
            log.error("[collect_github] GitHubTrendingTool 未返回有效数据")
            return {
                "github_data": "GitHub 数据采集失败，无可用数据。",
                "errors": ["GitHub 数据采集: GitHubTrendingTool 未返回有效数据"],
            }

        log.info(f"[collect_github] 完成, 输出 {len(github_summary)} 字符")
        return {"github_data": github_summary}

    except Exception as e:
        log.error(f"[collect_github] 异常: {e}")
        return {
            "github_data": f"GitHub 数据采集异常: {e}",
            "errors": [f"collect_github: {e}"],
        }


def collect_news_node(state: dict[str, Any]) -> dict[str, Any]:
    """节点 2: AI 行业新闻数据采集.

    触发 AINewsTool（内部由 NewsCollectCrew 完成多源抓取 + LLM 筛选），
    直接返回已筛选好的新闻摘要，无需在节点层再做 LLM 处理。
    """
    current_date = state.get("current_date", "")
    log.info(f"[collect_news] 开始采集 AI 行业新闻 ({current_date})")

    try:
        from ai_trending.tools.ai_news_tool import AINewsTool

        # 一次调用，内部并发抓取 HN / Reddit / newsdata.io / 知乎，并由 CrewAI Agent 筛选
        news_summary = AINewsTool()._run(keywords="AI,LLM,AI Agent,大模型", top_n=30)

        if not news_summary or news_summary.startswith("❌"):
            log.error(f"[collect_news] AINewsTool 返回失败: {news_summary}")
            return {
                "news_data": "新闻数据采集失败，无可用数据。",
                "errors": [f"新闻数据采集: {news_summary}"],
            }

        log.info(f"[collect_news] 完成, 输出 {len(news_summary)} 字符")
        return {"news_data": news_summary}

    except Exception as e:
        log.error(f"[collect_news] 异常: {e}")
        return {
            "news_data": f"新闻数据采集异常: {e}",
            "errors": [f"collect_news: {e}"],
        }


def score_trends_node(state: dict[str, Any]) -> dict[str, Any]:
    """节点 3: 结构化评分.

    调用 TrendScoringCrew（Agent 机制）对采集数据进行量化评分，输出结构化 JSON。
    评分结果供 ReportWritingCrew 决定项目排序和详略。
    """
    current_date = state.get("current_date", "")
    github_data = state.get("github_data", "无数据")
    news_data = state.get("news_data", "无数据")

    log.info("[score_trends] 开始结构化评分")

    try:
        from ai_trending.crew.trend_scoring import TrendScoringCrew

        output, token_usage = TrendScoringCrew().run(
            github_data=github_data,
            news_data=news_data,
            current_date=current_date,
        )

        import json

        scoring_result = json.dumps(output.model_dump(), ensure_ascii=False)

        # 累加 token 用量到 State
        prev_usage = state.get("token_usage") or {}
        merged_usage = _merge_token_usage(prev_usage, token_usage, "score_trends")

        log.info(
            f"[score_trends] 完成，项目评分 {len(output.scored_repos)} 条，"
            f"新闻评分 {len(output.scored_news)} 条，"
            f"token 用量 {token_usage.get('total_tokens', 0)}"
        )
        return {"scoring_result": scoring_result, "token_usage": merged_usage}

    except Exception as e:
        log.error(f"[score_trends] TrendScoringCrew 调用失败: {e}")
        # 评分失败时，使用空 JSON 确保下游节点仍可运行
        fallback = '{"scored_repos": [], "scored_news": [], "daily_summary": {"top_trend": "评分数据不可用", "hot_directions": [], "overall_sentiment": "中性"}}'
        return {
            "scoring_result": fallback,
            "errors": [f"score_trends: TrendScoringCrew 失败: {e}"],
        }


def editorial_planning_node(state: dict[str, Any]) -> dict[str, Any]:
    """节点 3.5: 编辑部选题规划.

    调用 EditorialPlanningCrew（Agent 机制，light 档 LLM）做编辑决策：
    信号强度、头条选择、角度分配、Kill List、今日一句话。
    注入 TopicTracker 的近期话题上下文，帮助 Agent 避免连续雷同。
    输出 EditorialPlan 文本，供 write_report_node 使用。
    """
    current_date = state.get("current_date", "")
    scoring_result = state.get("scoring_result", "{}")

    log.info(f"[editorial_planning] 开始编辑选题规划 ({current_date})")

    # 获取近期话题上下文（失败时返回空字符串，不阻断）
    topic_context = ""
    try:
        from ai_trending.crew.report_writing.topic_tracker import TopicTracker

        topic_context = TopicTracker().get_topic_context()
        if topic_context and "无近期" not in topic_context:
            log.info("[editorial_planning] 已获取近期话题追踪上下文")
        else:
            log.info("[editorial_planning] 无近期话题追踪记录")
    except Exception as e:
        log.warning(f"[editorial_planning] TopicTracker 获取失败，跳过话题上下文: {e}")

    try:
        from ai_trending.crew.editorial_planning import EditorialPlanningCrew

        plan, token_usage = EditorialPlanningCrew().run(
            scoring_result=scoring_result,
            current_date=current_date,
            topic_context=topic_context,
        )

        editorial_plan_text = plan.format_for_prompt()

        # 累加 token 用量到 State
        prev_usage = state.get("token_usage") or {}
        merged_usage = _merge_token_usage(prev_usage, token_usage, "editorial_planning")

        log.info(
            f"[editorial_planning] 完成: signal={plan.signal_strength}, "
            f"headline={plan.headline.chosen_item}, "
            f"token 用量 {token_usage.get('total_tokens', 0)}"
        )
        return {"editorial_plan": editorial_plan_text, "token_usage": merged_usage}

    except Exception as e:
        log.error(f"[editorial_planning] EditorialPlanningCrew 失败: {e}")
        return {
            "editorial_plan": "",
            "errors": [f"editorial_planning: EditorialPlanningCrew 失败: {e}"],
        }


def write_report_node(state: dict[str, Any]) -> dict[str, Any]:
    """节点 4: 调用 ReportWritingCrew 撰写 Markdown 日报.

    通过 WritingBrief 将评分层的叙事字段（story_hook、so_what_analysis 等）
    显式传递给写作层，同时注入 EditorialPlan 编辑决策。
    由 ReportWritingCrew（Agent 机制）负责内容生成，确保格式规范和内容质量。
    节点只负责调用 Crew、保存文件、更新 State，不做任何内容修改。
    """
    current_date = state.get("current_date", "")
    github_data = state.get("github_data", "无数据")
    news_data = state.get("news_data", "无数据")
    scoring_result = state.get("scoring_result", "{}")
    editorial_plan = state.get("editorial_plan", "")

    log.info(f"[write_report] 开始撰写日报 ({current_date})")

    # 构建写作简报（WritingBrief）
    writing_brief = _build_writing_brief(scoring_result, github_data, news_data)
    writing_brief_text = writing_brief.format_for_prompt()
    log.info(
        f"[write_report] WritingBrief 构建完成: "
        f"{len(writing_brief.top_repos)} 个项目, "
        f"{len(writing_brief.top_news)} 条新闻, "
        f"信号强度建议={writing_brief.signal_strength_suggestion}"
    )
    if editorial_plan:
        log.info("[write_report] 已获取 EditorialPlan 编辑决策，将独立传递给写作层")
    else:
        log.info("[write_report] 无 EditorialPlan，写作层将自行决定编辑方向")

    # 获取风格记忆指导（失败不阻断主流程）
    style_guidance = ""
    try:
        from ai_trending.crew.report_writing.style_memory import StyleMemory

        style_guidance = StyleMemory().get_style_guidance()
        if style_guidance and "无风格记忆" not in style_guidance:
            log.info("[write_report] 已获取风格记忆指导")
        else:
            log.info("[write_report] 无风格记忆记录")
    except Exception as e:
        log.warning(f"[write_report] StyleMemory 获取失败，跳过风格记忆: {e}")

    # 获取上期回顾追踪数据（失败时返回空字符串，不阻断主流程）
    previous_report_context = ""
    try:
        from ai_trending.crew.report_writing.tracker import PreviousReportTracker

        previous_report_context = PreviousReportTracker().get_previous_report_context(
            current_date
        )
    except Exception as e:
        log.warning(f"[write_report] 上期回顾数据获取失败，将省略该 Section: {e}")

    # 合并写作简报和编辑决策 → 不再合并，独立传递给 Crew

    try:
        from ai_trending.crew.report_writing import ReportWritingCrew

        output, token_usage = ReportWritingCrew().run(
            github_data=github_data,
            news_data=news_data,
            scoring_result=scoring_result,
            current_date=current_date,
            previous_report_context=previous_report_context,
            writing_brief=writing_brief_text,
            editorial_plan=editorial_plan,
            style_guidance=style_guidance,
        )

        report = output.content

        # 保存报告到本地文件
        from pathlib import Path

        reports_dir = Path.cwd() / "reports"
        reports_dir.mkdir(parents=True, exist_ok=True)
        report_file = reports_dir / f"{current_date}.md"
        report_file.write_text(report, encoding="utf-8")

        # 累加 token 用量到 State
        prev_usage = state.get("token_usage") or {}
        merged_usage = _merge_token_usage(prev_usage, token_usage, "write_report")

        log.info(
            f"[write_report] 完成，报告已保存到 {report_file} ({len(report)} 字符)，"
            f"token 用量 {token_usage.get('total_tokens', 0)}"
        )

        # 记录今日话题到 TopicTracker（失败不阻断）
        try:
            from ai_trending.crew.report_writing.topic_tracker import TopicTracker

            tracker = TopicTracker()
            headline = tracker.extract_headline_from_report(report)
            keywords = tracker.extract_keywords_from_report(report)
            hook = tracker.extract_hook_from_report(report)
            tracker.record_today(
                date=current_date,
                headline=headline,
                keywords=keywords,
                hook=hook,
            )
        except Exception as e:
            log.warning(f"[write_report] TopicTracker 记录失败，不影响发布: {e}")

        # 格式校验问题记录到 errors（不阻断发布）
        errors: list[str] = []
        if output.validation_issues:
            for issue in output.validation_issues:
                errors.append(f"write_report/格式校验: {issue}")

        # 记录质量结果到 StyleMemory（失败不阻断）
        try:
            from ai_trending.crew.report_writing.style_memory import StyleMemory

            style_mem = StyleMemory()
            good_patterns, bad_patterns = style_mem.extract_patterns_from_report(report)
            style_mem.record_quality_result(
                date=current_date,
                validation_issues=output.validation_issues,
                good_patterns=good_patterns,
                bad_patterns=bad_patterns,
            )
        except Exception as e:
            log.warning(f"[write_report] StyleMemory 记录失败，不影响发布: {e}")

        result: dict[str, Any] = {"report_content": report, "token_usage": merged_usage}
        if errors:
            result["errors"] = errors
        return result

    except Exception as e:
        log.error(f"[write_report] 报告撰写失败: {e}")
        return {
            "report_content": f"# 🤖 AI 日报 · {current_date}\n\n报告生成失败: {e}",
            "errors": [f"write_report: ReportWritingCrew 失败: {e}"],
        }


def quality_review_node(state: dict[str, Any]) -> dict[str, Any]:
    """节点 4.5: 质量审核.

    调用 QualityReviewCrew（Agent 机制，light 档 LLM）对日报内容进行质量审核：
    检查虚构数据、事实一致性、风格合规、结构完整性。
    审核失败**不阻断**发布，只记录 warning。
    """
    current_date = state.get("current_date", "")
    report_content = state.get("report_content", "")
    scoring_result = state.get("scoring_result", "{}")

    log.info(f"[quality_review] 开始质量审核 ({current_date})")

    if not report_content or (
        report_content.startswith("# 🤖 AI 日报") and "报告生成失败" in report_content
    ):
        log.warning("[quality_review] 日报内容为空或生成失败，跳过审核")
        return {
            "quality_review": "跳过审核: 日报内容无效",
            "errors": ["quality_review: 日报内容为空或生成失败，跳过审核"],
        }

    try:
        from ai_trending.crew.quality_review import QualityReviewCrew

        review_result, token_usage = QualityReviewCrew().run(
            report_content=report_content,
            scoring_result=scoring_result,
            current_date=current_date,
        )

        # 格式化审核摘要
        review_summary = review_result.format_summary()

        # 累加 token 用量到 State
        prev_usage = state.get("token_usage") or {}
        merged_usage = _merge_token_usage(prev_usage, token_usage, "quality_review")

        log.info(
            f"[quality_review] 完成: passed={review_result.passed}, "
            f"issues={len(review_result.issues)} "
            f"(error={review_result.error_count}, warning={review_result.warning_count}), "
            f"token 用量 {token_usage.get('total_tokens', 0)}"
        )

        # 审核未通过时只记录 warning，不阻断发布
        errors: list[str] = []
        if not review_result.passed:
            errors.append(
                f"quality_review: 审核未通过 "
                f"(error={review_result.error_count}, warning={review_result.warning_count})"
            )
        elif review_result.warning_count > 0:
            errors.append(
                f"quality_review: 审核通过但有 {review_result.warning_count} 条 warning"
            )

        result: dict[str, Any] = {
            "quality_review": review_summary,
            "token_usage": merged_usage,
        }
        if errors:
            result["errors"] = errors
        return result

    except Exception as e:
        log.error(f"[quality_review] 质量审核异常: {e}")
        return {
            "quality_review": f"质量审核异常: {e}",
            "errors": [f"quality_review: {e}"],
        }


def publish_node(state: dict[str, Any]) -> dict[str, Any]:
    """节点 5: 多渠道发布.

    各发布步骤相互独立，任意一步失败不影响其他步骤继续执行。
    """
    report_content = state.get("report_content", "")
    current_date = state.get("current_date", "")
    author_name = state.get("author_name", "AI Trending Bot")
    article_title = f"AI 日报 | {current_date} 最热 AI 开源项目与行业新闻"

    publish_results: list[str] = []

    if (
        not report_content
        or report_content.startswith("# 🤖 AI 日报")
        and "报告生成失败" in report_content
    ):
        log.warning("[publish] 报告内容为空或生成失败，跳过发布")
        return {"publish_results": ["跳过发布: 报告内容无效"]}

    # --- Step 1: GitHub 发布 ---
    try:
        from ai_trending.tools.github_publish_tool import GitHubPublishTool

        result = GitHubPublishTool()._run(
            content=report_content,
            filename=f"{current_date}.md",
            commit_message=f"AI Trending Report - {current_date}",
        )
        first_line = result.splitlines()[0] if result else ""
        log.info(f"[publish] GitHub: {first_line}")
        publish_results.append(f"GitHub: {first_line}")
    except Exception as e:
        log.error(f"[publish] GitHub 发布失败: {e}")
        publish_results.append(f"GitHub: 失败 - {e}")

    # --- Step 2: 微信公众号 HTML + 草稿箱 ---
    try:
        from ai_trending.tools.wechat_publish_tool import WeChatPublishTool

        wechat_tool = WeChatPublishTool()
        wechat_result = wechat_tool._run(
            content=report_content,
            title=article_title,
            author=author_name,
        )
        first_line = wechat_result.splitlines()[0] if wechat_result else ""
        log.info(f"[publish] 微信HTML: {first_line}")
        publish_results.append(f"微信HTML: {first_line}")
    except Exception as e:
        log.error(f"[publish] 微信 HTML 生成失败: {e}")
        publish_results.append(f"微信HTML: 失败 - {e}")

    return {"publish_results": publish_results}
