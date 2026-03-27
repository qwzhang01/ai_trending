"""GitHub Trending Crew — 输出格式化层。

职责：
  - 将最终仓库列表格式化为 Markdown 文本
  - 供 run_as_agent 和 LangGraph Tool 共用

不负责：
  - 任何数据采集或 LLM 调用
  - 排名合并逻辑
"""

from __future__ import annotations

from datetime import datetime
from typing import Any


def format_text_output(
    repos: list[dict[str, Any]],
    query: str,
    keywords: list[str],
    summary: str,
    hot_signals: list[str],
) -> str:
    """将运行结果格式化为 Markdown 文本（供 run_as_agent 和 LangGraph Tool 共用）。

    Args:
        repos:       最终选出的仓库列表（含 _crew_analysis、_final_score 等字段）
        query:       用户原始主题
        keywords:    本次实际使用的搜索关键词
        summary:     CrewAI 趋势总结（可为空字符串）
        hot_signals: 热点信号列表（可为空列表）

    Returns:
        格式化的 Markdown 字符串
    """
    output = f"## GitHub 热门 AI 开源项目 Top {len(repos)}\n"
    output += f"数据时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
    output += f"主题: {query}\n"
    output += f"搜索关键词: {', '.join(keywords)}\n"
    output += "分析方式: CrewAI（关键词规划 + GitHub 搜索采集 + 趋势打分）\n"
    output += "去重窗口: 最近 30 天仅过滤已输出过的仓库\n\n"

    output += "### 趋势判断\n"
    output += f"- **结论**: {summary}\n"
    if hot_signals:
        output += f"- **热点信号**: {'、'.join(hot_signals)}\n"
    output += "\n"

    for index, repo in enumerate(repos, 1):
        analysis = repo.get("_crew_analysis", {})
        stars = repo.get("stargazers_count", 0)
        language = repo.get("language", "未知") or "未知"
        description = repo.get("description", "无描述") or "无描述"
        created_at = (repo.get("created_at", "") or "")[:10]
        updated_at = (repo.get("updated_at", "") or "")[:10]
        topics = ", ".join(repo.get("topics", [])[:5]) or "无"
        reason = analysis.get("reason", "基于近期活跃度、技术方向和社区信号综合入选")
        trend_score = analysis.get("trend_score", repo.get("_final_score", 0.0))
        innovation_score = analysis.get(
            "innovation_score", repo.get("_final_score", 0.0)
        )
        execution_score = analysis.get("execution_score", repo.get("_final_score", 0.0))
        ecosystem_score = analysis.get("ecosystem_score", repo.get("_final_score", 0.0))

        output += f"### {index}. {repo['full_name']} | ⭐ {stars:,} | {language}\n"
        output += f"**定位**: {description}\n"
        output += (
            "**评分**: "
            f"综合 {repo.get('_final_score', 0.0):.1f}/10 | "
            f"趋势代表性 {trend_score:.1f}/10 | "
            f"技术前沿性 {innovation_score:.1f}/10 | "
            f"工程落地性 {execution_score:.1f}/10 | "
            f"生态信号 {ecosystem_score:.1f}/10\n"
        )
        output += f"**亮点**: {reason}\n"
        output += f"**时间**: 创建 {created_at} | 更新 {updated_at}\n"
        output += (
            f"**补充**: 命中查询 {repo.get('_match_count', 1)} 次 | 标签 {topics}\n"
        )
        output += f"🔗 {repo.get('html_url', '')}\n\n"

    return output
