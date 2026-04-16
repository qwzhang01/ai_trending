"""GitHub Trending Crew — 输出格式化层。

职责：
  - 将最终仓库列表格式化为 Markdown 文本
  - 供 run_as_agent 和 LangGraph Tool 共用

不负责：
  - 任何数据采集或 LLM 调用
  - 排名合并逻辑
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

# 默认 TOPIC_TRACKER 路径
_DEFAULT_TRACKER_PATH = Path("output/TOPIC_TRACKER.md")


def _get_prev_appearances(
    repo_name: str,
    tracker_path: Path | None = None,
    days: int = 7,
) -> str:
    """从 TOPIC_TRACKER.md 中查找项目名是否在近 N 天内出现过。

    Args:
        repo_name: 仓库名（owner/repo 或 repo 短名）
        tracker_path: TOPIC_TRACKER.md 路径，默认 output/TOPIC_TRACKER.md
        days: 查找窗口天数，默认 7 天

    Returns:
        描述字符串，例如：
          - "首次上榜"
          - "2026-04-14(头条), 2026-04-12(热点)"
          - "数据不可用"
    """
    path = tracker_path or _DEFAULT_TRACKER_PATH
    try:
        if not path.exists():
            return "首次上榜"

        content = path.read_text(encoding="utf-8")
        cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

        # 提取仓库短名（owner/repo → repo）
        short_name = (
            repo_name.split("/")[-1].lower() if "/" in repo_name else repo_name.lower()
        )

        appearances: list[str] = []
        in_table = False

        for line in content.splitlines():
            stripped = line.strip()
            if stripped.startswith("| 日期"):
                in_table = True
                continue
            if stripped.startswith("|---"):
                continue
            if in_table and stripped.startswith("|"):
                parts = [p.strip() for p in stripped.split("|") if p.strip()]
                if len(parts) < 4:
                    continue
                row_date = parts[0]
                row_headline = parts[1].lower()
                row_keywords = parts[2].lower()
                # 过滤日期窗口
                if row_date < cutoff:
                    continue
                # 检查项目名是否出现在头条或关键词中
                if short_name in row_headline:
                    appearances.append(f"{row_date}(头条)")
                elif short_name in row_keywords:
                    appearances.append(f"{row_date}(热点)")
            elif in_table and not stripped.startswith("|"):
                in_table = False

        if not appearances:
            return "首次上榜"
        return ", ".join(appearances)

    except Exception:
        return "数据不可用"


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
        # 追加 README 摘要（截断到 300 字）
        readme_raw = repo.get("readme_summary", "") or ""
        readme_display = readme_raw[:300] if readme_raw else "（暂无）"
        output += f"**README摘要**: {readme_display}\n"
        # 追加 7 日星数增长
        stars_growth = repo.get("stars_growth_7d")
        growth_display = (
            f"+{stars_growth}" if stars_growth is not None else "（暂无历史数据）"
        )
        output += f"**7日增长**: {growth_display}\n"
        # 追加历史出现记录（从 TOPIC_TRACKER 查找）
        prev_appearances = _get_prev_appearances(repo.get("full_name", ""))
        output += f"**历史出现**: {prev_appearances}\n"
        output += f"🔗 {repo.get('html_url', '')}\n\n"

    return output
