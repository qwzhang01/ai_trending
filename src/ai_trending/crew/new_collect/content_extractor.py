"""新闻正文提取器 — 从 URL 提取正文内容摘要。

基于 trafilatura 库，支持大多数新闻网站的正文提取。
失败时返回空字符串，不抛出异常，不影响上游流程。

职责：
  - 从给定 URL 下载网页并提取正文文本
  - 截取指定长度的摘要
  - 处理超时、网络错误等异常

不负责：
  - LLM 调用或语义判断
  - 判断内容是否有价值（由 CrewAI Agent 完成）
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed

import trafilatura

from ai_trending.logger import get_logger

log = get_logger("content_extractor")

# 单条提取的最大字符数（下载的 HTML 内容限制）
_MAX_DOWNLOAD_CHARS = 500_000

# 正文提取超时（秒）
_FETCH_TIMEOUT = 10


def extract_article_content(url: str, max_chars: int = 500) -> str:
    """从 URL 提取正文内容的前 N 个字符。

    使用 trafilatura 库提取网页正文，去除导航栏、广告、评论等噪音。
    失败时返回空字符串，不抛出异常。

    Args:
        url: 新闻文章 URL
        max_chars: 返回的最大字符数，默认 500

    Returns:
        提取后的正文摘要，失败时返回空字符串
    """
    if not url or not url.startswith(("http://", "https://")):
        return ""

    try:
        downloaded = trafilatura.fetch_url(url)
        if not downloaded:
            return ""

        text = trafilatura.extract(
            downloaded,
            include_comments=False,
            include_tables=False,
        )
        if not text:
            return ""

        return text[:max_chars].strip()
    except Exception as e:
        log.warning(f"正文提取失败({url[:80]}): {type(e).__name__}: {e}")
        return ""


def enrich_empty_summaries(
    items: list[dict],
    max_items: int = 10,
    max_chars: int = 300,
    timeout: int = 30,
) -> int:
    """对 summary 为空的新闻条目，并发提取正文摘要。

    直接修改 item["summary"] 字段。

    Args:
        items: 新闻条目列表，每个条目需包含 url 和 summary 键
        max_items: 最多补充的条目数，避免过多 HTTP 请求
        max_chars: 每条摘要的最大字符数
        timeout: 全部提取的总超时（秒）

    Returns:
        成功填充的条目数
    """
    empty_items = [
        item for item in items
        if not item.get("summary") and item.get("url")
    ]

    if not empty_items:
        return 0

    # 限制最多处理的条目数
    to_process = empty_items[:max_items]
    filled = 0

    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = {
            executor.submit(extract_article_content, item["url"], max_chars): item
            for item in to_process
        }
        for future in as_completed(futures, timeout=timeout):
            item = futures[future]
            try:
                content = future.result()
                if content:
                    item["summary"] = content
                    filled += 1
            except Exception as e:
                log.warning(
                    f"正文提取超时或失败({item.get('url', '')[:60]}): "
                    f"{type(e).__name__}: {e}"
                )

    log.info(
        f"正文摘要补充完成: {filled}/{len(to_process)} 条成功填充"
    )
    return filled
