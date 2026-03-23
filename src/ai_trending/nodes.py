"""LangGraph 节点实现 — 每个节点是流水线中的一个独立步骤.

节点职责:
  - collect_github_node: 调用 GitHubTrendingTool 抓取热门项目（工具内部使用 CrewAI 规划与分析）
  - collect_news_node:   触发 NewsCollectCrew（多源抓取 + CrewAI Agent LLM 筛选）
  - score_trends_node:   调用 LLM 结构化评分（核心差异点）
  - write_report_node:   调用 ReportWritingCrew 撰写 Markdown 日报
  - publish_node:        调用 publish tools 推送到各渠道

设计原则:
  - 每个节点只读取需要的 state 字段，写入自己负责的字段
  - Tool 调用和 LLM 调用分离，便于独立测试
  - GitHub 采集的 CrewAI 编排下沉到工具内部，节点只负责接线
  - 评分节点直接调用 LiteLLM（JSON 模式，精确 prompt 控制）
  - 报告撰写节点调用 ReportWritingCrew（Agent 机制，格式规范强约束）
"""

from __future__ import annotations

from typing import Any

from ai_trending.llm_client import call_llm_with_usage
from ai_trending.logger import get_logger

log = get_logger("nodes")


# ==================== Prompt 模板 ====================

SCORING_SYSTEM_PROMPT = """你是一位数据驱动的技术分析师，专注于 AI 领域的量化评估。
你的评分标准严格、客观、一致，不受项目知名度影响。
你只输出结构化 JSON，不输出任何多余文字。"""

SCORING_PROMPT_TEMPLATE = """基于以下采集到的 GitHub 项目数据和行业新闻，对每个项目/新闻进行结构化评分。

## GitHub 项目数据
{github_data}

## 行业新闻数据
{news_data}

## 重要约束（违反则输出无效）
- 只对上方数据中真实存在的项目和新闻评分，绝不虚构任何项目名称、仓库地址或新闻标题
- repo 字段必须与原始数据中的仓库路径完全一致（格式：owner/repo_name）
- 如果原始数据为空或无效，scored_repos / scored_news 返回空数组

## 评分要求

对每个 GitHub 项目，输出 JSON:
{{
  "repo": "owner/repo_name（必须与原始数据完全一致）",
  "name": "项目显示名称",
  "url": "GitHub 完整 URL",
  "stars": 数字（从原始数据中读取，不得估算或虚构）,
  "language": "主要编程语言",
  "is_ai": true/false,
  "category": "Agent框架 / 推理框架 / 多模态 / 开发工具 / 数据处理 / 模型微调 / 评测基准 / 应用集成",
  "scores": {{
    "热度": 0-10,
    "技术前沿性": 0-10,
    "成长潜力": 0-10,
    "综合": 0-10
  }},
  "one_line_reason": "一句话说明，不超过 30 字，说清楚技术价值或应用场景"
}}

评分标准:
- 热度: Star 数 >50k=9-10, >20k=7-8, >10k=5-6, >5k=3-4, <5k=1-2
- 技术前沿性: 是否引入新架构/新范式。已有技术封装、UI 套壳或教程类不超过 3 分
- 成长潜力: 架构设计合理性、社区活跃度、近期更新频率
- 综合: 热度 30% + 前沿性 40% + 潜力 30%，保留一位小数

对每条行业新闻，输出 JSON:
{{
  "title": "新闻标题（保留原文，不改写）",
  "url": "新闻链接",
  "source": "来源名称",
  "category": "大厂动态 / 技术突破 / 开源生态 / 投融资 / 行业观察 / 产品发布 / 政策监管",
  "impact_score": 0-10,
  "impact_reason": "一句话说明行业影响，不超过 35 字，必须是判断句"
}}

最终输出严格 JSON 格式:
{{
  "scored_repos": [ ... ],
  "scored_news": [ ... ],
  "daily_summary": {{
    "top_trend": "今天最值得关注的一个趋势，不超过 30 字，有数据支撑",
    "hot_directions": ["技术方向1（3-6字）", "技术方向2", "技术方向3"],
    "overall_sentiment": "积极/中性/消极"
  }}
}}

不要输出任何 JSON 以外的内容。

当前日期: {current_date}"""


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

    使用 LLM(default) JSON 模式对采集数据进行量化评分，输出结构化 JSON。
    评分结果供 ReportWritingCrew 决定项目排序和详略。
    """
    current_date = state.get("current_date", "")
    github_data = state.get("github_data", "无数据")
    news_data = state.get("news_data", "无数据")

    log.info("[score_trends] 开始结构化评分")

    try:
        scoring_result, usage = call_llm_with_usage(
            prompt=SCORING_PROMPT_TEMPLATE.format(
                github_data=github_data,
                news_data=news_data,
                current_date=current_date,
            ),
            system_prompt=SCORING_SYSTEM_PROMPT,
            tier="default",
            max_tokens=4096,
            json_mode=True,
        )

        log.info(f"[score_trends] 完成, 输出 {len(scoring_result)} 字符, tokens={usage.get('total_tokens', 0)}")
        return {
            "scoring_result": scoring_result,
            "token_usage": usage,
        }

    except Exception as e:
        log.error(f"[score_trends] 评分失败: {e}")
        # 评分失败时，使用空 JSON 确保下游节点仍可运行
        fallback = '{"scored_repos": [], "scored_news": [], "daily_summary": {"top_trend": "评分数据不可用", "hot_directions": [], "overall_sentiment": "中性"}}'
        return {
            "scoring_result": fallback,
            "errors": [f"score_trends: {e}"],
        }


def write_report_node(state: dict[str, Any]) -> dict[str, Any]:
    """节点 4: 调用 ReportWritingCrew 撰写 Markdown 日报.

    由 ReportWritingCrew（Agent 机制）负责内容生成，确保格式规范和内容质量。
    节点只负责调用 Crew、保存文件、更新 State，不做任何内容修改。
    """
    current_date = state.get("current_date", "")
    github_data = state.get("github_data", "无数据")
    news_data = state.get("news_data", "无数据")
    scoring_result = state.get("scoring_result", "{}")

    log.info(f"[write_report] 开始撰写日报 ({current_date})")

    try:
        from ai_trending.crew.report_writing import ReportWritingCrew

        output = ReportWritingCrew().run(
            github_data=github_data,
            news_data=news_data,
            scoring_result=scoring_result,
            current_date=current_date,
        )

        report = output.content

        # 保存报告到本地文件
        from pathlib import Path
        reports_dir = Path.cwd() / "reports"
        reports_dir.mkdir(parents=True, exist_ok=True)
        report_file = reports_dir / f"{current_date}.md"
        report_file.write_text(report, encoding="utf-8")

        log.info(f"[write_report] 完成，报告已保存到 {report_file} ({len(report)} 字符)")

        # 格式校验问题记录到 errors（不阻断发布）
        errors: list[str] = []
        if output.validation_issues:
            for issue in output.validation_issues:
                errors.append(f"write_report/格式校验: {issue}")

        result: dict[str, Any] = {"report_content": report}
        if errors:
            result["errors"] = errors
        return result

    except Exception as e:
        log.error(f"[write_report] 报告撰写失败: {e}")
        return {
            "report_content": f"# 🤖 AI 日报 · {current_date}\n\n报告生成失败: {e}",
            "errors": [f"write_report: ReportWritingCrew 失败: {e}"],
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

    if not report_content or report_content.startswith("# 🤖 AI 日报") and "报告生成失败" in report_content:
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