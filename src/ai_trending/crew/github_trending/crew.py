"""GitHub Trending Crew — 编排入口。

架构：
  两个独立的标准 @CrewBase Crew 按顺序执行：
    1. KeywordPlanningCrew  — 关键词规划（light 模型）
    2. TrendRankingCrew     — 趋势分析排名（default 模型）

  GitHub 搜索采集由程序化方法直接完成（无需 LLM 参与）。

  GitHubTrendingOrchestrator 负责：
    - 依次执行关键词规划 → 程序化搜索 → 趋势排名
    - 传递中间结果（关键词 → 搜索 → 排名）
    - 兜底降级策略
    - 最终结果合并输出

使用方式：
  1. 独立 Agent 运行（命令行 / 脚本）：
       orchestrator = GitHubTrendingOrchestrator()
       text = orchestrator.run_as_agent(query="AI", top_n=5)
       print(text)

     或直接执行本文件：
       python -m ai_trending.crew.github_trending.crew

  2. 作为 LangGraph Tool 使用：
       from ai_trending.crew.github_trending import create_langgraph_tool
       tool = create_langgraph_tool()
       # 在 LangGraph 节点中调用
       result = tool.invoke({"query": "AI", "top_n": 5})

对外暴露：
  - GitHubTrendingOrchestrator.run(query, top_n)        → 原始数据元组
  - GitHubTrendingOrchestrator.run_as_agent(query, top_n) → 格式化文本（独立运行）
  - GitHubTrendingOrchestrator.as_langgraph_tool()      → LangGraph StructuredTool
  - create_langgraph_tool()                             → 模块级工厂函数（推荐）
"""

from __future__ import annotations

import json
import os
import re
import time
from datetime import datetime, timedelta
from typing import Any

from ai_trending.crew.github_trending.keyword_planning.crew import KeywordPlanningCrew
from ai_trending.crew.github_trending.models import (
    GitHubSearchPlan,
    GitHubSearchResult,
    GitHubTrendRanking,
    RankedGitHubRepo,
    RepoCandidate,
)
from ai_trending.crew.github_trending.trend_ranking.crew import TrendRankingCrew
from ai_trending.crew.github_trending.utils import (
    TREND_KEYWORD_MAP,
    TREND_TOPICS,
    is_excluded,
    is_searchable_keyword,
    model_to_dict,
    unique_preserve_order,
)
from ai_trending.logger import get_logger
from ai_trending.retry import safe_request

log = get_logger("github_crew")


class GitHubTrendingOrchestrator:
    """GitHub 趋势发现编排器。

    流程：关键词规划（CrewAI）→ GitHub 搜索采集（程序化）→ 趋势排名（CrewAI）。
    对外只暴露 run(query, top_n) 一个方法。
    """

    # ── 唯一对外入口 ─────────────────────────────────────────

    def run(
        self,
        query: str = "AI",
        top_n: int = 5,
    ) -> tuple[list[dict[str, Any]], str, list[str], list[str]]:
        """执行完整的 GitHub 趋势发现流程。

        Args:
            query: 用户主题，例如 "AI"、"MCP"、"AI Agent"
            top_n: 期望输出数量（3-5）

        Returns:
            (final_repos, summary, hot_signals, keywords_used)
        """
        requested_count = max(3, min(top_n, 5))
        current_date = datetime.now().strftime("%Y-%m-%d")

        # Step 1: 关键词规划 Crew
        keywords = self._run_keyword_planning(query, current_date)

        # Step 2: 程序化 GitHub 搜索采集
        search_result = self._programmatic_search(keywords,query)
        candidates_raw = self._search_result_to_raw(search_result)

        if not candidates_raw:
            log.warning(f"未搜索到与 '{query}' 相关的热门仓库")
            return [], "", [], keywords

        # Step 3: 趋势排名 Crew
        candidates_json = json.dumps(
            [model_to_dict(c) for c in search_result.candidates],
            ensure_ascii=False,
            indent=2,
        )
        ranking = self._run_trend_ranking(
            query, current_date, requested_count, candidates_json
        )

        # Step 4: 合并排名，选出最终结果
        final_repos, summary, hot_signals = self._merge_rankings(
            candidates_raw, ranking, requested_count, query
        )

        return final_repos, summary, hot_signals, keywords

    # ── Step 实现 ────────────────────────────────────────────

    def _run_keyword_planning(self, query: str, current_date: str) -> list[str]:
        """Step 1：KeywordPlanningCrew 规划关键词，失败时使用兜底策略。"""
        try:
            result = KeywordPlanningCrew().crew().kickoff(
                inputs={"query": query, "current_date": current_date}
            )
            plan = self._extract_pydantic_output(result, GitHubSearchPlan)
            if plan and plan.keywords:
                keywords = self._sanitize_keywords(plan.keywords, query)
                log.info(f"CrewAI 关键词规划成功: {query} -> {keywords}")
                return keywords
        except Exception as e:
            log.warning(f"CrewAI 关键词规划失败: {e}")

        fallback = self._default_keywords_for_query(query)
        log.info(f"关键词规划使用兜底策略: {query} -> {fallback}")
        return fallback

    def _run_trend_ranking(
        self,
        query: str,
        current_date: str,
        requested_count: int,
        candidates_json: str,
    ) -> GitHubTrendRanking | None:
        """Step 3：TrendRankingCrew 趋势分析与重排行。"""
        try:
            result = TrendRankingCrew().crew().kickoff(
                inputs={
                    "query": query,
                    "current_date": current_date,
                    "requested_count": requested_count,
                    "candidates_json": candidates_json,
                }
            )
            ranking = self._extract_pydantic_output(result, GitHubTrendRanking)
            if ranking:
                log.info(f"CrewAI 趋势分析成功: 产出 {len(ranking.ranked_repos)} 个排序结果")
                return ranking
        except Exception as e:
            log.warning(f"CrewAI 趋势分析失败: {e}")
        return None

    # ── GitHub 搜索核心逻辑 ────────────────────────────────────────────

    def _programmatic_search(
        self,
        keywords: list[str],
        query: str,
    ) -> GitHubSearchResult:
        """程序化 GitHub 搜索：构建查询 → 调用 API → 过滤 → 去重 → 预排序。"""
        search_queries = self._build_search_queries(keywords)
        repos_raw = self._call_github_api(search_queries, query)
        total_found = len(repos_raw)

        from ai_trending.crew.util.dedup_cache import DedupCache  # 延迟导入，避免循环依赖
        dedup = DedupCache("github_repos", keep_days=30)
        deduped = dedup.filter_new(repos_raw, key_fn=lambda r: r["full_name"])
        log.info(f"GitHub 去重缓存统计: {dedup.stats()}")
        dedup_filtered = total_found - len(deduped)

        candidates_raw = deduped if deduped else repos_raw
        if not deduped:
            log.info("最近 30 天候选项全部出现过，回退到全量候选继续分析")

        for repo in candidates_raw:
            repo["_heuristic_score"] = self._calculate_base_score(repo)
        candidates_raw.sort(key=lambda r: r["_heuristic_score"], reverse=True)

        candidates = [
            RepoCandidate(
                full_name=r.get("full_name", ""),
                description=r.get("description", "") or "",
                language=r.get("language", "未知") or "未知",
                stars=r.get("stargazers_count", 0),
                topics=r.get("topics", []),
                created_at=(r.get("created_at", "") or "")[:10],
                updated_at=(r.get("updated_at", "") or "")[:10],
                html_url=r.get("html_url", ""),
                match_count=r.get("_match_count", 1),
                heuristic_score=round(r.get("_heuristic_score", 0.0), 2),
            )
            for r in candidates_raw[:15]
        ]

        return GitHubSearchResult(
            candidates=candidates,
            keywords_used=keywords,
            total_found=total_found,
            dedup_filtered=dedup_filtered,
        )

    def _build_search_queries(self, keywords: list[str]) -> list[str]:
        """根据关键词构建 GitHub 搜索查询列表。"""
        recent_active = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
        recent_created = (datetime.now() - timedelta(days=180)).strftime("%Y-%m-%d")

        queries: list[str] = []
        for keyword in keywords[:5]:
            topic_keyword = re.sub(
                r"[^a-z0-9\-]", "", keyword.lower().replace(" ", "-")
            )
            if topic_keyword:
                queries.append(
                    f"topic:{topic_keyword} stars:>80 created:>{recent_created}"
                )
            quoted = f'"{keyword}"'
            queries.extend(
                [
                    f"{quoted} in:name,description stars:>80 pushed:>{recent_active}",
                    f"{quoted} in:readme stars:>150 pushed:>{recent_active}",
                    f"{keyword} stars:>300 pushed:>{recent_active}",
                ]
            )

        # 仅当关键词覆盖 AI 方向时，才追加 AI 热点固定查询，避免非 AI 主题引入噪音
        ai_related_keywords = {k.lower() for k in keywords}
        is_ai_query = any(
            kw in " ".join(ai_related_keywords)
            for kw in ("ai", "llm", "agent", "mcp", "multimodal", "inference", "rag")
        )
        if is_ai_query:
            queries.extend(
                [
                    f"topic:mcp-server stars:>80 created:>{recent_created}",
                    f"topic:ai-agent stars:>120 created:>{recent_created}",
                    f"topic:multimodal stars:>120 created:>{recent_created}",
                    f"mcp server in:name,description stars:>150 pushed:>{recent_active}",
                    f"agentic workflow in:name,description stars:>150 pushed:>{recent_active}",
                    f"llm inference in:name,description stars:>300 pushed:>{recent_active}",
                ]
            )
        return unique_preserve_order(queries)

    def _call_github_api(
        self,
        search_queries: list[str],
        base_query: str,
    ) -> list[dict[str, Any]]:
        """调用 GitHub Search API，聚合候选仓库。"""
        token = os.environ.get("GITHUB_TRENDING_TOKEN", "")
        headers = {"Accept": "application/vnd.github+json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        else:
            log.warning("GITHUB_TRENDING_TOKEN 未设置，GitHub Search API 速率限制较低")

        repo_map: dict[str, dict[str, Any]] = {}
        started_at = time.time()

        for search_query in search_queries:
            response = safe_request(
                "GET",
                "https://api.github.com/search/repositories",
                headers=headers,
                params={
                    "q": search_query,
                    "sort": "stars",
                    "order": "desc",
                    "per_page": 20,
                },
                timeout=30,
                max_retries=3,
                operation_name=f"GitHub搜索({base_query})",
            )
            if response is None:
                continue
            if response.status_code == 422:
                log.warning(f"GitHub 搜索语法错误(422)，跳过: {search_query[:80]}")
                continue

            remaining = int(response.headers.get("X-RateLimit-Remaining", 99))
            if remaining <= 1:
                log.warning("GitHub API 速率限制即将耗尽，建议配置 GITHUB_TRENDING_TOKEN")

            try:
                payload = response.json()
            except ValueError as e:
                log.warning(f"GitHub 搜索结果 JSON 解析失败: {e}")
                continue

            for item in payload.get("items", []):
                full_name = (item.get("full_name") or "").strip()
                if not full_name or is_excluded(item):
                    continue
                key = full_name.lower()
                existing = repo_map.get(key)
                if existing is None:
                    item["_match_count"] = 1
                    item["_matched_queries"] = [search_query]
                    repo_map[key] = item
                else:
                    existing["_match_count"] = existing.get("_match_count", 1) + 1
                    existing.setdefault("_matched_queries", []).append(search_query)

        elapsed = time.time() - started_at
        repos = list(repo_map.values())
        log.info(
            f"GitHub 搜索完成: 主题='{base_query}', 候选={len(repos)} 个, 耗时={elapsed:.1f}s"
        )
        return repos

    def _calculate_base_score(self, repo: dict[str, Any]) -> float:
        """基于程序特征计算基础分，用于候选预排序和兜底排序。"""
        recent_active = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
        recent_created = (datetime.now() - timedelta(days=180)).strftime("%Y-%m-%d")

        stars = repo.get("stargazers_count", 0)
        updated_at = (repo.get("updated_at", "") or "")[:10]
        created_at = (repo.get("created_at", "") or "")[:10]
        topics = {topic.lower() for topic in repo.get("topics", [])}
        match_count = repo.get("_match_count", 1)

        score = 0.0
        score += min(stars / 2000, 4.0)
        score += 2.0 if updated_at >= recent_active else 0.0
        score += 1.5 if created_at >= recent_created else 0.0
        score += 1.8 if topics & TREND_TOPICS else 0.0
        score += min(match_count * 0.5, 1.2)
        return min(score, 10.0)

    # ── 排名合并 ─────────────────────────────────────────────

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
        # 直接复用 _programmatic_search 中已计算并缓存的基础分，避免重复计算
        base_score = repo.get("_heuristic_score", self._calculate_base_score(repo))
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

    # ── 关键词辅助方法 ────────────────────────────────────────

    def _default_keywords_for_query(self, base_query: str) -> list[str]:
        """兜底关键词策略。"""
        normalized = base_query.strip().lower()
        fallback = TREND_KEYWORD_MAP.get(
            normalized,
            [base_query, "AI agent", "MCP", "LLM inference"],
        )
        merged: list[str] = []
        if is_searchable_keyword(base_query):
            merged.append(base_query.strip())
        merged.extend(fallback)
        return unique_preserve_order(merged)[:5]

    def _sanitize_keywords(self, keywords: list[str], base_query: str) -> list[str]:
        """清洗 CrewAI 输出的关键词，确保可用于 GitHub 检索。"""
        cleaned: list[str] = []
        for keyword in keywords:
            for part in re.split(r"[,/\n]", keyword):
                candidate = part.strip().strip('"').strip("'")
                if candidate and is_searchable_keyword(candidate):
                    cleaned.append(candidate)

        merged: list[str] = []
        if is_searchable_keyword(base_query):
            merged.append(base_query.strip())
        merged.extend(cleaned)
        merged.extend(self._default_keywords_for_query(base_query))
        return unique_preserve_order(merged)[:5]

    # ── CrewOutput 解析辅助 ───────────────────────────────────

    def _extract_pydantic_output(self, output: Any, model_type: type) -> Any:
        """从 CrewOutput / TaskOutput 中提取结构化结果。"""
        direct = getattr(output, "pydantic", None)
        if isinstance(direct, model_type):
            return direct

        tasks_output = getattr(output, "tasks_output", None) or []
        for task_output in reversed(tasks_output):
            task_model = getattr(task_output, "pydantic", None)
            if isinstance(task_model, model_type):
                return task_model
            raw_text = getattr(task_output, "raw", None)
            parsed = self._parse_model_from_text(raw_text, model_type)
            if parsed is not None:
                return parsed

        raw_text = getattr(output, "raw", None)
        return self._parse_model_from_text(raw_text, model_type)

    def _parse_model_from_text(self, text: str | None, model_type: type) -> Any:
        """从原始文本中兜底解析 Pydantic 结果。"""
        if not text:
            return None

        candidates = [text.strip()]
        json_block = re.search(r"(\{.*\}|\[.*\])", text.strip(), re.DOTALL)
        if json_block:
            candidates.append(json_block.group(1).strip())

        for candidate in candidates:
            normalized = re.sub(r"^```(?:json)?\s*", "", candidate)
            normalized = re.sub(r"\s*```$", "", normalized).strip()
            try:
                if hasattr(model_type, "model_validate_json"):
                    return model_type.model_validate_json(normalized)
                return model_type.parse_raw(normalized)
            except Exception:
                continue
        return None

    # ── 独立 Agent 运行入口 ───────────────────────────────────

    def run_as_agent(
        self,
        query: str = "AI",
        top_n: int = 5,
    ) -> str:
        """独立 Agent 运行入口：执行完整流程并返回格式化文本。

        适用场景：命令行调用、脚本直接运行、单元测试。

        Args:
            query: 用户主题，例如 "AI"、"MCP"、"AI Agent"
            top_n:  期望输出数量（3-5）

        Returns:
            格式化的 Markdown 文本；失败时返回错误提示字符串。

        示例::

            orchestrator = GitHubTrendingOrchestrator()
            print(orchestrator.run_as_agent(query="MCP", top_n=5))
        """
        log.info(f"[run_as_agent] 开始执行，主题='{query}', top_n={top_n}")
        try:
            final_repos, summary, hot_signals, keywords = self.run(
                query=query, top_n=top_n
            )
        except Exception as e:
            log.error(f"[run_as_agent] 执行失败: {e}")
            return f"❌ GitHub 趋势发现失败: {e}"

        if not final_repos:
            return (
                f"未能从 GitHub 搜索到与 '{query}' 相关的热门仓库。\n"
                "请检查网络连接、GITHUB_TRENDING_TOKEN 或模型配置。"
            )

        return self._format_text_output(final_repos, query, keywords, summary, hot_signals)

    def _format_text_output(
        self,
        repos: list[dict[str, Any]],
        query: str,
        keywords: list[str],
        summary: str,
        hot_signals: list[str],
    ) -> str:
        """将运行结果格式化为 Markdown 文本（供 run_as_agent 和 LangGraph tool 共用）。"""
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
            innovation_score = analysis.get("innovation_score", repo.get("_final_score", 0.0))
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

    # ── LangGraph Tool 入口 ───────────────────────────────────

    def as_langgraph_tool(self):
        """返回可直接注册到 LangGraph 的 StructuredTool。

        适用场景：在 LangGraph 节点或 ReAct Agent 中将本 Crew 作为工具调用。

        Returns:
            langchain_core.tools.StructuredTool 实例。

        示例::

            tool = GitHubTrendingOrchestrator().as_langgraph_tool()
            # 在 LangGraph 节点中
            result = tool.invoke({"query": "AI", "top_n": 5})
        """
        try:
            from langchain_core.tools import StructuredTool
            from pydantic import BaseModel, Field as PydanticField
        except ImportError as e:
            raise ImportError(
                "as_langgraph_tool() 需要 langchain-core，请执行: pip install langchain-core"
            ) from e

        orchestrator = self  # 捕获当前实例，供闭包使用

        class _GitHubTrendingInput(BaseModel):
            query: str = PydanticField(
                default="AI",
                description="搜索主题，例如 'AI'、'LLM'、'AI Agent'、'MCP'",
            )
            top_n: int = PydanticField(
                default=5,
                description="最终返回 3-5 个项目，默认 5",
            )

        def _run_tool(query: str = "AI", top_n: int = 5) -> str:
            return orchestrator.run_as_agent(query=query, top_n=top_n)

        return StructuredTool.from_function(
            func=_run_tool,
            name="github_trending_tool",
            description=(
        "通过 CrewAI 编排两个 Agent（关键词规划 → 趋势分析）+ 程序化 GitHub 搜索，"
                "发现最近最能代表 AI 发展趋势的 3-5 个 GitHub 开源项目。"
                "返回格式化的 Markdown 文本，包含项目评分、亮点和趋势判断。"
            ),
            args_schema=_GitHubTrendingInput,
        )


# ── 模块级工厂函数（推荐在 LangGraph 中使用）────────────────────

def create_langgraph_tool():
    """创建并返回 GitHub 趋势发现的 LangGraph StructuredTool。

    这是在 LangGraph 节点或 ReAct Agent 中使用本 Crew 的推荐方式。

    Returns:
        langchain_core.tools.StructuredTool 实例。

    示例::

        from ai_trending.crew.github_trending import create_langgraph_tool

        tool = create_langgraph_tool()
        result = tool.invoke({"query": "MCP", "top_n": 5})
    """
    return GitHubTrendingOrchestrator().as_langgraph_tool()


# ── 独立运行入口 ──────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    import sys

    from ai_trending.logger import setup_logging

    parser = argparse.ArgumentParser(
        description="GitHub 热门 AI 开源项目发现（独立 Agent 模式）"
    )
    parser.add_argument(
        "--query", default="AI", help="搜索主题，例如 'AI'、'MCP'、'AI Agent'（默认: AI）"
    )
    parser.add_argument(
        "--top-n", type=int, default=5, help="返回项目数量 3-5（默认: 5）"
    )
    parser.add_argument("--verbose", action="store_true", help="输出详细日志")
    args = parser.parse_args()

    setup_logging(level="DEBUG" if args.verbose else "INFO")

    result = GitHubTrendingOrchestrator().run_as_agent(
        query=args.query, top_n=args.top_n
    )
    print(result)
    sys.exit(0 if result and not result.startswith("❌") else 1)