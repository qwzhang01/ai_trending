"""WeChatDraftTool 测试."""

from unittest.mock import MagicMock, patch

import pytest

from ai_trending.tools.wechat_draft_tool import WeChatDraftInput, WeChatDraftTool


# ── fixtures ──────────────────────────────────────────────────────

@pytest.fixture
def tool():
    return WeChatDraftTool()


SAMPLE_HTML = "<h1>AI 日报</h1><p>今日热点内容</p>"
FAKE_ACCESS_TOKEN = "fake_access_token_12345"
FAKE_MEDIA_ID = "fake_draft_media_id_abc"


def _make_token_response():
    mock = MagicMock()
    mock.status_code = 200
    mock.json.return_value = {"access_token": FAKE_ACCESS_TOKEN, "expires_in": 7200}
    return mock


def _make_draft_response(media_id=FAKE_MEDIA_ID):
    mock = MagicMock()
    mock.status_code = 200
    mock.json.return_value = {"media_id": media_id}
    return mock


def _make_error_response(errcode, errmsg="error"):
    mock = MagicMock()
    mock.status_code = 200
    mock.json.return_value = {"errcode": errcode, "errmsg": errmsg}
    return mock


# ── WeChatDraftInput schema ───────────────────────────────────────

class TestWeChatDraftInput:
    def test_required_content(self):
        inp = WeChatDraftInput(content="some html")
        assert inp.content == "some html"

    def test_default_title_empty(self):
        inp = WeChatDraftInput(content="x")
        assert inp.title == ""

    def test_default_author(self):
        inp = WeChatDraftInput(content="x")
        assert inp.author == "AI Trending Bot"

    def test_default_digest_empty(self):
        inp = WeChatDraftInput(content="x")
        assert inp.digest == ""

    def test_custom_values(self):
        inp = WeChatDraftInput(content="x", title="标题", author="作者", digest="摘要")
        assert inp.title == "标题"
        assert inp.author == "作者"
        assert inp.digest == "摘要"


# ── _run — 无环境变量时跳过 ───────────────────────────────────────

class TestWeChatDraftToolRunNoEnv:
    def test_no_app_id_returns_warning(self, tool, monkeypatch):
        monkeypatch.delenv("WECHAT_APP_ID", raising=False)
        monkeypatch.delenv("WECHAT_APP_SECRET", raising=False)
        result = tool._run(content=SAMPLE_HTML)
        assert "⚠️" in result
        assert "WECHAT_APP_ID" in result

    def test_no_app_secret_returns_warning(self, tool, monkeypatch):
        monkeypatch.setenv("WECHAT_APP_ID", "fake_id")
        monkeypatch.delenv("WECHAT_APP_SECRET", raising=False)
        result = tool._run(content=SAMPLE_HTML)
        assert "⚠️" in result


# ── _get_access_token ─────────────────────────────────────────────

class TestGetAccessToken:
    def test_returns_token_on_success(self, tool):
        with patch("ai_trending.tools.wechat_draft_tool.safe_request",
                   return_value=_make_token_response()):
            token = tool._get_access_token("app_id", "app_secret")
        assert token == FAKE_ACCESS_TOKEN

    def test_returns_empty_on_request_failure(self, tool):
        with patch("ai_trending.tools.wechat_draft_tool.safe_request", return_value=None):
            token = tool._get_access_token("app_id", "app_secret")
        assert token == ""

    def test_returns_empty_on_api_error(self, tool):
        with patch("ai_trending.tools.wechat_draft_tool.safe_request",
                   return_value=_make_error_response(40013, "invalid appid")):
            token = tool._get_access_token("bad_id", "bad_secret")
        assert token == ""


# ── _resolve_thumb_media_id ───────────────────────────────────────

class TestResolveThumbMediaId:
    def test_uses_env_media_id_directly(self, tool, monkeypatch):
        monkeypatch.setenv("WECHAT_THUMB_MEDIA_ID", "env_media_id_xyz")
        monkeypatch.delenv("WECHAT_THUMB_IMAGE_URL", raising=False)
        result = tool._resolve_thumb_media_id("any_token")
        assert result == "env_media_id_xyz"

    def test_returns_empty_when_no_config(self, tool, monkeypatch):
        monkeypatch.delenv("WECHAT_THUMB_MEDIA_ID", raising=False)
        monkeypatch.delenv("WECHAT_THUMB_IMAGE_URL", raising=False)
        result = tool._resolve_thumb_media_id("any_token")
        assert result == ""

    def test_uploads_from_url_when_no_media_id(self, tool, monkeypatch):
        monkeypatch.delenv("WECHAT_THUMB_MEDIA_ID", raising=False)
        monkeypatch.setenv("WECHAT_THUMB_IMAGE_URL", "https://example.com/cover.jpg")

        with patch.object(tool, "_upload_thumb_from_url", return_value="uploaded_media_id"):
            result = tool._resolve_thumb_media_id("any_token")
        assert result == "uploaded_media_id"

    def test_returns_empty_when_upload_fails(self, tool, monkeypatch):
        monkeypatch.delenv("WECHAT_THUMB_MEDIA_ID", raising=False)
        monkeypatch.setenv("WECHAT_THUMB_IMAGE_URL", "https://example.com/cover.jpg")

        with patch.object(tool, "_upload_thumb_from_url", return_value=""):
            result = tool._resolve_thumb_media_id("any_token")
        assert result == ""


# ── _add_draft ────────────────────────────────────────────────────

class TestAddDraft:
    def test_returns_media_id_on_success(self, tool):
        with patch("ai_trending.tools.wechat_draft_tool.safe_request",
                   return_value=_make_draft_response()):
            result = tool._add_draft(
                FAKE_ACCESS_TOKEN, "标题", "作者", "摘要", SAMPLE_HTML, "thumb_id"
            )
        assert result == FAKE_MEDIA_ID

    def test_returns_empty_on_request_failure(self, tool):
        with patch("ai_trending.tools.wechat_draft_tool.safe_request", return_value=None):
            result = tool._add_draft(
                FAKE_ACCESS_TOKEN, "标题", "作者", "摘要", SAMPLE_HTML, "thumb_id"
            )
        assert result == ""

    def test_returns_empty_on_api_error(self, tool):
        with patch("ai_trending.tools.wechat_draft_tool.safe_request",
                   return_value=_make_error_response(40007, "invalid media_id")):
            result = tool._add_draft(
                FAKE_ACCESS_TOKEN, "标题", "作者", "摘要", SAMPLE_HTML, "bad_thumb_id"
            )
        assert result == ""

    def test_payload_structure(self, tool):
        """验证发送给微信 API 的 payload 结构正确."""
        captured = {}

        def mock_request(method, url, **kwargs):
            captured.update(kwargs.get("json", {}))
            return _make_draft_response()

        with patch("ai_trending.tools.wechat_draft_tool.safe_request", side_effect=mock_request):
            tool._add_draft(FAKE_ACCESS_TOKEN, "测试标题", "测试作者", "测试摘要", SAMPLE_HTML, "thumb_123")

        articles = captured.get("articles", [])
        assert len(articles) == 1
        article = articles[0]
        assert article["title"] == "测试标题"
        assert article["author"] == "测试作者"
        assert article["digest"] == "测试摘要"
        assert article["content"] == SAMPLE_HTML
        assert article["thumb_media_id"] == "thumb_123"


# ── _run — 完整流程 ───────────────────────────────────────────────

class TestWeChatDraftToolRunFull:
    def test_run_success(self, tool, wechat_env):
        """完整成功流程：获取 token → 解析 media_id → 添加草稿."""
        with patch.object(tool, "_get_access_token", return_value=FAKE_ACCESS_TOKEN), \
             patch.object(tool, "_resolve_thumb_media_id", return_value="thumb_media_id"), \
             patch.object(tool, "_add_draft", return_value=FAKE_MEDIA_ID):
            result = tool._run(content=SAMPLE_HTML)

        assert "✅" in result
        assert FAKE_MEDIA_ID in result
        assert "草稿箱" in result

    def test_run_fails_when_token_empty(self, tool, wechat_env):
        with patch.object(tool, "_get_access_token", return_value=""):
            result = tool._run(content=SAMPLE_HTML)
        assert "❌" in result
        assert "access_token" in result

    def test_run_fails_when_no_thumb_media_id(self, tool, wechat_env):
        with patch.object(tool, "_get_access_token", return_value=FAKE_ACCESS_TOKEN), \
             patch.object(tool, "_resolve_thumb_media_id", return_value=""):
            result = tool._run(content=SAMPLE_HTML)
        assert "❌" in result
        assert "media_id" in result

    def test_run_fails_when_draft_add_fails(self, tool, wechat_env):
        with patch.object(tool, "_get_access_token", return_value=FAKE_ACCESS_TOKEN), \
             patch.object(tool, "_resolve_thumb_media_id", return_value="thumb_id"), \
             patch.object(tool, "_add_draft", return_value=""):
            result = tool._run(content=SAMPLE_HTML)
        assert "❌" in result
        assert "草稿箱" in result

    def test_run_auto_generates_title(self, tool, wechat_env):
        """未指定 title 时，应自动生成包含日期的标题."""
        with patch.object(tool, "_get_access_token", return_value=FAKE_ACCESS_TOKEN), \
             patch.object(tool, "_resolve_thumb_media_id", return_value="thumb_id"), \
             patch.object(tool, "_add_draft", return_value=FAKE_MEDIA_ID) as mock_add:
            tool._run(content=SAMPLE_HTML, title="")

        call_args = mock_add.call_args
        title_used = call_args[0][1]  # 第2个位置参数是 title
        from datetime import datetime
        today = datetime.now().strftime("%Y-%m-%d")
        assert today in title_used

    def test_run_auto_generates_digest(self, tool, wechat_env):
        """未指定 digest 时，应自动截取内容前 120 字作为摘要."""
        long_html = "<p>" + "A" * 200 + "</p>"
        with patch.object(tool, "_get_access_token", return_value=FAKE_ACCESS_TOKEN), \
             patch.object(tool, "_resolve_thumb_media_id", return_value="thumb_id"), \
             patch.object(tool, "_add_draft", return_value=FAKE_MEDIA_ID) as mock_add:
            tool._run(content=long_html, digest="")

        call_args = mock_add.call_args
        digest_used = call_args[0][3]  # 第4个位置参数是 digest
        assert len(digest_used) <= 120

    def test_run_uses_custom_title_and_author(self, tool, wechat_env):
        with patch.object(tool, "_get_access_token", return_value=FAKE_ACCESS_TOKEN), \
             patch.object(tool, "_resolve_thumb_media_id", return_value="thumb_id"), \
             patch.object(tool, "_add_draft", return_value=FAKE_MEDIA_ID) as mock_add:
            tool._run(content=SAMPLE_HTML, title="自定义标题", author="自定义作者")

        call_args = mock_add.call_args
        assert call_args[0][1] == "自定义标题"
        assert call_args[0][2] == "自定义作者"
