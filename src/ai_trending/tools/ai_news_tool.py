"""AI News Tool — 从多个来源抓取最新 AI / LLM / Agent 相关新闻."""

import os
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from typing import Type

from crewai.tools import BaseTool
from pydantic import BaseModel, Field

from ai_trending.logger import get_logger
from ai_trending.retry import safe_request
from ai_trending.tools.dedup_cache import DedupCache, make_news_key

log = get_logger("news_tool")

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


class AINewsInput(BaseModel):
    """Input schema for AINewsTool."""

    keywords: str = Field(
        default="AI,LLM,AI Agent",
        description="逗号分隔的搜索关键词，例如 'AI,LLM,AI Agent,大模型'",
    )
    top_n: int = Field(
        default=10,
        description="返回前 N 条最相关的新闻，默认 10",
    )


class AINewsTool(BaseTool):
    """从 Hacker News、Reddit、newsdata.io、知乎等来源抓取最新 AI 新闻."""

    name: str = "ai_news_tool"
    description: str = (
        "从 Hacker News、Reddit、newsdata.io 和知乎等来源抓取最新的 AI、大模型、AI Agent 相关新闻。"
        "返回新闻标题、摘要、来源和链接。"
    )
    args_schema: Type[BaseModel] = AINewsInput

    def _run(self, keywords: str = "AI,LLM,AI Agent", top_n: int = 10) -> str:
        """抓取新闻并返回格式化结果."""
        keyword_list = [k.strip() for k in keywords.split(",") if k.strip()]
        all_news: list[dict] = []
        source_stats: list[str] = []

        # 1. Hacker News — 免费，无需 API Key
        t0 = time.time()
        hn_news = self._fetch_hacker_news(keyword_list, top_n)
        all_news.extend(hn_news)
        source_stats.append(f"HackerNews: {len(hn_news)} 条 ({time.time() - t0:.1f}s)")

        # 2. Reddit — RSS + Pullpush 双通道（修复 403）
        t0 = time.time()
        reddit_news = self._fetch_reddit_news(keyword_list, top_n)
        all_news.extend(reddit_news)
        source_stats.append(f"Reddit: {len(reddit_news)} 条 ({time.time() - t0:.1f}s)")

        # 3. newsdata.io (如果有 key)
        newsdata_api_key = os.environ.get("NEWSDATA_API_KEY", "")
        if newsdata_api_key:
            t0 = time.time()
            newsdata_news = self._fetch_newsdata(keyword_list, top_n, newsdata_api_key)
            all_news.extend(newsdata_news)
            source_stats.append(f"newsdata.io: {len(newsdata_news)} 条 ({time.time() - t0:.1f}s)")

        # 4. 知乎 — AI/LLM/Agent 相关话题
        t0 = time.time()
        zhihu_news = self._fetch_zhihu_hot(keyword_list, top_n)
        all_news.extend(zhihu_news)
        source_stats.append(f"知乎: {len(zhihu_news)} 条 ({time.time() - t0:.1f}s)")

        log.info(f"新闻抓取完成 — {' | '.join(source_stats)}")

        if not all_news:
            log.warning("所有新闻源均未返回数据")
            return "未能获取到最新的 AI 相关新闻。请检查网络连接。"

        # 本次运行内去重（按标题）
        seen_titles: set[str] = set()
        unique_news: list[dict] = []
        for news in all_news:
            title_lower = news["title"].lower().strip()
            if title_lower not in seen_titles:
                seen_titles.add(title_lower)
                unique_news.append(news)

        # 按 score 排序
        unique_news.sort(key=lambda x: x.get("score", 0), reverse=True)

        # ── 跨日去重：过滤昨天及之前已出现过的新闻 ──────────────────────
        dedup = DedupCache("news_urls")
        new_news = dedup.filter_new(
            unique_news,
            key_fn=lambda n: make_news_key(n.get("url", ""), n.get("title", "")),
        )
        # 将本次新条目标记为已见
        dedup.mark_seen([
            make_news_key(n.get("url", ""), n.get("title", ""))
            for n in new_news
        ])
        log.info(f"跨日去重缓存统计: {dedup.stats()}")

        # 如果全部都是重复的，降级返回全量（避免空结果）
        if not new_news:
            log.info("所有新闻均已在近期出现过，返回全量结果（不去重）")
            new_news = unique_news

        top_news = new_news[:top_n]
        log.info(f"去重后 {len(unique_news)} 条，跨日过滤后 {len(new_news)} 条，返回 Top {len(top_news)}")

        # 格式化输出
        output = f"## 最新 AI 热门新闻 Top {len(top_news)}\n"
        output += f"数据时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
        output += f"搜索关键词: {', '.join(keyword_list)}\n\n"

        for i, news in enumerate(top_news, 1):
            output += f"### {i}. {news['title']}\n"
            output += f"- **来源**: {news.get('source', '未知')}\n"
            output += f"- **链接**: {news.get('url', '无')}\n"
            output += f"- **热度**: {news.get('score', 0)} 分\n"
            if news.get("summary"):
                output += f"- **摘要**: {news['summary']}\n"
            output += f"- **时间**: {news.get('time', '未知')}\n\n"

        return output

    # ------------------------------------------------------------------
    # Hacker News
    # ------------------------------------------------------------------
    def _fetch_hacker_news(self, keywords: list[str], limit: int) -> list[dict]:
        """从 Hacker News 抓取热门 AI 相关帖子."""
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
                        "url": hit.get("url", f"https://news.ycombinator.com/item?id={hit.get('objectID', '')}"),
                        "score": hit.get("points", 0),
                        "source": "Hacker News",
                        "summary": "",
                        "time": hit.get("created_at", "")[:10],
                    }
                )
        return news_list

    # ------------------------------------------------------------------
    # Reddit — 修复 403: RSS + Pullpush 双通道
    # ------------------------------------------------------------------
    def _fetch_reddit_news(self, keywords: list[str], limit: int) -> list[dict]:
        """从 Reddit 抓取 AI 相关帖子.

        Reddit 自 2023 年起封锁了 .json 公开端点（返回 403）。
        解决方案采用双通道：
          通道 A: RSS Feed（/hot.rss）— 获取最新帖子，但无 score
          通道 B: Pullpush API — 获取高分帖子（第三方索引）
        两个通道合并去重，确保数据完整。
        """
        news_list: list[dict] = []
        subreddits = ["artificial", "MachineLearning", "LocalLLaMA", "ChatGPT"]

        # --- 通道 A: RSS Feed ---
        rss_count = 0
        for sub in subreddits:
            rss_items = self._fetch_reddit_rss(sub, keywords)
            news_list.extend(rss_items)
            rss_count += len(rss_items)

        # --- 通道 B: Pullpush API（高分帖子补充）---
        pullpush_count = 0
        for sub in subreddits:
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

            # 提取摘要（从 content HTML 中简单去标签）
            content_elem = entry.find("atom:content", ns)
            summary = ""
            if content_elem is not None and content_elem.text:
                text = re.sub(r"<[^>]+>", " ", content_elem.text)
                text = re.sub(r"&\w+;", " ", text)  # 去除 HTML 实体
                text = re.sub(r"\s+", " ", text).strip()
                summary = text[:200]

            # RSS 无 score，给一个默认分数（按 subreddit 热度调整）
            news_list.append(
                {
                    "title": title,
                    "url": link,
                    "score": 20,  # RSS 默认分数，排序时低于有真实 score 的
                    "source": f"Reddit r/{subreddit}",
                    "summary": summary,
                    "time": updated,
                }
            )

        return news_list

    def _fetch_reddit_pullpush(
        self, subreddit: str, keywords: list[str], limit: int = 5
    ) -> list[dict]:
        """通过 Pullpush API（Pushshift 替代）获取 Reddit 近 7 天高分帖子."""
        news_list: list[dict] = []
        # 只获取近 7 天的帖子，避免返回多年前的历史数据
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
    # newsdata.io — 免费版直接用基础参数
    # ------------------------------------------------------------------
    def _fetch_newsdata(
        self, keywords: list[str], limit: int, api_key: str
    ) -> list[dict]:
        """通过 newsdata.io Latest News API 获取新闻.

        注意：`timeframe`, `removeduplicate`, `prioritydomain` 是付费版功能，
        免费版传入会返回 422 UNPROCESSABLE ENTITY，因此直接使用基础参数。
        """
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
            log.warning(f"newsdata.io 返回非 success: {data.get('status')} — {data.get('results', {})}")
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
    # 知乎 — 多通道获取 AI 热门内容
    # ------------------------------------------------------------------
    def _fetch_zhihu_hot(self, keywords: list[str], limit: int) -> list[dict]:
        """从知乎获取 AI / LLM / Agent 相关热门内容.

        知乎 API 自 2024 年起要求登录认证（Cookie/Token）。
        策略：
          通道 A: 知乎热榜 JSON API（需要环境变量 ZHIHU_COOKIE）
          通道 B: 知乎热榜 SSR 页面解析（从 HTML 中提取 initialData）
        如果都失败，优雅降级返回空列表。
        """
        # 构建完整的 AI 关键词列表
        all_keywords = list(set(
            [kw.lower() for kw in _AI_KEYWORDS_CN]
            + [kw.lower() for kw in keywords]
        ))

        # 通道 A: 如果有 ZHIHU_COOKIE，尝试 JSON API
        zhihu_cookie = os.environ.get("ZHIHU_COOKIE", "")
        if zhihu_cookie:
            items = self._fetch_zhihu_api(zhihu_cookie, all_keywords, limit)
            if items:
                return items

        # 通道 B: 从知乎热榜页面 SSR 提取数据
        items = self._fetch_zhihu_ssr(all_keywords, limit)
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

        # 检查是否鉴权失败
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

            # 过滤：标题必须包含 AI 相关关键词
            title_lower = title.lower()
            if not any(kw in title_lower for kw in keywords):
                continue

            # 热度
            metrics = item.get("detail_text", "") or item.get("metrics_area", {}).get("text", "")
            heat_score = self._parse_zhihu_heat(metrics)

            # 链接
            question_id = target.get("id", "")
            url = f"https://www.zhihu.com/question/{question_id}" if question_id else ""

            # 摘要
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

    def _fetch_zhihu_ssr(self, keywords: list[str], limit: int) -> list[dict]:
        """从知乎热榜 HTML 页面提取 SSR 渲染的 initialData JSON."""
        news_list: list[dict] = []
        headers = {
            "User-Agent": _BROWSER_UA,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        }

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

        # 从 HTML 中提取 <script id="js-initialData"> 中的 JSON
        match = re.search(
            r'<script\s+id="js-initialData"\s+type="text/json">(.*?)</script>',
            resp.text,
        )
        if not match:
            log.info("知乎热榜页面未找到 initialData（可能需要登录）")
            return news_list

        import json

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

            # 过滤 AI 相关
            title_lower = title.lower()
            if not any(kw in title_lower for kw in keywords):
                continue

            # 热度
            metrics_area = target.get("metricsArea", {})
            heat_text = metrics_area.get("text", "")
            heat_score = self._parse_zhihu_heat(heat_text)

            # 链接
            link = target.get("link", {}).get("url", "")

            # 摘要
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
            return 30  # 默认分数
        # 匹配 "xxx 万热度" 格式
        m = re.search(r"([\d.]+)\s*万", text)
        if m:
            return int(float(m.group(1)) * 10000)
        # 匹配纯数字
        m = re.search(r"([\d,]+)", text)
        if m:
            return int(m.group(1).replace(",", ""))
        return 30
