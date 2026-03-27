"""GitHubPublishTool 测试."""

import base64
import os
from unittest.mock import MagicMock, patch

import pytest

from ai_trending.tools.github_publish_tool import GitHubPublishInput, GitHubPublishTool


# ── fixtures ──────────────────────────────────────────────────────

@pytest.fixture
def tool():
    return GitHubPublishTool()


SAMPLE_CONTENT = "# AI Trending Report\n\nSome content here."


def _make_github_response(status_code=200, html_url="https://github.com/owner/repo/blob/main/reports/2026-03-19.md"):
    mock = MagicMock()
    mock.status_code = status_code
    mock.json.return_value = {
        "content": {"html_url": html_url},
        "sha": "abc123sha",
    }
    return mock


# ── GitHubPublishInput schema ─────────────────────────────────────

class TestGitHubPublishInput:
    def test_required_content(self):
        inp = GitHubPublishInput(content="some content")
        assert inp.content == "some content"

    def test_default_filename_empty(self):
        inp = GitHubPublishInput(content="x")
        assert inp.filename == ""

    def test_default_commit_message_empty(self):
        inp = GitHubPublishInput(content="x")
        assert inp.commit_message == ""

    def test_custom_values(self):
        inp = GitHubPublishInput(content="x", filename="custom.md", commit_message="feat: add report")
        assert inp.filename == "custom.md"
        assert inp.commit_message == "feat: add report"


# ── _save_locally ─────────────────────────────────────────────────

class TestSaveLocally:
    def test_saves_file_to_reports_dir(self, tool, tmp_output_dir):
        result = tool._save_locally(SAMPLE_CONTENT, "test.md", "测试原因")
        reports_dir = tmp_output_dir / "reports"
        assert (reports_dir / "test.md").exists()
        assert (reports_dir / "test.md").read_text(encoding="utf-8") == SAMPLE_CONTENT

    def test_auto_generates_filename_from_date(self, tool, tmp_output_dir):
        result = tool._save_locally(SAMPLE_CONTENT, "", "测试原因")
        reports_dir = tmp_output_dir / "reports"
        # 应该有一个以日期命名的文件
        md_files = list(reports_dir.glob("*.md"))
        assert len(md_files) == 1

    def test_returns_warning_message(self, tool, tmp_output_dir):
        result = tool._save_locally(SAMPLE_CONTENT, "test.md", "未设置 GITHUB_TRENDING_TOKEN")
        assert "未设置 GITHUB_TRENDING_TOKEN" in result
        assert "test.md" in result


# ── _run — 无环境变量时降级到本地 ────────────────────────────────

class TestGitHubPublishToolRunFallback:
    def test_no_token_saves_locally(self, tool, tmp_output_dir):
        """未设置 token 时，应降级保存到本地并提示 GITHUB_TRENDING_TOKEN。"""
        from ai_trending.config import AppConfig, GitHubConfig, LLMConfig, NewsConfig, WeChatConfig
        fake_cfg = AppConfig(
            llm=LLMConfig(),
            github=GitHubConfig(token="", report_repo=""),
            news=NewsConfig(),
            wechat=WeChatConfig(),
        )
        with patch("ai_trending.tools.github_publish_tool.load_config", return_value=fake_cfg):
            result = tool._run(content=SAMPLE_CONTENT)
        assert "GITHUB_TRENDING_TOKEN" in result
        assert "本地路径" in result

    def test_no_repo_saves_locally(self, tool, tmp_output_dir):
        """有 token 但未设置 repo 时，应降级保存到本地并提示 GITHUB_REPORT_REPO。"""
        from ai_trending.config import AppConfig, GitHubConfig, LLMConfig, NewsConfig, WeChatConfig
        fake_cfg = AppConfig(
            llm=LLMConfig(),
            github=GitHubConfig(token="fake-token", report_repo=""),
            news=NewsConfig(),
            wechat=WeChatConfig(),
        )
        with patch("ai_trending.tools.github_publish_tool.load_config", return_value=fake_cfg):
            result = tool._run(content=SAMPLE_CONTENT)
        assert "GITHUB_REPORT_REPO" in result
        assert "本地路径" in result


# ── _run — 正常推送到 GitHub ──────────────────────────────────────

class TestGitHubPublishToolRunSuccess:
    def test_push_new_file(self, tool, tmp_output_dir, github_env):
        """文件不存在时，直接创建（GET 返回 404，PUT 返回 201）."""
        check_resp = MagicMock()
        check_resp.status_code = 404

        put_resp = _make_github_response(status_code=201)

        with patch("ai_trending.tools.github_publish_tool.safe_request",
                   side_effect=[check_resp, put_resp]):
            result = tool._run(content=SAMPLE_CONTENT)

        assert "✅" in result
        assert "test-owner/test-repo" in result

    def test_push_existing_file_with_sha(self, tool, tmp_output_dir, github_env):
        """文件已存在时，PUT 请求应包含 sha."""
        check_resp = MagicMock()
        check_resp.status_code = 200
        check_resp.json.return_value = {"sha": "existing_sha_abc"}

        put_resp = _make_github_response(status_code=200)

        captured_payload = {}

        def mock_request(method, url, **kwargs):
            if method == "GET":
                return check_resp
            captured_payload.update(kwargs.get("json", {}))
            return put_resp

        with patch("ai_trending.tools.github_publish_tool.safe_request", side_effect=mock_request):
            result = tool._run(content=SAMPLE_CONTENT)

        assert captured_payload.get("sha") == "existing_sha_abc"
        assert "✅" in result

    def test_content_is_base64_encoded(self, tool, tmp_output_dir, github_env):
        """推送内容应经过 base64 编码."""
        check_resp = MagicMock()
        check_resp.status_code = 404

        put_resp = _make_github_response()
        captured_payload = {}

        def mock_request(method, url, **kwargs):
            if method == "GET":
                return check_resp
            captured_payload.update(kwargs.get("json", {}))
            return put_resp

        with patch("ai_trending.tools.github_publish_tool.safe_request", side_effect=mock_request):
            tool._run(content=SAMPLE_CONTENT)

        encoded = captured_payload.get("content", "")
        decoded = base64.b64decode(encoded).decode("utf-8")
        assert decoded == SAMPLE_CONTENT

    def test_auto_generates_filename(self, tool, tmp_output_dir, github_env):
        """未指定 filename 时，应自动生成日期文件名."""
        check_resp = MagicMock()
        check_resp.status_code = 404
        put_resp = _make_github_response()

        captured_url = {}

        def mock_request(method, url, **kwargs):
            if method == "GET":
                captured_url["get"] = url
                return check_resp
            captured_url["put"] = url
            return put_resp

        with patch("ai_trending.tools.github_publish_tool.safe_request", side_effect=mock_request):
            tool._run(content=SAMPLE_CONTENT, filename="")

        assert "reports/" in captured_url.get("put", "")
        assert ".md" in captured_url.get("put", "")

    def test_custom_filename_used(self, tool, tmp_output_dir, github_env):
        """指定 filename 时，应使用指定的文件名."""
        check_resp = MagicMock()
        check_resp.status_code = 404
        put_resp = _make_github_response()

        captured_url = {}

        def mock_request(method, url, **kwargs):
            if method == "GET":
                return check_resp
            captured_url["put"] = url
            return put_resp

        with patch("ai_trending.tools.github_publish_tool.safe_request", side_effect=mock_request):
            tool._run(content=SAMPLE_CONTENT, filename="my-report.md")

        assert "my-report.md" in captured_url.get("put", "")

    def test_push_failure_falls_back_to_local(self, tool, tmp_output_dir, github_env):
        """推送失败（safe_request 返回 None）时，降级保存到本地."""
        with patch("ai_trending.tools.github_publish_tool.safe_request", return_value=None):
            result = tool._run(content=SAMPLE_CONTENT)
        assert "本地路径" in result
        assert "⚠️" in result
