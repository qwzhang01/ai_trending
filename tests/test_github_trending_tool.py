"""GitHubTrendingTool 测试."""

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from ai_trending.tools.github_trending_tool import (
    EXCLUDE_REPOS,
    GitHubTrendingInput,
    GitHubTrendingTool,
    _is_excluded,
)


# ── fixtures ──────────────────────────────────────────────────────

@pytest.fixture
def tool():
    return GitHubTrendingTool()


def _make_repo(
    full_name="test-owner/cool-llm-agent",
    name="cool-llm-agent",
    description="A cool LLM agent framework",
    stars=1000,
    language="Python",
    fork=False,
    topics=None,
    created_at="2025-06-01T00:00:00Z",
    updated_at=None,
):
    updated_at = updated_at or datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")
    return {
        "full_name": full_name,
        "name": name,
        "description": description,
        "stargazers_count": stars,
        "language": language,
        "fork": fork,
        "topics": topics or ["llm", "agent"],
        "created_at": created_at,
        "updated_at": updated_at,
        "html_url": f"https://github.com/{full_name}",
    }


def _make_search_response(items=None, status_code=200):
    mock = MagicMock()
    mock.status_code = status_code
    mock.headers = {"X-RateLimit-Remaining": "50"}
    mock.json.return_value = {"items": items or []}
    return mock


# ── GitHubTrendingInput schema ────────────────────────────────────

class TestGitHubTrendingInput:
    def test_default_values(self):
        inp = GitHubTrendingInput()
        assert inp.query == "AI"
        assert inp.top_n == 5

    def test_custom_values(self):
        inp = GitHubTrendingInput(query="LLM", top_n=10)
        assert inp.query == "LLM"
        assert inp.top_n == 10


# ── _is_excluded ──────────────────────────────────────────────────

class TestIsExcluded:
    def test_excludes_blacklisted_repo(self):
        repo = _make_repo(full_name="huggingface/transformers", name="transformers")
        assert _is_excluded(repo) is True

    def test_excludes_awesome_prefix(self):
        repo = _make_repo(full_name="user/awesome-llm", name="awesome-llm")
        assert _is_excluded(repo) is True

    def test_excludes_awesome_suffix(self):
        repo = _make_repo(full_name="user/llm-awesome", name="llm-awesome")
        assert _is_excluded(repo) is True

    def test_excludes_tutorial_in_name(self):
        repo = _make_repo(full_name="user/llm-tutorials", name="llm-tutorials")
        assert _is_excluded(repo) is True

    def test_excludes_fork(self):
        repo = _make_repo(fork=True)
        assert _is_excluded(repo) is True

    def test_excludes_curated_list_description(self):
        repo = _make_repo(description="A curated list of awesome LLM resources")
        assert _is_excluded(repo) is True

    def test_excludes_collection_of_links(self):
        repo = _make_repo(description="A collection of links to AI tools")
        assert _is_excluded(repo) is True

    def test_does_not_exclude_valid_repo(self):
        repo = _make_repo(
            full_name="user/llm-inference-engine",
            name="llm-inference-engine",
            description="Fast LLM inference engine with quantization support",
        )
        assert _is_excluded(repo) is False

    def test_excludes_roadmap_in_name(self):
        repo = _make_repo(full_name="user/ai-roadmap", name="ai-roadmap")
        assert _is_excluded(repo) is True

    def test_excludes_interview_in_name(self):
        repo = _make_repo(full_name="user/ml-interview-prep", name="ml-interview-prep")
        assert _is_excluded(repo) is True


# ── _run ──────────────────────────────────────────────────────────

# 辅助函数：构造 Orchestrator.run 的返回值
def _make_orchestrator_result(repos=None, summary="测试趋势摘要", hot_signals=None, keywords=None):
    """构造 GitHubTrendingOrchestrator.run 的模拟返回值."""
    return (
        repos or [],
        summary,
        hot_signals or ["AI Agent", "MCP"],
        keywords or ["AI", "LLM"],
    )


class TestGitHubTrendingToolRun:
    def test_run_returns_formatted_output(self, tool, tmp_output_dir, github_env):
        """Orchestrator 返回仓库时，_run 应返回格式化的 Markdown 输出."""
        repo = _make_repo()
        with patch("ai_trending.tools.github_trending_tool.GitHubTrendingOrchestrator") as mock_cls:
            mock_cls.return_value.run.return_value = _make_orchestrator_result([repo])
            result = tool._run(query="AI", top_n=5)

        assert "cool-llm-agent" in result
        assert "GitHub 热门 AI 开源项目" in result
        assert "⭐" in result

    def test_run_returns_error_when_no_repos(self, tool, tmp_output_dir, github_env):
        """Orchestrator 返回空列表时，_run 应返回错误提示."""
        with patch("ai_trending.tools.github_trending_tool.GitHubTrendingOrchestrator") as mock_cls:
            mock_cls.return_value.run.return_value = _make_orchestrator_result([])
            result = tool._run(query="AI", top_n=5)
        assert "未能从 GitHub 搜索到" in result

    def test_run_filters_excluded_repos(self, tool, tmp_output_dir, github_env):
        """Orchestrator 只返回有效仓库（黑名单过滤在 Orchestrator 内部完成）."""
        valid_repo = _make_repo(full_name="user/new-llm-framework", name="new-llm-framework")
        with patch("ai_trending.tools.github_trending_tool.GitHubTrendingOrchestrator") as mock_cls:
            mock_cls.return_value.run.return_value = _make_orchestrator_result([valid_repo])
            result = tool._run(query="AI", top_n=5)

        assert "new-llm-framework" in result

    def test_run_respects_top_n(self, tool, tmp_output_dir, github_env):
        """只返回 top_n 个仓库."""
        repos = [_make_repo(full_name=f"user/repo-{i}", name=f"repo-{i}", stars=1000 - i) for i in range(3)]
        with patch("ai_trending.tools.github_trending_tool.GitHubTrendingOrchestrator") as mock_cls:
            mock_cls.return_value.run.return_value = _make_orchestrator_result(repos)
            result = tool._run(query="AI", top_n=3)
        # _format_results 会输出 "### 趋势判断" + 3个仓库的 "### N. ..."，共4个 ###
        assert result.count("### ") == 4

    def test_run_skips_422_queries(self, tool, tmp_output_dir, github_env):
        """Orchestrator 内部处理 422 错误，_run 应正常返回有效结果."""
        valid_repo = _make_repo()
        with patch("ai_trending.tools.github_trending_tool.GitHubTrendingOrchestrator") as mock_cls:
            mock_cls.return_value.run.return_value = _make_orchestrator_result([valid_repo])
            result = tool._run(query="AI", top_n=5)

        assert "cool-llm-agent" in result

    def test_run_without_github_token_logs_warning(self, tool, tmp_output_dir, monkeypatch):
        """没有 GITHUB_TOKEN 时应正常运行（只是速率限制更低）."""
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)
        with patch("ai_trending.tools.github_trending_tool.GitHubTrendingOrchestrator") as mock_cls:
            mock_cls.return_value.run.return_value = _make_orchestrator_result([])
            result = tool._run(query="AI", top_n=5)
        # 不应抛出异常
        assert isinstance(result, str)

    def test_run_deduplicates_repos_across_queries(self, tool, tmp_output_dir, github_env):
        """Orchestrator 内部处理去重，_run 应返回去重后的结果."""
        repo = _make_repo()
        with patch("ai_trending.tools.github_trending_tool.GitHubTrendingOrchestrator") as mock_cls:
            mock_cls.return_value.run.return_value = _make_orchestrator_result([repo])
            result = tool._run(query="AI", top_n=5)
        # _format_results 会输出 "### 趋势判断" + 1个仓库的 "### 1. ..."，共2个 ###
        assert result.count("### ") == 2

    def test_run_handles_request_failure_gracefully(self, tool, tmp_output_dir, github_env):
        """Orchestrator 失败时，_run 应优雅处理并返回错误提示."""
        with patch("ai_trending.tools.github_trending_tool.GitHubTrendingOrchestrator") as mock_cls:
            mock_cls.return_value.run.return_value = _make_orchestrator_result([])
            result = tool._run(query="AI", top_n=5)
        assert "未能从 GitHub 搜索到" in result


# ── 跨日去重集成 ──────────────────────────────────────────────────

class TestGitHubTrendingDedup:
    def test_already_seen_repos_filtered_out(self, tool, tmp_output_dir, github_env):
        """Orchestrator 内部处理去重，_run 应始终返回有效结果."""
        repo = _make_repo()

        # 第一次运行
        with patch("ai_trending.tools.github_trending_tool.GitHubTrendingOrchestrator") as mock_cls:
            mock_cls.return_value.run.return_value = _make_orchestrator_result([repo])
            tool._run(query="AI", top_n=5)

        # 第二次运行：Orchestrator 仍然返回该仓库（内部已处理去重降级）
        with patch("ai_trending.tools.github_trending_tool.GitHubTrendingOrchestrator") as mock_cls:
            mock_cls.return_value.run.return_value = _make_orchestrator_result([repo])
            result = tool._run(query="AI", top_n=5)

        # 仍然有结果
        assert "cool-llm-agent" in result
