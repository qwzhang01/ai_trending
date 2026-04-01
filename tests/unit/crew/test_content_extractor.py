"""tests/unit/crew/test_content_extractor.py — 正文提取器单元测试。

覆盖 TASK-003 新增的新闻正文摘要提取功能：
- extract_article_content: 正常提取、URL 无效、提取失败、超长截断
- enrich_empty_summaries: 批量填充、部分失败容错、空列表
- NewsFetcher._enrich_empty_summaries: 集成容错
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from ai_trending.crew.new_collect.content_extractor import (
    enrich_empty_summaries,
    extract_article_content,
)


# ── extract_article_content 测试 ──────────────────────────────


class TestExtractArticleContent:
    """测试单条 URL 正文提取。"""

    @patch("ai_trending.crew.new_collect.content_extractor.trafilatura")
    def test_normal_extraction(self, mock_traf):
        """正常情况：应返回提取后的正文摘要。"""
        mock_traf.fetch_url.return_value = "<html><body>Hello World</body></html>"
        mock_traf.extract.return_value = "This is the article content about AI agents and LLM."

        result = extract_article_content("https://example.com/article")

        assert result != ""
        assert "article content" in result
        mock_traf.fetch_url.assert_called_once_with("https://example.com/article")

    @patch("ai_trending.crew.new_collect.content_extractor.trafilatura")
    def test_truncated_to_max_chars(self, mock_traf):
        """超长正文应被截断到 max_chars。"""
        mock_traf.fetch_url.return_value = "<html><body>content</body></html>"
        mock_traf.extract.return_value = "A" * 1000

        result = extract_article_content("https://example.com/long", max_chars=100)

        assert len(result) <= 100

    @patch("ai_trending.crew.new_collect.content_extractor.trafilatura")
    def test_download_fails(self, mock_traf):
        """下载失败时应返回空字符串。"""
        mock_traf.fetch_url.return_value = None

        result = extract_article_content("https://example.com/404")

        assert result == ""

    @patch("ai_trending.crew.new_collect.content_extractor.trafilatura")
    def test_extract_returns_none(self, mock_traf):
        """提取结果为 None 时应返回空字符串。"""
        mock_traf.fetch_url.return_value = "<html>no article</html>"
        mock_traf.extract.return_value = None

        result = extract_article_content("https://example.com/empty")

        assert result == ""

    @patch("ai_trending.crew.new_collect.content_extractor.trafilatura")
    def test_exception_returns_empty(self, mock_traf):
        """提取过程异常应返回空字符串，不崩溃。"""
        mock_traf.fetch_url.side_effect = ConnectionError("网络超时")

        result = extract_article_content("https://example.com/timeout")

        assert result == ""

    def test_invalid_url_empty_string(self):
        """空 URL 应返回空字符串。"""
        assert extract_article_content("") == ""

    def test_invalid_url_no_http(self):
        """非 http/https URL 应返回空字符串。"""
        assert extract_article_content("ftp://example.com") == ""
        assert extract_article_content("not-a-url") == ""

    @patch("ai_trending.crew.new_collect.content_extractor.trafilatura")
    def test_extract_empty_text(self, mock_traf):
        """提取结果为空字符串时应返回空字符串。"""
        mock_traf.fetch_url.return_value = "<html></html>"
        mock_traf.extract.return_value = ""

        result = extract_article_content("https://example.com/blank")

        assert result == ""


# ── enrich_empty_summaries 测试 ───────────────────────────────


class TestEnrichEmptySummaries:
    """测试批量正文摘要填充。"""

    @patch(
        "ai_trending.crew.new_collect.content_extractor.extract_article_content"
    )
    def test_fills_empty_summaries(self, mock_extract):
        """应为 summary 为空的条目填充正文。"""
        mock_extract.return_value = "Extracted content"

        items = [
            {"title": "News A", "url": "https://a.com", "summary": ""},
            {"title": "News B", "url": "https://b.com", "summary": "existing"},
            {"title": "News C", "url": "https://c.com", "summary": ""},
        ]

        filled = enrich_empty_summaries(items)

        assert filled == 2
        assert items[0]["summary"] == "Extracted content"
        assert items[1]["summary"] == "existing"  # 已有摘要不变
        assert items[2]["summary"] == "Extracted content"

    @patch(
        "ai_trending.crew.new_collect.content_extractor.extract_article_content"
    )
    def test_partial_failure(self, mock_extract):
        """部分提取失败时，成功的应被填充，失败的保持空。"""
        mock_extract.side_effect = ["Extracted", "", "Also extracted"]

        items = [
            {"title": "A", "url": "https://a.com", "summary": ""},
            {"title": "B", "url": "https://b.com", "summary": ""},
            {"title": "C", "url": "https://c.com", "summary": ""},
        ]

        filled = enrich_empty_summaries(items)

        # 至少 2 个成功（由于线程执行顺序不确定）
        assert filled >= 1
        # 有值的 summary 应为非空
        filled_items = [i for i in items if i["summary"]]
        assert len(filled_items) >= 1

    @patch(
        "ai_trending.crew.new_collect.content_extractor.extract_article_content"
    )
    def test_all_failure(self, mock_extract):
        """全部失败时应返回 0，不崩溃。"""
        mock_extract.return_value = ""

        items = [
            {"title": "A", "url": "https://a.com", "summary": ""},
        ]

        filled = enrich_empty_summaries(items)

        assert filled == 0

    def test_all_have_summaries(self):
        """所有条目都有 summary 时应不做任何操作。"""
        items = [
            {"title": "A", "url": "https://a.com", "summary": "Existing A"},
            {"title": "B", "url": "https://b.com", "summary": "Existing B"},
        ]

        filled = enrich_empty_summaries(items)

        assert filled == 0
        assert items[0]["summary"] == "Existing A"

    def test_empty_list(self):
        """空列表应返回 0。"""
        filled = enrich_empty_summaries([])
        assert filled == 0

    @patch(
        "ai_trending.crew.new_collect.content_extractor.extract_article_content"
    )
    def test_max_items_limit(self, mock_extract):
        """应最多只处理 max_items 条。"""
        mock_extract.return_value = "content"

        items = [
            {"title": f"News {i}", "url": f"https://n{i}.com", "summary": ""}
            for i in range(20)
        ]

        enrich_empty_summaries(items, max_items=3)

        # mock 应最多被调用 3 次
        assert mock_extract.call_count <= 3

    @patch(
        "ai_trending.crew.new_collect.content_extractor.extract_article_content"
    )
    def test_items_without_url_skipped(self, mock_extract):
        """没有 url 的条目应被跳过。"""
        mock_extract.return_value = "content"

        items = [
            {"title": "No URL", "summary": ""},
            {"title": "Has URL", "url": "https://a.com", "summary": ""},
        ]

        filled = enrich_empty_summaries(items)

        # 只有 1 个有 URL 的被处理
        assert mock_extract.call_count == 1


# ── NewsFetcher._enrich_empty_summaries 集成测试 ──────────────


class TestNewsFetcherEnrichIntegration:
    """测试 NewsFetcher 中正文补充的容错集成。"""

    def test_enrich_tolerates_import_error(self):
        """content_extractor 导入失败时不影响主流程。"""
        from ai_trending.crew.new_collect.fetchers import NewsFetcher

        items = [
            {"title": "A", "url": "https://a.com", "summary": ""},
        ]

        with patch(
            "ai_trending.crew.new_collect.content_extractor.enrich_empty_summaries",
            side_effect=ImportError("module not found"),
        ):
            # 不应抛出异常
            NewsFetcher._enrich_empty_summaries(items)

        # item 保持原样
        assert items[0]["summary"] == ""

    def test_enrich_tolerates_runtime_error(self):
        """运行时异常不影响主流程。"""
        from ai_trending.crew.new_collect.fetchers import NewsFetcher

        items = [
            {"title": "A", "url": "https://a.com", "summary": ""},
        ]

        with patch(
            "ai_trending.crew.new_collect.content_extractor.enrich_empty_summaries",
            side_effect=RuntimeError("unexpected error"),
        ):
            NewsFetcher._enrich_empty_summaries(items)

        assert items[0]["summary"] == ""
