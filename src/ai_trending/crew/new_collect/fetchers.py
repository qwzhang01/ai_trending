"""新闻抓取器 — 从多个来源并发抓取最新 AI / LLM / Agent 相关新闻.

数据源:
  - Hacker News  : hn.algolia.com 搜索 API，近 3 天
  - Reddit       : RSS Feed + Pullpush API 双通道
  - newsdata.io  : 需要 NEWSDATA_API_KEY 环境变量
  - 知乎热榜     : JSON API（需 ZHIHU_COOKIE）或 SSR 页面解析

本模块只负责「抓取 + 去重」，不做 LLM 筛选。
LLM 筛选由 crew/new_collect/crew.py 中的 CrewAI Agent 完成。
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import time
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta

from ai_trending.logger import get_logger
from ai_trending.retry import safe_request
from ai_trending.crew.util.dedup_cache import DedupCache, make_news_key

log = get_logger("news_fetcher")

# 完整的浏览器 User-Agent，避免被站点 403 封锁
_BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)

# AI 相关关键词（中英文混合），用于知乎等中文源的过滤
_AI_KEYWORDS_CN = [
    "ai", "人工智能", "llm", "大模型", "大语言模型",
    "gpt", "chatgpt", "agent", "智能体", "ai agent",
    "机器学习", "深度学习", "神经网络", "openai", "claude",
    "gemini", "copilot", "算力", "芯片", "transformer",
    "manus", "deepseek", "通义", "文心", "豆包", "kimi",
    "cursor", "midjourney", "sora", "生成式",
]


class NewsFetcher:
    """多源新闻抓取器，支持异步并发抓取."""

    def fetch(
        self,
        keywords: list[str],
        top_n: int = 30,
    ) -> tuple[list[dict], list[str]]:
        """同步入口：并发抓取所有渠道，返回 (去重后新闻列表, 来源统计).

        Args:
            keywords: 搜索关键词列表
            top_n: 每个渠道最多抓取条数

        Returns:
            (news_list, source_stats) — news_list 已按 score 降序排列并完成跨日去重
        """
        all_news, source_stats = asyncio.run(
            self._fetch_all_async(keywords, top_n)
        )

        log.info(f"新闻抓取完成 — {' | '.join(source_stats)}")

        if not all_news:
            return [], source_stats

        # 本次运行内去重（按标题）
        seen_titles: set[str] = set()
        unique_news: list[dict] = []
        for news in all_news:
            title_lower = news["title"].lower().strip()
            if title_lower not in seen_titles:
                seen_titles.add(title_lower)
                unique_news.append(news)

        # 按 score 降序排列
        unique_news.sort(key=lambda x: x.get("score", 0), reverse=True)

        # 跨日去重：过滤近期已出现过的新闻
        dedup = DedupCache("news_urls")
        new_news = dedup.filter_new(
            unique_news,
            key_fn=lambda n: make_news_key(n.get("url", ""), n.get("title", "")),
        )
        dedup.mark_seen([
            make_news_key(n.get("url", ""), n.get("title", ""))
            for n in new_news
        ])
        log.info(f"跨日去重缓存统计: {dedup.stats()}")

        # 全部重复时降级返回全量，避免空结果
        if not new_news:
            log.info("所有新闻均已在近期出现过，返回全量结果（不去重）")
            new_news = unique_news

        log.info(
            f"去重后 {len(unique_news)} 条，跨日过滤后 {len(new_news)} 条，"
            f"返回 Top {min(len(new_news), top_n)}"
        )
        return new_news[:top_n], source_stats

    # ------------------------------------------------------------------
    # 异步并发入口
    # ------------------------------------------------------------------
    async def _fetch_all_async(
        self, keyword_list: list[str], top_n: int
    ) -> tuple[list[dict], list[str]]:
        """并发抓取 4 个渠道，使用线程池执行同步 IO 任务."""
        newsdata_api_key = os.environ.get("NEWSDATA_API_KEY", "")

        loop = asyncio.get_event_loop()
        t_start = time.time()

        with ThreadPoolExecutor(max_workers=4) as executor:
            fut_hn = loop.run_in_executor(
                executor, self._fetch_hacker_news, keyword_list, top_n
            )
            fut_reddit = loop.run_in_executor(
                executor, self._fetch_reddit_news, keyword_list, top_n
            )
            fut_newsdata = (
                loop.run_in_executor(
                    executor, self._fetch_newsdata, keyword_list, top_n, newsdata_api_key
                )
                if newsdata_api_key
                else asyncio.sleep(0, result=[])
            )
            fut_zhihu = loop.run_in_executor(
                executor, self._fetch_zhihu_hot, keyword_list, top_n
            )

            results = await asyncio.gather(
                fut_hn, fut_reddit, fut_newsdata, fut_zhihu,
                return_exceptions=True,
            )

        total_elapsed = time.time() - t_start
        labels = ["HackerNews", "Reddit", "newsdata.io", "知乎"]
        all_news: list[dict] = []
        source_stats: list[str] = []

        for label, result in zip(labels, results):
            if isinstance(result, BaseException):
                log.warning(f"{label} 抓取异常: {result}")
                source_stats.append(f"{label}: 失败")
            else:
                if label == "newsdata.io" and not newsdata_api_key:
                    continue
                all_news.extend(result)
                source_stats.append(f"{label}: {len(result)} 条")

        source_stats.append(f"总耗时 {total_elapsed:.1f}s")
        return all_news, source_stats

    # ------------------------------------------------------------------
    # Hacker News
    # ------------------------------------------------------------------
    def _fetch_hacker_news(self, keywords: list[str], limit: int) -> list[dict]:
        """从 Hacker News 抓取热门 AI 相关帖子（近 3 天）."""
        news_list: list[dict] = []
        for keyword in keywords[:3]:
            resp = safe_request(
                "GET",
                "https://hn.algolia.com/api/v1/search",
                params={
                    "query": keyword,
                    "tags": "story",
                    "hitsPerPage": limit,
                    "numericFilters": f"created_at_i>{int((datetime.now() - timedelta(days=3)).timestamp())}",
                },
                timeout=15,
                max_retries=2,
                operation_name=f"HackerNews搜索({keyword})",
            )
            if resp is None:
                continue
            data = resp.json()
            for hit in data.get("hits", []):
                news_list.append(
                    {
                        "title": hit.get("title", ""),
                        "url": hit.get(
                            "url",
                            f"https://news.ycombinator.com/item?id={hit.get('objectID', '')}",
                        ),
                        "score": hit.get("points", 0),
                        "source": "Hacker News",
                        "summary": "",
                        "time": hit.get("created_at", "")[:10],
                    }
                )
        return news_list

    # ------------------------------------------------------------------
    # Reddit — RSS + Pullpush 双通道
    # ------------------------------------------------------------------
    def _fetch_reddit_news(self, keywords: list[str], limit: int) -> list[dict]:
        """从 Reddit 抓取 AI 相关帖子（RSS + Pullpush 双通道）."""
        news_list: list[dict] = []
        subreddits = ["artificial", "MachineLearning", "LocalLLaMA", "ChatGPT"]

        rss_count = 0
        for sub in subreddits:
            rss_items = self._fetch_reddit_rss(sub, keywords)
            news_list.extend(rss_items)
            rss_count += len(rss_items)

        pullpush_subreddits = ["artificial", "MachineLearning"]
        pullpush_count = 0
        for sub in pullpush_subreddits:
            pp_items = self._fetch_reddit_pullpush(sub, keywords, limit=5)
            news_list.extend(pp_items)
            pullpush_count += len(pp_items)

        log.info(f"Reddit 数据: RSS={rss_count}, Pullpush={pullpush_count}")
        return news_list

    def _fetch_reddit_rss(self, subreddit: str, keywords: list[str]) -> list[dict]:
        """通过 Reddit RSS Feed 获取最新帖子（无需认证）."""
        news_list: list[dict] = []
        resp = safe_request(
            "GET",
            f"https://www.reddit.com/r/{subreddit}/hot.rss",
            headers={"User-Agent": _BROWSER_UA},
            timeout=15,
            max_retries=2,
            operation_name=f"Reddit-RSS(r/{subreddit})",
        )
        if resp is None:
            return news_list

        try:
            root = ET.fromstring(resp.text)
        except ET.ParseError as e:
            log.warning(f"Reddit RSS r/{subreddit} XML 解析失败: {e}")
            return news_list

        ns = {"atom": "http://www.w3.org/2005/Atom"}
        entries = root.findall("atom:entry", ns)

        for entry in entries:
            title_elem = entry.find("atom:title", ns)
            title = title_elem.text if title_elem is not None else ""
            if not title:
                continue

            link_elem = entry.find("atom:link", ns)
            link = link_elem.get("href", "") if link_elem is not None else ""

            updated_elem = entry.find("atom:updated", ns)
            updated = (updated_elem.text or "")[:10] if updated_elem is not None else ""

            content_elem = entry.find("atom:content", ns)
            summary = ""
            if content_elem is not None and content_elem.text:
                text = re.sub(r"<[^>]+>", " ", content_elem.text)
                text = re.sub(r"&\w+;", " ", text)
                text = re.sub(r"\s+", " ", text).strip()
                summary = text[:200]

            news_list.append(
                {
                    "title": title,
                    "url": link,
                    "score": 20,
                    "source": f"Reddit r/{subreddit}",
                    "summary": summary,
                    "time": updated,
                }
            )

        return news_list

    def _fetch_reddit_pullpush(
        self, subreddit: str, keywords: list[str], limit: int = 5
    ) -> list[dict]:
        """通过 Pullpush API 获取 Reddit 近 7 天高分帖子."""
        news_list: list[dict] = []
        after_ts = int((datetime.now() - timedelta(days=7)).timestamp())
        resp = safe_request(
            "GET",
            "https://api.pullpush.io/reddit/search/submission/",
            params={
                "subreddit": subreddit,
                "size": limit,
                "sort": "desc",
                "sort_type": "score",
                "after": after_ts,
            },
            timeout=15,
            max_retries=2,
            operation_name=f"Pullpush(r/{subreddit})",
        )
        if resp is None:
            return news_list

        try:
            data = resp.json()
        except Exception as e:
            log.warning(f"Pullpush r/{subreddit} JSON 解析失败: {e}")
            return news_list

        for item in data.get("data", []):
            title = item.get("title", "")
            if not title:
                continue
            permalink = item.get("permalink", "")
            created_utc = item.get("created_utc", 0)
            news_list.append(
                {
                    "title": title,
                    "url": f"https://reddit.com{permalink}" if permalink else "",
                    "score": item.get("score", 0),
                    "source": f"Reddit r/{subreddit}",
                    "summary": (item.get("selftext", "") or "")[:200],
                    "time": datetime.fromtimestamp(created_utc).strftime("%Y-%m-%d")
                    if created_utc
                    else "",
                }
            )

        return news_list

    # ------------------------------------------------------------------
    # newsdata.io
    # ------------------------------------------------------------------
    def _fetch_newsdata(
        self, keywords: list[str], limit: int, api_key: str
    ) -> list[dict]:
        """通过 newsdata.io Latest News API 获取新闻（需要 NEWSDATA_API_KEY）."""
        news_list: list[dict] = []
        q = " OR ".join(keywords[:5])
        page_size = min(limit, 10)

        resp = safe_request(
            "GET",
            "https://newsdata.io/api/1/latest",
            params={
                "apikey": api_key,
                "q": q,
                "language": "en",
                "size": page_size,
            },
            timeout=15,
            max_retries=2,
            operation_name="newsdata.io",
        )

        if resp is None:
            return news_list

        data = resp.json()
        if data.get("status") != "success":
            log.warning(
                f"newsdata.io 返回非 success: {data.get('status')} — {data.get('results', {})}"
            )
            return news_list

        for article in data.get("results", []):
            title = article.get("title", "")
            if not title:
                continue
            news_list.append(
                {
                    "title": title,
                    "url": article.get("link", ""),
                    "score": 50,
                    "source": article.get("source_name", "newsdata.io"),
                    "summary": (article.get("description", "") or "")[:300],
                    "time": (article.get("pubDate", "") or "")[:10],
                }
            )
        return news_list

    # ------------------------------------------------------------------
    # 知乎热榜
    # ------------------------------------------------------------------
    def _fetch_zhihu_hot(self, keywords: list[str], limit: int) -> list[dict]:
        """从知乎获取 AI / LLM / Agent 相关热门内容."""
        all_keywords = list(set(
            [kw.lower() for kw in _AI_KEYWORDS_CN]
            + [kw.lower() for kw in keywords]
        ))

        zhihu_cookie = os.environ.get("ZHIHU_COOKIE", "")
        if zhihu_cookie:
            items = self._fetch_zhihu_api(zhihu_cookie, all_keywords, limit)
            if items:
                return items

        # SSR 方式也传入 Cookie，避免知乎要求登录时返回 403
        items = self._fetch_zhihu_ssr(all_keywords, limit, cookie=zhihu_cookie)
        if items:
            return items

        log.info("知乎热榜获取失败（需要登录）。可设置 ZHIHU_COOKIE 环境变量启用。")
        return []

    def _fetch_zhihu_api(
        self, cookie: str, keywords: list[str], limit: int
    ) -> list[dict]:
        """通过知乎热榜 JSON API 获取数据（需要 Cookie 认证）."""
        news_list: list[dict] = []
        headers = {
            "User-Agent": _BROWSER_UA,
            "Accept": "application/json",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Referer": "https://www.zhihu.com/hot",
            "Cookie": cookie,
        }

        resp = safe_request(
            "GET",
            "https://www.zhihu.com/api/v3/feed/topstory/hot-lists/total",
            headers=headers,
            params={"limit": 50},
            timeout=15,
            max_retries=2,
            operation_name="知乎热榜API",
        )
        if resp is None:
            return news_list

        try:
            data = resp.json()
        except Exception as e:
            log.warning(f"知乎热榜 JSON 解析失败: {e}")
            return news_list

        if "error" in data:
            log.warning(f"知乎 API 鉴权失败: {data['error'].get('message', '')}")
            return news_list

        for item in data.get("data", []):
            target = item.get("target", {})
            title = target.get("title", "") or target.get("title_area", {}).get("text", "")
            if not title:
                card = item.get("card_content", {})
                title = card.get("title", "")
            if not title:
                continue

            title_lower = title.lower()
            if not any(kw in title_lower for kw in keywords):
                continue

            metrics = item.get("detail_text", "") or item.get("metrics_area", {}).get("text", "")
            heat_score = self._parse_zhihu_heat(metrics)

            question_id = target.get("id", "")
            url = f"https://www.zhihu.com/question/{question_id}" if question_id else ""
            excerpt = target.get("excerpt", "") or target.get("detail", "")

            news_list.append(
                {
                    "title": title,
                    "url": url,
                    "score": heat_score,
                    "source": "知乎热榜",
                    "summary": (excerpt or "")[:200],
                    "time": datetime.now().strftime("%Y-%m-%d"),
                }
            )

        news_list.sort(key=lambda x: x.get("score", 0), reverse=True)
        return news_list[:limit]

    def _fetch_zhihu_ssr(self, keywords: list[str], limit: int, cookie: str = "") -> list[dict]:
        """从知乎热榜 HTML 页面提取 SSR 渲染的 initialData JSON."""
        news_list: list[dict] = []
        headers = {
            "User-Agent": _BROWSER_UA,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        }
        # 携带 Cookie 可绕过知乎的登录墙（403）
        if cookie:
            headers["Cookie"] = cookie

        resp = safe_request(
            "GET",
            "https://www.zhihu.com/hot",
            headers=headers,
            timeout=15,
            max_retries=2,
            operation_name="知乎热榜SSR",
        )
        if resp is None:
            return news_list

        match = re.search(
            r'<script\s+id="js-initialData"\s+type="text/json">(.*?)</script>',
            resp.text,
        )
        if not match:
            log.info("知乎热榜页面未找到 initialData（可能需要登录）")
            return news_list

        try:
            init_data = json.loads(match.group(1))
        except json.JSONDecodeError as e:
            log.warning(f"知乎 initialData JSON 解析失败: {e}")
            return news_list

        hot_list = (
            init_data.get("initialState", {})
            .get("topstory", {})
            .get("hotList", [])
        )

        for item in hot_list:
            target = item.get("target", {})
            title_area = target.get("titleArea", {})
            title = title_area.get("text", "")
            if not title:
                continue

            title_lower = title.lower()
            if not any(kw in title_lower for kw in keywords):
                continue

            metrics_area = target.get("metricsArea", {})
            heat_text = metrics_area.get("text", "")
            heat_score = self._parse_zhihu_heat(heat_text)

            link = target.get("link", {}).get("url", "")
            excerpt_area = target.get("excerptArea", {})
            excerpt = excerpt_area.get("text", "")

            news_list.append(
                {
                    "title": title,
                    "url": link,
                    "score": heat_score,
                    "source": "知乎热榜",
                    "summary": (excerpt or "")[:200],
                    "time": datetime.now().strftime("%Y-%m-%d"),
                }
            )

        news_list.sort(key=lambda x: x.get("score", 0), reverse=True)
        return news_list[:limit]

    @staticmethod
    def _parse_zhihu_heat(text: str) -> int:
        """解析知乎热度文本为数值，如 '2345 万热度' -> 23450000."""
        if not text:
            return 30
        m = re.search(r"([\d.]+)\s*万", text)
        if m:
            return int(float(m.group(1)) * 10000)
        m = re.search(r"([\d,]+)", text)
        if m:
            return int(m.group(1).replace(",", ""))
        return 30
