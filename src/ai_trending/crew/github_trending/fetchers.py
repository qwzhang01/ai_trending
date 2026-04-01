"""GitHub Trending Crew — GitHub 搜索采集层。

职责：
  - 根据关键词构建 GitHub Search API 查询
  - 调用 GitHub Search API 聚合候选仓库
  - 基于程序特征计算启发式基础分
  - 去重、预排序，输出 GitHubSearchResult

不负责：
  - LLM 调用（由 CrewAI Agent 完成）
  - 排名合并（由 ranker.py 完成）
  - 输出格式化（由 formatter.py 完成）
"""

from __future__ import annotations

import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from typing import Any

from ai_trending.crew.github_trending.models import (
    GitHubSearchResult,
    RepoCandidate,
)
from ai_trending.crew.github_trending.utils import (
    TREND_TOPICS,
    is_excluded,
    unique_preserve_order,
)
from ai_trending.logger import get_logger
from ai_trending.retry import safe_request

log = get_logger("github_fetcher")


class GitHubFetcher:
    """GitHub 搜索采集器：关键词 → 查询构建 → API 调用 → 去重 → 预排序。

    对外只暴露 fetch(keywords, query) 一个方法。
    """

    def fetch(
        self,
        keywords: list[str],
        query: str,
    ) -> GitHubSearchResult:
        """程序化 GitHub 搜索：构建查询 → 调用 API → 过滤 → 去重 → 预排序。

        Args:
            keywords: 搜索关键词列表（由 KeywordPlanningCrew 或兜底策略提供）
            query:    用户原始主题（用于日志和 AI 相关性判断）

        Returns:
            GitHubSearchResult，包含候选仓库列表和搜索元信息
        """
        search_queries = self._build_search_queries(keywords)
        repos_raw = self._call_github_api(search_queries, query)
        total_found = len(repos_raw)

        from ai_trending.crew.util.dedup_cache import (
            DedupCache,  # 延迟导入，避免循环依赖
        )

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

        # 并发抓取 top-15 候选仓库的 README 摘要
        self._fetch_readmes_concurrently(candidates)

        # 星数快照：记录当日快照 + 填充增长数据
        self._track_star_growth(candidates)

        return GitHubSearchResult(
            candidates=candidates,
            keywords_used=keywords,
            total_found=total_found,
            dedup_filtered=dedup_filtered,
        )

    # ── 内部实现 ──────────────────────────────────────────────

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
                log.warning(
                    "GitHub API 速率限制即将耗尽，建议配置 GITHUB_TRENDING_TOKEN"
                )

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

    # ── 星数增长追踪 ─────────────────────────────────────────

    @staticmethod
    def _track_star_growth(candidates: list[RepoCandidate]) -> None:
        """记录当日星数快照并为候选仓库填充增长数据。

        使用 StarTracker 实现本地持久化星数快照。失败时仅记录日志，
        不影响主流程。
        """
        try:
            from ai_trending.crew.github_trending.star_tracker import StarTracker

            tracker = StarTracker()

            # 1. 记录当日快照
            repos_data = [
                {"full_name": c.full_name, "stars": c.stars} for c in candidates
            ]
            tracker.record_snapshot(repos_data)

            # 2. 查询历史快照，填充增长数据
            tracker.enrich_candidates(candidates, days=7)

            # 3. 清理过期快照
            tracker.cleanup_old_snapshots()

        except Exception as e:
            log.warning(f"星数增长追踪失败，不影响主流程: {type(e).__name__}: {e}")

    # ── README 摘要抓取 ──────────────────────────────────────

    def _fetch_readmes_concurrently(self, candidates: list[RepoCandidate]) -> None:
        """并发抓取候选仓库的 README 摘要，结果直接写入 candidate 对象。

        最多并发 5 个线程，总超时 30 秒。单个仓库失败不阻塞其他仓库。
        """
        if not candidates:
            return

        filled = 0
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = {
                executor.submit(self._fetch_readme_summary, repo.full_name): repo
                for repo in candidates
            }
            for future in as_completed(futures, timeout=60):
                repo = futures[future]
                try:
                    summary = future.result()
                    if summary:
                        repo.readme_summary = summary
                        filled += 1
                except Exception as e:
                    log.warning(
                        f"README 抓取失败({repo.full_name}): {type(e).__name__}: {e}"
                    )

        log.info(f"README 摘要抓取完成: {filled}/{len(candidates)} 个仓库获取成功")

    def _fetch_readme_summary(self, full_name: str) -> str:
        """获取仓库 README 的前 500 字符摘要。

        使用 GitHub Contents API 获取原始 README 文本，
        去除 badge 图片、链接标记等噪音后截取前 500 字符。

        Args:
            full_name: 仓库全名，如 "owner/repo"

        Returns:
            清洗后的 README 摘要，失败时返回空字符串
        """
        token = os.environ.get("GITHUB_TRENDING_TOKEN", "")
        headers = {"Accept": "application/vnd.github.raw+json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"

        resp = safe_request(
            "GET",
            f"https://api.github.com/repos/{full_name}/readme",
            headers=headers,
            timeout=10,
            max_retries=1,
            operation_name=f"readme({full_name})",
        )
        if resp is None:
            return ""

        content = resp.text[:2000]  # 限制读取量，降低内存开销
        return self._clean_readme(content)[:500]

    @staticmethod
    def _clean_readme(raw: str) -> str:
        """清洗 README 原始文本，去除 badge、图片链接、HTML 标签等噪音。

        处理逻辑：
        1. 移除 Markdown badge 图片 ([![...](img_url)](link_url))
        2. 移除普通 Markdown 图片 (![alt](url))
        3. 移除 HTML 标签 (<img>, <a>, <div> 等)
        4. 将 Markdown 链接 [text](url) 替换为纯文本 text
        5. 移除 Markdown 标题标记 (###)
        6. 压缩连续空白行
        7. 去除首尾空白

        Args:
            raw: README 原始 Markdown 文本

        Returns:
            清洗后的纯文本摘要
        """
        text = raw

        # 1. 移除 badge（带链接的图片）: [![alt](img)](link)
        text = re.sub(r"\[!\[.*?\]\(.*?\)\]\(.*?\)", "", text)

        # 2. 移除普通 Markdown 图片: ![alt](url)
        text = re.sub(r"!\[.*?\]\(.*?\)", "", text)

        # 3. 移除 HTML 标签（img, a, div, span, p, br, hr 等）
        text = re.sub(r"<[^>]+>", "", text)

        # 4. 将 Markdown 链接 [text](url) 替换为纯文本
        text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)

        # 5. 移除 Markdown 标题标记
        text = re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)

        # 6. 压缩连续空白行为单个换行
        text = re.sub(r"\n{3,}", "\n\n", text)

        return text.strip()
