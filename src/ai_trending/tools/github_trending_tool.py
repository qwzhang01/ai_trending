"""GitHub Trending Tool — 工具层入口。

职责：
  1. 定义 BaseTool 接口（GitHubTrendingTool）
  2. 格式化最终输出

所有业务逻辑（关键词规划、GitHub 搜索采集、趋势排名、去重缓存）
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from crewai.tools import BaseTool
from pydantic import BaseModel, Field

from ai_trending.crew.github_trending import GitHubTrendingOrchestrator
from ai_trending.crew.github_trending.utils import EXCLUDE_REPOS
from ai_trending.crew.github_trending.utils import is_excluded as _is_excluded
from ai_trending.logger import get_logger

log = get_logger("github_tool")

# 重新导出，供测试和外部模块使用
__all__ = ["GitHubTrendingInput", "GitHubTrendingTool", "EXCLUDE_REPOS", "_is_excluded"]


class GitHubTrendingInput(BaseModel):
    """Input schema for GitHubTrendingTool."""

    query: str = Field(
        default="AI",
        description="搜索主题，例如 'AI'、'LLM'、'AI Agent'、'MCP'",
    )
    top_n: int = Field(
        default=5,
        description="最终返回 3-5 个项目，默认 5",
    )


class GitHubTrendingTool(BaseTool):
    """使用 CrewAI 驱动 GitHub 趋势项目发现和重排行。"""

    name: str = "github_trending_tool"
    description: str = (
        "通过 CrewAI 编排三个 Agent（关键词规划 → GitHub 搜索采集 → 趋势分析），"
        "发现最近最能代表 AI 发展趋势的 3-5 个 GitHub 开源项目。"
    )
    args_schema: type[BaseModel] = GitHubTrendingInput

    def _run(self, query: str = "AI", top_n: int = 5) -> str:
        orchestrator = GitHubTrendingOrchestrator()
        final_repos, summary, hot_signals, keywords = orchestrator.run(
            query=query, top_n=top_n
        )

        if not final_repos:
            return (
                f"未能从 GitHub 搜索到与 '{query}' 相关的热门仓库。"
                "请检查网络连接、GitHub Token 或模型配置。"
            )

        return self._format_results(final_repos, query, keywords, summary, hot_signals)

    # ── 格式化输出 ────────────────────────────────────────────

    def _format_results(
        self,
        repos: list[dict[str, Any]],
        query: str,
        keywords: list[str],
        summary: str,
        hot_signals: list[str],
    ) -> str:
        """格式化最终结果为 Markdown 文本。"""
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
            reason = analysis.get(
                "reason", "基于近期活跃度、技术方向和社区信号综合入选"
            )
            trend_score = analysis.get("trend_score", repo.get("_final_score", 0.0))
            innovation_score = analysis.get(
                "innovation_score", repo.get("_final_score", 0.0)
            )
            execution_score = analysis.get(
                "execution_score", repo.get("_final_score", 0.0)
            )
            ecosystem_score = analysis.get(
                "ecosystem_score", repo.get("_final_score", 0.0)
            )

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
