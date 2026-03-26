"""GitHub Trending Crew — 排名合并层。

职责：
  - 将 CrewAI 趋势分析分与程序基础分合并
  - 决定最终输出数量（3-5 个）
  - 提取热点信号（CrewAI 失败时从 topic 兜底）
  - 标记已输出仓库到去重缓存

不负责：
  - GitHub API 调用（由 fetchers.py 完成）
  - LLM 调用（由 CrewAI Agent 完成）
  - 输出格式化（由 formatter.py 完成）
"""

from __future__ import annotations

from typing import Any

from ai_trending.crew.github_trending.models import (
    GitHubSearchResult,
    GitHubTrendRanking,
    RankedGitHubRepo,
)
from ai_trending.crew.github_trending.utils import model_to_dict
from ai_trending.logger import get_logger

log = get_logger("github_ranker")


class GitHubRanker:
    """排名合并器：将 CrewAI 分析结果与程序基础分合并，选出最终仓库列表。

    对外只暴露 merge(search_result, ranking, requested_count, query) 一个方法。
    """

    def merge(
        self,
        search_result: GitHubSearchResult,
        ranking: GitHubTrendRanking | None,
        requested_count: int,
        query: str,
    ) -> tuple[list[dict[str, Any]], str, list[str]]:
        """合并 CrewAI 排名结果与程序基础分，选出最终结果。

        Args:
            search_result:   程序化搜索结果（含候选仓库和启发式分）
            ranking:         CrewAI 趋势分析输出（可为 None，触发兜底）
            requested_count: 期望输出数量（3-5）
            query:           用户原始主题（用于日志）

        Returns:
            (final_repos, summary, hot_signals)
        """
        repos = self._search_result_to_raw(search_result)
        return self._merge_rankings(repos, ranking, requested_count, query)

    # ── 内部实现 ──────────────────────────────────────────────

    def _search_result_to_raw(
        self, search_result: GitHubSearchResult
    ) -> list[dict[str, Any]]:
        """将 GitHubSearchResult 转换为 raw dict 列表（供合并排名使用）。"""
        return [
            {
                "full_name": c.full_name,
                "description": c.description,
                "language": c.language,
                "stargazers_count": c.stars,
                "topics": c.topics,
                "created_at": c.created_at,
                "updated_at": c.updated_at,
                "html_url": c.html_url,
                "_match_count": c.match_count,
                "_heuristic_score": c.heuristic_score,
            }
            for c in search_result.candidates
        ]

    def _merge_rankings(
        self,
        repos: list[dict[str, Any]],
        ranking: GitHubTrendRanking | None,
        requested_count: int,
        query: str,
    ) -> tuple[list[dict[str, Any]], str, list[str]]:
        """将 CrewAI 排名结果与程序基础分合并，选出最终结果。"""
        repo_index = {repo["full_name"].lower(): repo for repo in repos}
        analysis_map: dict[str, RankedGitHubRepo] = {}

        if ranking is not None:
            for ranked_repo in ranking.ranked_repos:
                key = ranked_repo.full_name.strip().lower()
                if key in repo_index and key not in analysis_map:
                    analysis_map[key] = ranked_repo

        merged: list[dict[str, Any]] = []
        for repo in repos:
            repo_copy = dict(repo)
            key = repo_copy["full_name"].lower()
            analysis = analysis_map.get(key)
            repo_copy["_final_score"] = self._calculate_final_score(repo_copy, analysis)
            if analysis is not None:
                repo_copy["_crew_analysis"] = model_to_dict(analysis)
            merged.append(repo_copy)

        merged.sort(key=lambda r: r.get("_final_score", 0), reverse=True)
        final_count = self._select_output_count(merged, requested_count)
        selected = merged[:final_count]

        from ai_trending.crew.util.dedup_cache import DedupCache  # 延迟导入，避免循环依赖
        dedup = DedupCache("github_repos", keep_days=30)
        dedup.mark_seen([repo["full_name"] for repo in selected])

        hot_signals: list[str] = []
        if ranking is not None:
            hot_signals = [s.strip() for s in ranking.hot_signals if s.strip()]
        if not hot_signals:
            hot_signals = self._fallback_hot_signals(selected)

        summary = ranking.summary.strip() if ranking and ranking.summary else ""
        if not summary:
            log.warning(f"趋势排名未返回 summary，query='{query}'")

        return selected, summary, hot_signals[:5]

    def _calculate_final_score(
        self,
        repo: dict[str, Any],
        analysis: RankedGitHubRepo | None,
    ) -> float:
        """合并程序特征分和 CrewAI 分析分。"""
        # 直接复用 fetchers.py 中已计算并缓存的基础分，避免重复计算
        base_score = repo.get("_heuristic_score", 0.0)
        if analysis is None:
            return base_score

        crew_score = (
            analysis.trend_score * 0.45
            + analysis.innovation_score * 0.25
            + analysis.execution_score * 0.15
            + analysis.ecosystem_score * 0.15
        )
        final_score = crew_score * 0.75 + base_score * 0.25
        if not analysis.representative:
            final_score -= 1.5
        return max(0.0, min(final_score, 10.0))

    def _select_output_count(
        self,
        repos: list[dict[str, Any]],
        requested_count: int,
    ) -> int:
        """根据综合分决定最终输出 3-5 个项目。"""
        available = len(repos)
        if available == 0:
            return 0
        if available <= 3:
            return available

        strong_count = sum(1 for r in repos if r.get("_final_score", 0) >= 7.5)
        medium_count = sum(1 for r in repos if r.get("_final_score", 0) >= 6.5)

        if strong_count >= requested_count:
            return requested_count
        if strong_count >= 3:
            return strong_count
        if medium_count >= 3:
            return min(medium_count, requested_count)
        return min(available, 3)

    def _fallback_hot_signals(self, repos: list[dict[str, Any]]) -> list[str]:
        """CrewAI 分析失败时，从 topic 中提取热点信号。"""
        topic_counter: dict[str, int] = {}
        for repo in repos:
            for topic in repo.get("topics", [])[:8]:
                normalized = topic.strip().lower()
                if normalized:
                    topic_counter[normalized] = topic_counter.get(normalized, 0) + 1

        if topic_counter:
            sorted_topics = sorted(
                topic_counter.items(), key=lambda x: (-x[1], x[0])
            )
            return [t for t, _ in sorted_topics[:5]]
        return []
