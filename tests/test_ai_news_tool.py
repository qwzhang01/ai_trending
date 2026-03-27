"""AINewsTool 测试."""

import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ai_trending.tools.ai_news_tool import AINewsTool, AINewsInput


# ── fixtures ──────────────────────────────────────────────────────

@pytest.fixture
def tool():
    return AINewsTool()


def _make_hn_response(hits=None):
    """构造 HackerNews API 响应."""
    hits = hits or [
        {
            "title": "GPT-5 Released with Multimodal Capabilities",
            "url": "https://openai.com/gpt5",
            "points": 500,
            "created_at": "2026-03-19T10:00:00Z",
            "objectID": "12345",
        }
    ]
    mock = MagicMock()
    mock.status_code = 200
    mock.json.return_value = {"hits": hits}
    return mock


def _make_reddit_rss_response(title="AI Agent Framework Released"):
    """构造 Reddit RSS 响应."""
    xml_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <title>{title}</title>
    <link href="https://reddit.com/r/artificial/comments/abc123"/>
    <updated>2026-03-19T10:00:00Z</updated>
    <content type="html">Some content about AI</content>
  </entry>
</feed>"""
    mock = MagicMock()
    mock.status_code = 200
    mock.text = xml_content
    return mock


def _make_pullpush_response(items=None):
    """构造 Pullpush API 响应."""
    items = items or [
        {
            "title": "New LLM Benchmark Results",
            "permalink": "/r/MachineLearning/comments/xyz",
            "score": 300,
            "created_utc": 1710835200,
            "selftext": "Benchmark details here",
        }
    ]
    mock = MagicMock()
    mock.status_code = 200
    mock.json.return_value = {"data": items}
    return mock


def _make_newsdata_response(articles=None):
    """构造 newsdata.io API 响应."""
    articles = articles or [
        {
            "title": "OpenAI Announces New Model",
            "link": "https://newsdata.io/article/1",
            "source_name": "TechCrunch",
            "description": "OpenAI has announced...",
            "pubDate": "2026-03-19 10:00:00",
        }
    ]
    mock = MagicMock()
    mock.status_code = 200
    mock.json.return_value = {"status": "success", "results": articles}
    return mock


# ── AINewsInput schema ────────────────────────────────────────────

class TestAINewsInput:
    def test_default_values(self):
        inp = AINewsInput()
        assert inp.keywords == "AI,LLM,AI Agent"
        assert inp.top_n == 10

    def test_custom_values(self):
        inp = AINewsInput(keywords="GPT,Claude", top_n=5)
        assert inp.keywords == "GPT,Claude"
        assert inp.top_n == 5


# ── _fetch_hacker_news ────────────────────────────────────────────

class TestFetchHackerNews:
    def test_returns_news_list(self, tool, tmp_output_dir):
        with patch("ai_trending.crew.new_collect.fetchers.safe_request", return_value=_make_hn_response()):
            result = tool._fetch_hacker_news(["AI"], 5)
        assert len(result) == 1
        assert result[0]["source"] == "Hacker News"
        assert result[0]["title"] == "GPT-5 Released with Multimodal Capabilities"
        assert result[0]["score"] == 500

    def test_returns_empty_on_request_failure(self, tool, tmp_output_dir):
        with patch("ai_trending.crew.new_collect.fetchers.safe_request", return_value=None):
            result = tool._fetch_hacker_news(["AI"], 5)
        assert result == []

    def test_url_fallback_to_hn_item(self, tool, tmp_output_dir):
        """当 hit 没有 url key 时，应回退到 HN item 链接."""
        hit_no_url = {
            "title": "Ask HN: Best AI tools?",
            # 不包含 url key，触发 fallback
            "points": 100,
            "created_at": "2026-03-19T10:00:00Z",
            "objectID": "99999",
        }
        with patch("ai_trending.crew.new_collect.fetchers.safe_request", return_value=_make_hn_response([hit_no_url])):
            result = tool._fetch_hacker_news(["AI"], 5)
        assert "99999" in result[0]["url"]

    def test_only_uses_first_3_keywords(self, tool, tmp_output_dir):
        """最多只用前3个关键词搜索."""
        call_count = 0
        def mock_request(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            return _make_hn_response([])

        with patch("ai_trending.crew.new_collect.fetchers.safe_request", side_effect=mock_request):
            tool._fetch_hacker_news(["k1", "k2", "k3", "k4", "k5"], 5)
        assert call_count == 3


# ── _fetch_reddit_rss ─────────────────────────────────────────────

class TestFetchRedditRss:
    def test_returns_news_from_rss(self, tool, tmp_output_dir):
        with patch("ai_trending.crew.new_collect.fetchers.safe_request", return_value=_make_reddit_rss_response()):
            result = tool._fetch_reddit_rss("artificial", ["AI"])
        assert len(result) == 1
        assert "Reddit r/artificial" == result[0]["source"]
        assert result[0]["score"] == 20  # RSS 默认分数

    def test_returns_empty_on_request_failure(self, tool, tmp_output_dir):
        with patch("ai_trending.crew.new_collect.fetchers.safe_request", return_value=None):
            result = tool._fetch_reddit_rss("artificial", ["AI"])
        assert result == []

    def test_handles_invalid_xml(self, tool, tmp_output_dir):
        mock = MagicMock()
        mock.text = "not valid xml <<<"
        with patch("ai_trending.crew.new_collect.fetchers.safe_request", return_value=mock):
            result = tool._fetch_reddit_rss("artificial", ["AI"])
        assert result == []


# ── _fetch_reddit_pullpush ────────────────────────────────────────

class TestFetchRedditPullpush:
    def test_returns_news_from_pullpush(self, tool, tmp_output_dir):
        with patch("ai_trending.crew.new_collect.fetchers.safe_request", return_value=_make_pullpush_response()):
            result = tool._fetch_reddit_pullpush("MachineLearning", ["LLM"])
        assert len(result) == 1
        assert result[0]["score"] == 300
        assert "reddit.com" in result[0]["url"]

    def test_returns_empty_on_request_failure(self, tool, tmp_output_dir):
        with patch("ai_trending.crew.new_collect.fetchers.safe_request", return_value=None):
            result = tool._fetch_reddit_pullpush("MachineLearning", ["LLM"])
        assert result == []

    def test_handles_invalid_json(self, tool, tmp_output_dir):
        mock = MagicMock()
        mock.json.side_effect = ValueError("bad json")
        with patch("ai_trending.crew.new_collect.fetchers.safe_request", return_value=mock):
            result = tool._fetch_reddit_pullpush("MachineLearning", ["LLM"])
        assert result == []


# ── _fetch_newsdata ───────────────────────────────────────────────

class TestFetchNewsdata:
    def test_returns_articles(self, tool, tmp_output_dir):
        with patch("ai_trending.crew.new_collect.fetchers.safe_request", return_value=_make_newsdata_response()):
            result = tool._fetch_newsdata(["AI"], 5, "fake-key")
        assert len(result) == 1
        assert result[0]["title"] == "OpenAI Announces New Model"
        assert result[0]["score"] == 50

    def test_returns_empty_on_request_failure(self, tool, tmp_output_dir):
        with patch("ai_trending.crew.new_collect.fetchers.safe_request", return_value=None):
            result = tool._fetch_newsdata(["AI"], 5, "fake-key")
        assert result == []

    def test_returns_empty_on_non_success_status(self, tool, tmp_output_dir):
        mock = MagicMock()
        mock.json.return_value = {"status": "error", "message": "quota exceeded"}
        with patch("ai_trending.crew.new_collect.fetchers.safe_request", return_value=mock):
            result = tool._fetch_newsdata(["AI"], 5, "fake-key")
        assert result == []

    def test_limits_to_5_keywords(self, tool, tmp_output_dir):
        """最多使用前5个关键词构建查询."""
        captured_params = {}
        def mock_request(*args, **kwargs):
            captured_params.update(kwargs.get("params", {}))
            return _make_newsdata_response([])

        with patch("ai_trending.crew.new_collect.fetchers.safe_request", side_effect=mock_request):
            tool._fetch_newsdata(["k1", "k2", "k3", "k4", "k5", "k6"], 5, "key")
        # 最多5个关键词，用 OR 连接
        assert captured_params["q"].count(" OR ") == 4


# ── _parse_zhihu_heat ─────────────────────────────────────────────

class TestParseZhihuHeat:
    def test_parses_wan_format(self):
        assert AINewsTool._parse_zhihu_heat("2345 万热度") == 23450000

    def test_parses_decimal_wan(self):
        assert AINewsTool._parse_zhihu_heat("1.5 万热度") == 15000

    def test_parses_plain_number(self):
        assert AINewsTool._parse_zhihu_heat("12345") == 12345

    def test_parses_number_with_comma(self):
        assert AINewsTool._parse_zhihu_heat("1,234") == 1234

    def test_returns_default_for_empty(self):
        assert AINewsTool._parse_zhihu_heat("") == 30

    def test_returns_default_for_unrecognized(self):
        assert AINewsTool._parse_zhihu_heat("热度很高") == 30


# ── _run (集成) ───────────────────────────────────────────────────

class TestAINewsToolRun:
    def test_run_returns_formatted_output(self, tool, tmp_output_dir):
        """_run 调用 NewsCollectCrew.run 并返回结果."""
        with patch("ai_trending.tools.ai_news_tool.NewsCollectCrew") as mock_crew_cls:
            mock_crew_cls.return_value.run.return_value = "### 1. GPT-5 Released\n- **来源**: Hacker News\n- **热度**: 500 分"
            result = tool._run(keywords="AI", top_n=5)

        assert "GPT-5 Released" in result
        assert "Hacker News" in result
        assert "500" in result

    def test_run_returns_error_message_when_no_news(self, tool, tmp_output_dir):
        """NewsCollectCrew.run 返回未能获取时，_run 应透传该消息."""
        with patch("ai_trending.tools.ai_news_tool.NewsCollectCrew") as mock_crew_cls:
            mock_crew_cls.return_value.run.return_value = "未能获取到最新的 AI 相关新闻。"
            result = tool._run(keywords="AI", top_n=5)
        assert "未能获取" in result

    def test_run_returns_error_on_exception(self, tool, tmp_output_dir):
        """NewsCollectCrew.run 抛出异常时，_run 应返回错误提示."""
        with patch("ai_trending.tools.ai_news_tool.NewsCollectCrew") as mock_crew_cls:
            mock_crew_cls.return_value.run.side_effect = Exception("LLM 超时")
            result = tool._run(keywords="AI", top_n=5)
        assert "❌" in result
        assert "新闻采集失败" in result

    def test_run_passes_keywords_to_crew(self, tool, tmp_output_dir):
        """_run 应将关键词列表传给 NewsCollectCrew."""
        with patch("ai_trending.tools.ai_news_tool.NewsCollectCrew") as mock_crew_cls:
            mock_crew_cls.return_value.run.return_value = "新闻结果"
            tool._run(keywords="AI,LLM,大模型", top_n=5)
        # 验证 NewsCollectCrew 被正确实例化
        mock_crew_cls.assert_called_once_with(keywords=["AI", "LLM", "大模型"], top_n=5)

    def test_run_respects_top_n(self, tool, tmp_output_dir):
        """top_n 参数应传递给 NewsCollectCrew."""
        with patch("ai_trending.tools.ai_news_tool.NewsCollectCrew") as mock_crew_cls:
            mock_crew_cls.return_value.run.return_value = "新闻结果"
            tool._run(keywords="AI", top_n=3)
        mock_crew_cls.assert_called_once_with(keywords=["AI"], top_n=3)


# ── _fetch_all_async ──────────────────────────────────────────────

class TestFetchAllAsync:
    def test_concurrent_fetch_returns_combined_results(self, tool, tmp_output_dir, monkeypatch):
        monkeypatch.delenv("NEWSDATA_API_KEY", raising=False)  # 确保不触发 newsdata 真实请求
        hn_news = [{"title": "HN News", "url": "https://hn.com/1", "score": 100, "source": "HN", "summary": "", "time": "2026-03-19"}]
        reddit_news = [{"title": "Reddit News", "url": "https://reddit.com/1", "score": 50, "source": "Reddit", "summary": "", "time": "2026-03-19"}]
        zhihu_news = [{"title": "知乎新闻", "url": "https://zhihu.com/1", "score": 30, "source": "知乎", "summary": "", "time": "2026-03-19"}]

        with patch.object(tool, "_fetch_hacker_news", return_value=hn_news), \
             patch.object(tool, "_fetch_reddit_news", return_value=reddit_news), \
             patch.object(tool, "_fetch_zhihu_hot", return_value=zhihu_news):
            all_news, stats = asyncio.run(tool._fetch_all_async(["AI"], 5))

        assert len(all_news) == 3
        titles = [n["title"] for n in all_news]
        assert "HN News" in titles
        assert "Reddit News" in titles
        assert "知乎新闻" in titles

    def test_single_channel_failure_does_not_affect_others(self, tool, tmp_output_dir):
        """单个渠道抛出异常，不影响其他渠道."""
        hn_news = [{"title": "HN News", "url": "https://hn.com/1", "score": 100, "source": "HN", "summary": "", "time": "2026-03-19"}]

        with patch.object(tool, "_fetch_hacker_news", return_value=hn_news), \
             patch.object(tool, "_fetch_reddit_news", side_effect=Exception("Reddit down")), \
             patch.object(tool, "_fetch_zhihu_hot", return_value=[]):
            all_news, stats = asyncio.run(tool._fetch_all_async(["AI"], 5))

        assert any(n["title"] == "HN News" for n in all_news)
        assert any("失败" in s for s in stats)

    def test_newsdata_skipped_without_api_key(self, tool, tmp_output_dir, monkeypatch):
        """没有 NEWSDATA_API_KEY 时，newsdata.io 不应出现在统计中."""
        monkeypatch.delenv("NEWSDATA_API_KEY", raising=False)

        with patch.object(tool, "_fetch_hacker_news", return_value=[]), \
             patch.object(tool, "_fetch_reddit_news", return_value=[]), \
             patch.object(tool, "_fetch_zhihu_hot", return_value=[]):
            _, stats = asyncio.run(tool._fetch_all_async(["AI"], 5))

        assert not any("newsdata.io" in s for s in stats)

    def test_newsdata_included_with_api_key(self, tool, tmp_output_dir, newsdata_env):
        """有 NEWSDATA_API_KEY 时，newsdata.io 应出现在统计中."""
        with patch.object(tool, "_fetch_hacker_news", return_value=[]), \
             patch.object(tool, "_fetch_reddit_news", return_value=[]), \
             patch.object(tool, "_fetch_newsdata", return_value=[]), \
             patch.object(tool, "_fetch_zhihu_hot", return_value=[]):
            _, stats = asyncio.run(tool._fetch_all_async(["AI"], 5))

        assert any("newsdata.io" in s for s in stats)
