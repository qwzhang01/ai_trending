"""tests/unit/crew/test_github_fetcher.py — GitHubFetcher 单元测试。

覆盖 TASK-001 新增的 README 摘要抓取功能：
- _fetch_readme_summary: 正常返回、404、超时
- _clean_readme: badge 移除、图片移除、链接简化、空行压缩
- _fetch_readmes_concurrently: 并发抓取、部分失败容错
- fetch(): 完整流程中 readme_summary 字段被正确填充
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from ai_trending.crew.github_trending.fetchers import GitHubFetcher
from ai_trending.crew.github_trending.models import RepoCandidate

# ── Fixtures ──────────────────────────────────────────────────


@pytest.fixture
def fetcher():
    """创建一个 GitHubFetcher 实例。"""
    return GitHubFetcher()


@pytest.fixture
def sample_candidates():
    """构造 3 个候选仓库。"""
    return [
        RepoCandidate(full_name="owner/repo-a", stars=5000),
        RepoCandidate(full_name="owner/repo-b", stars=3000),
        RepoCandidate(full_name="owner/repo-c", stars=1000),
    ]


def _make_readme_response(text: str, status_code: int = 200) -> MagicMock:
    """构造 README API 的 mock Response。"""
    resp = MagicMock()
    resp.status_code = status_code
    resp.text = text
    resp.headers = {"X-RateLimit-Remaining": "50"}
    return resp


# ── _clean_readme 测试 ────────────────────────────────────────


class TestCleanReadme:
    """测试 README 文本清洗逻辑。"""

    def test_removes_badge_images(self):
        """应移除带链接的 badge 图片 [![alt](img)](link)。"""
        raw = "[![Build Status](https://img.shields.io/badge.svg)](https://ci.example.com)\nHello World"
        result = GitHubFetcher._clean_readme(raw)
        assert "Build Status" not in result
        assert "img.shields.io" not in result
        assert "Hello World" in result

    def test_removes_plain_images(self):
        """应移除普通 Markdown 图片 ![alt](url)。"""
        raw = "![Logo](https://example.com/logo.png)\n\nThis is a project."
        result = GitHubFetcher._clean_readme(raw)
        assert "Logo" not in result
        assert "example.com/logo.png" not in result
        assert "This is a project." in result

    def test_removes_html_tags(self):
        """应移除 HTML 标签。"""
        raw = '<div align="center"><h1>Title</h1></div>\nContent here.'
        result = GitHubFetcher._clean_readme(raw)
        assert "<div" not in result
        assert "<h1>" not in result
        assert "Title" in result
        assert "Content here." in result

    def test_simplifies_markdown_links(self):
        """应将 [text](url) 替换为纯文本 text。"""
        raw = "Check out [the docs](https://docs.example.com) for more info."
        result = GitHubFetcher._clean_readme(raw)
        assert "the docs" in result
        assert "https://docs.example.com" not in result

    def test_removes_heading_markers(self):
        """应移除 Markdown 标题标记 ###。"""
        raw = "## Installation\n\nRun pip install foo.\n\n### Usage\n\nJust import it."
        result = GitHubFetcher._clean_readme(raw)
        assert "##" not in result
        assert "Installation" in result
        assert "Usage" in result

    def test_compresses_blank_lines(self):
        """应将连续 3+ 空行压缩为 2 行。"""
        raw = "First paragraph.\n\n\n\n\nSecond paragraph."
        result = GitHubFetcher._clean_readme(raw)
        assert "\n\n\n" not in result
        assert "First paragraph." in result
        assert "Second paragraph." in result

    def test_empty_input(self):
        """空字符串应返回空字符串。"""
        assert GitHubFetcher._clean_readme("") == ""

    def test_mixed_noise(self):
        """综合测试：badge + 图片 + HTML + 链接 + 标题标记同时出现。"""
        raw = (
            "[![CI](https://badge.svg)](https://ci.com)\n"
            "![Logo](https://logo.png)\n"
            '<p align="center">Centered text</p>\n'
            "## About\n"
            "This is [a cool project](https://github.com/foo).\n"
        )
        result = GitHubFetcher._clean_readme(raw)
        assert "badge.svg" not in result
        assert "logo.png" not in result
        assert "<p" not in result
        assert "##" not in result
        assert "Centered text" in result
        assert "About" in result
        assert "a cool project" in result
        assert "https://github.com/foo" not in result

    def test_preserves_code_blocks(self):
        """代码块中的内容应大部分被保留（不做额外清洗）。"""
        raw = "```python\nimport torch\nmodel = GPT()\n```\n\nEnd."
        result = GitHubFetcher._clean_readme(raw)
        assert "import torch" in result
        assert "End." in result


# ── _fetch_readme_summary 测试 ────────────────────────────────


class TestFetchReadmeSummary:
    """测试单个仓库 README 摘要抓取。"""

    @patch("ai_trending.crew.github_trending.fetchers.safe_request")
    def test_normal_readme(self, mock_request, fetcher):
        """正常情况：API 返回 README 文本，应返回清洗后的摘要。"""
        readme_text = (
            "# My Project\n\n"
            "![badge](https://badge.svg)\n\n"
            "This is a great AI tool for building agents.\n"
            "It supports multiple LLM backends.\n"
        )
        mock_request.return_value = _make_readme_response(readme_text)

        result = fetcher._fetch_readme_summary("owner/repo")

        assert result != ""
        assert "great AI tool" in result
        assert "badge.svg" not in result
        mock_request.assert_called_once()

    @patch("ai_trending.crew.github_trending.fetchers.safe_request")
    def test_readme_404(self, mock_request, fetcher):
        """README 不存在（API 返回 None）：应返回空字符串。"""
        mock_request.return_value = None

        result = fetcher._fetch_readme_summary("owner/no-readme-repo")

        assert result == ""

    @patch("ai_trending.crew.github_trending.fetchers.safe_request")
    def test_readme_timeout(self, mock_request, fetcher):
        """请求超时（safe_request 返回 None）：应返回空字符串。"""
        mock_request.return_value = None

        result = fetcher._fetch_readme_summary("owner/slow-repo")

        assert result == ""

    @patch("ai_trending.crew.github_trending.fetchers.safe_request")
    def test_readme_truncated_to_500(self, mock_request, fetcher):
        """超长 README 应被截断到 500 字符。"""
        long_text = "A" * 3000
        mock_request.return_value = _make_readme_response(long_text)

        result = fetcher._fetch_readme_summary("owner/long-readme")

        assert len(result) <= 500

    @patch("ai_trending.crew.github_trending.fetchers.safe_request")
    def test_readme_empty_response(self, mock_request, fetcher):
        """API 返回空文本：应返回空字符串。"""
        mock_request.return_value = _make_readme_response("")

        result = fetcher._fetch_readme_summary("owner/empty-readme")

        assert result == ""

    @patch("ai_trending.crew.github_trending.fetchers.safe_request")
    def test_readme_uses_auth_header(self, mock_request, fetcher, monkeypatch):
        """设置了 GITHUB_TRENDING_TOKEN 时，请求应带 Authorization 头。"""
        monkeypatch.setenv("GITHUB_TRENDING_TOKEN", "test-token-123")
        mock_request.return_value = _make_readme_response("Some content")

        fetcher._fetch_readme_summary("owner/repo")

        call_kwargs = mock_request.call_args
        headers = call_kwargs.kwargs.get("headers") or call_kwargs[1].get("headers", {})
        assert "Authorization" in headers
        assert "test-token-123" in headers["Authorization"]

    @patch("ai_trending.crew.github_trending.fetchers.safe_request")
    def test_readme_without_token(self, mock_request, fetcher, monkeypatch):
        """未设置 GITHUB_TRENDING_TOKEN 时，请求不带 Authorization 头。"""
        monkeypatch.delenv("GITHUB_TRENDING_TOKEN", raising=False)
        mock_request.return_value = _make_readme_response("Some content")

        fetcher._fetch_readme_summary("owner/repo")

        call_kwargs = mock_request.call_args
        headers = call_kwargs.kwargs.get("headers") or call_kwargs[1].get("headers", {})
        assert "Authorization" not in headers


# ── _fetch_readmes_concurrently 测试 ──────────────────────────


class TestFetchReadmesConcurrently:
    """测试并发 README 抓取。"""

    @patch.object(GitHubFetcher, "_fetch_readme_summary")
    def test_all_success(self, mock_fetch, fetcher, sample_candidates):
        """所有仓库 README 抓取成功，readme_summary 应全部填充。"""
        mock_fetch.side_effect = [
            "Summary for repo-a",
            "Summary for repo-b",
            "Summary for repo-c",
        ]

        fetcher._fetch_readmes_concurrently(sample_candidates)

        filled = [c for c in sample_candidates if c.readme_summary]
        assert len(filled) == 3
        assert sample_candidates[0].readme_summary == "Summary for repo-a"

    @patch.object(GitHubFetcher, "_fetch_readme_summary")
    def test_partial_failure(self, mock_fetch, fetcher, sample_candidates):
        """部分仓库失败时，成功的应被填充，失败的保持空字符串。"""
        mock_fetch.side_effect = [
            "Summary for repo-a",
            Exception("网络超时"),
            "Summary for repo-c",
        ]

        fetcher._fetch_readmes_concurrently(sample_candidates)

        # 至少应有 2 个成功（由于线程执行顺序不确定，用 >= 做断言）
        filled = [c for c in sample_candidates if c.readme_summary]
        assert len(filled) >= 2

    @patch.object(GitHubFetcher, "_fetch_readme_summary")
    def test_all_failure(self, mock_fetch, fetcher, sample_candidates):
        """所有仓库 README 抓取失败，readme_summary 应全部为空。"""
        mock_fetch.side_effect = Exception("全部超时")

        fetcher._fetch_readmes_concurrently(sample_candidates)

        filled = [c for c in sample_candidates if c.readme_summary]
        assert len(filled) == 0

    @patch.object(GitHubFetcher, "_fetch_readme_summary")
    def test_empty_candidates(self, mock_fetch, fetcher):
        """空候选列表应直接返回，不调用抓取方法。"""
        fetcher._fetch_readmes_concurrently([])

        mock_fetch.assert_not_called()

    @patch.object(GitHubFetcher, "_fetch_readme_summary")
    def test_some_return_empty_string(self, mock_fetch, fetcher, sample_candidates):
        """部分仓库返回空字符串（无 README），不应被计为成功。"""
        mock_fetch.side_effect = ["Summary A", "", "Summary C"]

        fetcher._fetch_readmes_concurrently(sample_candidates)

        filled = [c for c in sample_candidates if c.readme_summary]
        assert len(filled) == 2


# ── RepoCandidate 模型测试 ────────────────────────────────────


class TestRepoCandidateModel:
    """测试 RepoCandidate 的 readme_summary 字段。"""

    def test_default_empty(self):
        """默认 readme_summary 应为空字符串。"""
        repo = RepoCandidate(full_name="owner/repo")
        assert repo.readme_summary == ""

    def test_set_summary(self):
        """应能正常设置 readme_summary。"""
        repo = RepoCandidate(
            full_name="owner/repo",
            readme_summary="This is a cool project",
        )
        assert repo.readme_summary == "This is a cool project"

    def test_model_dump_includes_summary(self):
        """model_dump 应包含 readme_summary 字段。"""
        repo = RepoCandidate(
            full_name="owner/repo",
            readme_summary="Some summary",
        )
        data = repo.model_dump()
        assert "readme_summary" in data
        assert data["readme_summary"] == "Some summary"


# ── fetch() 集成测试（mock 外部调用）────────────────────────────


class TestFetchIntegration:
    """测试 fetch() 完整流程中 README 摘要的集成。"""

    @patch("ai_trending.crew.github_trending.fetchers.safe_request")
    @patch("ai_trending.crew.util.dedup_cache.DedupCache")
    def test_fetch_fills_readme_summary(
        self, mock_dedup_cls, mock_request, fetcher, monkeypatch
    ):
        """fetch() 完整流程应为 candidates 填充 readme_summary。"""
        monkeypatch.setenv("GITHUB_TRENDING_TOKEN", "fake-token")

        # mock DedupCache
        mock_dedup = MagicMock()
        mock_dedup.filter_new.side_effect = lambda items, key_fn: items
        mock_dedup.stats.return_value = "hits=0, misses=1"
        mock_dedup_cls.return_value = mock_dedup

        # 构造 GitHub 搜索 API 响应
        search_response = MagicMock()
        search_response.status_code = 200
        search_response.headers = {"X-RateLimit-Remaining": "50"}
        search_response.json.return_value = {
            "items": [
                {
                    "full_name": "test/ai-framework",
                    "description": "An AI framework",
                    "language": "Python",
                    "stargazers_count": 5000,
                    "topics": ["ai", "llm"],
                    "created_at": "2025-01-01T00:00:00Z",
                    "updated_at": "2026-03-30T00:00:00Z",
                    "html_url": "https://github.com/test/ai-framework",
                },
            ],
            "total_count": 1,
        }

        # 构造 README API 响应
        readme_response = MagicMock()
        readme_response.status_code = 200
        readme_response.text = "# AI Framework\n\nA powerful tool for building agents."
        readme_response.headers = {"X-RateLimit-Remaining": "49"}

        # safe_request 按 URL 路由不同响应
        def route_request(method, url, **kwargs):
            if "/readme" in url:
                return readme_response
            return search_response

        mock_request.side_effect = route_request

        result = fetcher.fetch(keywords=["ai-agent"], query="AI")

        assert len(result.candidates) > 0
        # 至少有一个候选仓库有 README 摘要
        has_readme = any(c.readme_summary for c in result.candidates)
        assert has_readme, "至少一个候选仓库应有 readme_summary"

    @patch("ai_trending.crew.github_trending.fetchers.safe_request")
    @patch("ai_trending.crew.util.dedup_cache.DedupCache")
    def test_fetch_tolerates_readme_failure(
        self, mock_dedup_cls, mock_request, fetcher, monkeypatch
    ):
        """README 抓取全部失败时，fetch() 仍应正常返回候选列表。"""
        monkeypatch.setenv("GITHUB_TRENDING_TOKEN", "fake-token")

        mock_dedup = MagicMock()
        mock_dedup.filter_new.side_effect = lambda items, key_fn: items
        mock_dedup.stats.return_value = "hits=0, misses=1"
        mock_dedup_cls.return_value = mock_dedup

        search_response = MagicMock()
        search_response.status_code = 200
        search_response.headers = {"X-RateLimit-Remaining": "50"}
        search_response.json.return_value = {
            "items": [
                {
                    "full_name": "test/repo",
                    "description": "A test repo",
                    "language": "Python",
                    "stargazers_count": 2000,
                    "topics": [],
                    "created_at": "2025-06-01T00:00:00Z",
                    "updated_at": "2026-03-28T00:00:00Z",
                    "html_url": "https://github.com/test/repo",
                },
            ],
            "total_count": 1,
        }

        def route_request(method, url, **kwargs):
            if "/readme" in url:
                return None  # README 抓取失败
            return search_response

        mock_request.side_effect = route_request

        result = fetcher.fetch(keywords=["test"], query="test")

        # fetch 仍应正常返回
        assert len(result.candidates) > 0
        # README 为空但不影响其他字段
        assert result.candidates[0].full_name == "test/repo"
