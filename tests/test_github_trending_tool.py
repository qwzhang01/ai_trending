"""GitHub Trending Tool 测试套件.

测试重点：
1. _is_excluded 过滤逻辑 — 确保垃圾仓库被正确过滤（含新增的 prompts/gallery/template 等规则）
2. _build_trend_keywords 关键词展开 — 确保搜索词覆盖 AI 技术趋势
3. 搜索结果质量 — Mock API 响应，验证最终输出只包含有代表性的仓库
4. 排序逻辑 — 近期活跃 + 趋势话题标签 + 高 Star 综合评分
5. 新增黑名单仓库 — open-webui、lobe-chat 等纯 UI 层仓库应被过滤
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from ai_trending.tools.github_trending_tool import (
    GitHubTrendingTool,
    _build_trend_keywords,
    _is_excluded,
)


# ─────────────────────────────────────────────────────────────
# 测试夹具：构造仓库数据
# ─────────────────────────────────────────────────────────────

def _make_repo(
    full_name: str = "owner/repo",
    name: str = "repo",
    description: str = "A useful AI framework",
    stars: int = 1000,
    fork: bool = False,
    updated_at: str | None = None,
    created_at: str | None = None,
    language: str = "Python",
    topics: list[str] | None = None,
) -> dict[str, Any]:
    """构造一个标准的 GitHub 仓库数据字典."""
    now = datetime.now()
    return {
        "full_name": full_name,
        "name": name,
        "description": description,
        "stargazers_count": stars,
        "fork": fork,
        "updated_at": (updated_at or now.strftime("%Y-%m-%dT%H:%M:%SZ")),
        "created_at": (created_at or (now - timedelta(days=60)).strftime("%Y-%m-%dT%H:%M:%SZ")),
        "html_url": f"https://github.com/{full_name}",
        "language": language,
        "topics": topics or [],
    }


def _make_response(items: list[dict[str, Any]], remaining: int = 50) -> MagicMock:
    """构造一个模拟的 requests.Response 对象."""
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"total_count": len(items), "items": items}
    mock_resp.headers = {"X-RateLimit-Remaining": str(remaining)}
    return mock_resp


# ─────────────────────────────────────────────────────────────
# 1. _is_excluded 过滤逻辑测试
# ─────────────────────────────────────────────────────────────

class TestIsExcluded:
    """验证 _is_excluded 能正确识别并过滤无价值仓库."""

    # ── 应该被过滤的情况 ──────────────────────────────────────

    def test_exclude_awesome_prefix(self):
        """awesome-xxx 格式的清单仓库应被过滤."""
        repo = _make_repo(full_name="user/awesome-llm", name="awesome-llm")
        assert _is_excluded(repo) is True

    def test_exclude_awesome_suffix(self):
        """xxx-awesome 格式的清单仓库应被过滤."""
        repo = _make_repo(full_name="user/llm-awesome", name="llm-awesome")
        assert _is_excluded(repo) is True

    def test_exclude_blacklist_repo(self):
        """黑名单中的具体仓库应被过滤."""
        repo = _make_repo(full_name="f/awesome-chatgpt-prompts", name="awesome-chatgpt-prompts")
        assert _is_excluded(repo) is True

    def test_exclude_blacklist_repo_case_insensitive(self):
        """黑名单匹配不区分大小写."""
        repo = _make_repo(full_name="F/Awesome-ChatGPT-Prompts", name="Awesome-ChatGPT-Prompts")
        assert _is_excluded(repo) is True

    def test_exclude_tutorial_in_name(self):
        """名称含 tutorial 的仓库应被过滤."""
        repo = _make_repo(full_name="user/llm-tutorials", name="llm-tutorials")
        assert _is_excluded(repo) is True

    def test_exclude_course_in_name(self):
        """名称含 course 的仓库应被过滤."""
        repo = _make_repo(full_name="user/ai-courses", name="ai-courses")
        assert _is_excluded(repo) is True

    def test_exclude_roadmap_in_name(self):
        """名称含 roadmap 的仓库应被过滤."""
        repo = _make_repo(full_name="user/ai-roadmap", name="ai-roadmap")
        assert _is_excluded(repo) is True

    def test_exclude_interview_in_name(self):
        """名称含 interview 的仓库应被过滤."""
        repo = _make_repo(full_name="user/llm-interview", name="llm-interview")
        assert _is_excluded(repo) is True

    def test_exclude_cheatsheet_in_name(self):
        """名称含 cheatsheet 的仓库应被过滤."""
        repo = _make_repo(full_name="user/ai-cheatsheet", name="ai-cheatsheet")
        assert _is_excluded(repo) is True

    def test_exclude_curated_list_in_description(self):
        """描述含 'curated list' 的仓库应被过滤."""
        repo = _make_repo(
            full_name="user/ai-stuff",
            name="ai-stuff",
            description="A curated list of AI tools and resources",
        )
        assert _is_excluded(repo) is True

    def test_exclude_collection_of_resources_in_description(self):
        """描述含 'collection of resources' 的仓库应被过滤."""
        repo = _make_repo(
            full_name="user/ai-collection",
            name="ai-collection",
            description="A collection of resources for AI developers",
        )
        assert _is_excluded(repo) is True

    def test_exclude_awesome_list_in_description(self):
        """描述含 'awesome list' 的仓库应被过滤."""
        repo = _make_repo(
            full_name="user/my-list",
            name="my-list",
            description="An awesome list of LLM papers",
        )
        assert _is_excluded(repo) is True

    def test_exclude_fork_repo(self):
        """Fork 仓库应被过滤."""
        repo = _make_repo(full_name="user/langchain-fork", name="langchain-fork", fork=True)
        assert _is_excluded(repo) is True

    def test_exclude_donnemartin_system_design(self):
        """知名非技术创新仓库 system-design-primer 应被过滤."""
        repo = _make_repo(
            full_name="donnemartin/system-design-primer",
            name="system-design-primer",
        )
        assert _is_excluded(repo) is True

    def test_exclude_public_apis(self):
        """public-apis 应被过滤."""
        repo = _make_repo(full_name="public-apis/public-apis", name="public-apis")
        assert _is_excluded(repo) is True

    def test_exclude_prompts_in_name(self):
        """名称含 prompts 的仓库应被过滤（新增规则）."""
        repo = _make_repo(full_name="user/llm-prompts", name="llm-prompts")
        assert _is_excluded(repo) is True

    def test_exclude_gallery_in_name(self):
        """名称含 gallery 的仓库应被过滤（新增规则）."""
        repo = _make_repo(full_name="user/ai-gallery", name="ai-gallery")
        assert _is_excluded(repo) is True

    def test_exclude_collection_in_name(self):
        """名称含 collection 的仓库应被过滤（新增规则）."""
        repo = _make_repo(full_name="user/agent-collection", name="agent-collection")
        assert _is_excluded(repo) is True

    def test_exclude_template_suffix_in_name(self):
        """名称以 -template 结尾的仓库应被过滤（新增规则）."""
        repo = _make_repo(full_name="user/llm-template", name="llm-template")
        assert _is_excluded(repo) is True

    def test_exclude_demo_suffix_in_name(self):
        """名称以 -demo 结尾的仓库应被过滤（新增规则）."""
        repo = _make_repo(full_name="user/agent-demo", name="agent-demo")
        assert _is_excluded(repo) is True

    def test_exclude_boilerplate_suffix_in_name(self):
        """名称以 -boilerplate 结尾的仓库应被过滤（新增规则）."""
        repo = _make_repo(full_name="user/ai-boilerplate", name="ai-boilerplate")
        assert _is_excluded(repo) is True

    def test_exclude_list_of_papers_in_description(self):
        """描述含 'list of papers' 的仓库应被过滤（新增规则）."""
        repo = _make_repo(
            full_name="user/llm-papers",
            name="llm-papers",
            description="A list of papers on large language models",
        )
        assert _is_excluded(repo) is True

    def test_exclude_collection_of_models_in_description(self):
        """描述含 'collection of models' 的仓库应被过滤（新增规则）."""
        repo = _make_repo(
            full_name="user/model-zoo",
            name="model-zoo",
            description="A collection of models for various AI tasks",
        )
        assert _is_excluded(repo) is True

    def test_exclude_prompt_collection_in_description(self):
        """描述含 'prompt collection' 的仓库应被过滤（新增规则）."""
        repo = _make_repo(
            full_name="user/prompt-hub",
            name="prompt-hub",
            description="A prompt collection for LLM applications",
        )
        assert _is_excluded(repo) is True

    def test_exclude_open_webui_blacklist(self):
        """open-webui 纯 UI 层仓库应被过滤（新增黑名单）."""
        repo = _make_repo(full_name="open-webui/open-webui", name="open-webui")
        assert _is_excluded(repo) is True

    def test_exclude_lobe_chat_blacklist(self):
        """lobe-chat 纯 UI 层仓库应被过滤（新增黑名单）."""
        repo = _make_repo(full_name="lobehub/lobe-chat", name="lobe-chat")
        assert _is_excluded(repo) is True

    def test_exclude_markitdown_blacklist(self):
        """markitdown 文档转换工具应被过滤（非 AI 框架）."""
        repo = _make_repo(full_name="microsoft/markitdown", name="markitdown")
        assert _is_excluded(repo) is True

    # ── 不应该被过滤的情况 ────────────────────────────────────

    def test_keep_legitimate_llm_framework(self):
        """正常的 LLM 框架仓库不应被过滤."""
        repo = _make_repo(
            full_name="langchain-ai/langchain",
            name="langchain",
            description="Build context-aware reasoning applications",
            stars=100000,
        )
        assert _is_excluded(repo) is False

    def test_keep_vllm(self):
        """vLLM 推理框架不应被过滤."""
        repo = _make_repo(
            full_name="vllm-project/vllm",
            name="vllm",
            description="A high-throughput and memory-efficient inference engine for LLMs",
            stars=50000,
        )
        assert _is_excluded(repo) is False

    def test_keep_ollama(self):
        """Ollama 不应被过滤."""
        repo = _make_repo(
            full_name="ollama/ollama",
            name="ollama",
            description="Get up and running with large language models locally",
            stars=80000,
        )
        assert _is_excluded(repo) is False

    def test_keep_repo_with_awesome_in_description_but_not_list(self):
        """描述中含 awesome 但不是清单类的仓库不应被过滤."""
        repo = _make_repo(
            full_name="user/my-agent",
            name="my-agent",
            description="An awesome AI agent framework for production use",
        )
        assert _is_excluded(repo) is False

    def test_keep_repo_with_none_description(self):
        """描述为 None 的仓库不应崩溃，且不应被过滤（如果名称正常）."""
        repo = _make_repo(
            full_name="user/cool-llm-tool",
            name="cool-llm-tool",
            description=None,  # type: ignore[arg-type]
        )
        assert _is_excluded(repo) is False

    def test_keep_autogen(self):
        """AutoGen 框架不应被过滤（虽然 AutoGPT 在黑名单，但 AutoGen 不在）."""
        repo = _make_repo(
            full_name="microsoft/autogen",
            name="autogen",
            description="A framework for building multi-agent AI applications",
            stars=40000,
        )
        assert _is_excluded(repo) is False

    def test_keep_crewai(self):
        """CrewAI 框架不应被过滤."""
        repo = _make_repo(
            full_name="crewAIInc/crewAI",
            name="crewAI",
            description="Framework for orchestrating role-playing autonomous AI agents",
            stars=25000,
        )
        assert _is_excluded(repo) is False


# ─────────────────────────────────────────────────────────────
# 2. _build_trend_keywords 关键词展开测试
# ─────────────────────────────────────────────────────────────

class TestBuildTrendKeywords:
    """验证关键词展开逻辑覆盖 AI 技术趋势核心词."""

    def test_ai_query_expands_to_trend_keywords(self):
        """'AI' 查询应展开为 LLM、AI agent、RAG 等趋势关键词."""
        keywords = _build_trend_keywords("AI")
        assert "LLM" in keywords
        assert "AI agent" in keywords
        assert "RAG" in keywords

    def test_ai_query_keeps_original(self):
        """展开后应保留原始查询词."""
        keywords = _build_trend_keywords("AI")
        assert "AI" in keywords

    def test_llm_query_expands(self):
        """'LLM' 查询应展开为 large language model、fine-tuning 等."""
        keywords = _build_trend_keywords("LLM")
        assert "large language model" in keywords
        assert "fine-tuning" in keywords
        assert "inference" in keywords

    def test_agent_query_expands(self):
        """'agent' 查询应展开为 autonomous agent、agentic 等."""
        keywords = _build_trend_keywords("agent")
        assert "autonomous agent" in keywords
        assert "agentic" in keywords
        assert "multi-agent" in keywords

    def test_machine_learning_query_expands(self):
        """'machine learning' 查询应展开为 deep learning、diffusion model 等."""
        keywords = _build_trend_keywords("machine learning")
        assert "deep learning" in keywords
        assert "diffusion model" in keywords

    def test_unknown_query_returns_itself(self):
        """未知查询词应原样返回，不崩溃."""
        keywords = _build_trend_keywords("some-unknown-topic")
        assert "some-unknown-topic" in keywords
        assert len(keywords) == 1

    def test_no_duplicate_keywords(self):
        """返回的关键词列表不应有重复（大小写不敏感）."""
        keywords = _build_trend_keywords("AI")
        lower_keywords = [k.lower() for k in keywords]
        assert len(lower_keywords) == len(set(lower_keywords)), "关键词列表存在重复"

    def test_case_insensitive_match(self):
        """关键词匹配应不区分大小写."""
        keywords_lower = _build_trend_keywords("ai")
        keywords_upper = _build_trend_keywords("AI")
        assert set(k.lower() for k in keywords_lower) == set(k.lower() for k in keywords_upper)

    def test_mcp_keyword_included_for_ai(self):
        """AI 查询应包含 MCP（Model Context Protocol）这一新兴趋势词."""
        keywords = _build_trend_keywords("AI")
        assert "MCP" in keywords

    def test_multimodal_keyword_included_for_ai(self):
        """AI 查询应包含 multimodal 关键词."""
        keywords = _build_trend_keywords("AI")
        assert "multimodal" in keywords


# ─────────────────────────────────────────────────────────────
# 3. 搜索结果质量测试（Mock API）
# ─────────────────────────────────────────────────────────────

class TestGitHubTrendingToolRun:
    """通过 Mock GitHub API 验证工具的完整搜索 + 过滤 + 排序流程."""

    # 代表性的"好仓库"（应出现在结果中）
    GOOD_REPOS = [
        _make_repo(
            full_name="vllm-project/vllm",
            name="vllm",
            description="High-throughput LLM inference engine",
            stars=55000,
            updated_at=(datetime.now() - timedelta(days=2)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        ),
        _make_repo(
            full_name="langchain-ai/langchain",
            name="langchain",
            description="Build context-aware reasoning applications with LLMs",
            stars=100000,
            updated_at=(datetime.now() - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        ),
        _make_repo(
            full_name="microsoft/autogen",
            name="autogen",
            description="Multi-agent AI framework",
            stars=40000,
            updated_at=(datetime.now() - timedelta(days=3)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        ),
    ]

    # 应该被过滤掉的"垃圾仓库"
    BAD_REPOS = [
        _make_repo(
            full_name="user/awesome-llm-list",
            name="awesome-llm-list",
            description="A curated list of LLM resources",
            stars=20000,
        ),
        _make_repo(
            full_name="user/llm-tutorials",
            name="llm-tutorials",
            description="Learn LLM step by step",
            stars=15000,
        ),
        _make_repo(
            full_name="user/ai-interview-questions",
            name="ai-interview-questions",
            description="AI interview prep",
            stars=10000,
        ),
        _make_repo(
            full_name="f/awesome-chatgpt-prompts",
            name="awesome-chatgpt-prompts",
            description="Prompts for ChatGPT",
            stars=120000,
        ),
        _make_repo(
            full_name="user/forked-langchain",
            name="forked-langchain",
            description="Fork of langchain",
            stars=5000,
            fork=True,
        ),
    ]

    def _run_with_mock(self, repos: list[dict[str, Any]], top_n: int = 10) -> str:
        """用 Mock 数据运行工具，返回输出字符串.

        同时 mock 掉 DedupCache，避免测试之间通过真实缓存文件互相污染。
        """
        tool = GitHubTrendingTool()
        mock_resp = _make_response(repos)

        # DedupCache mock：filter_new 直接透传（不过滤），mark_seen 空操作
        class _NoopDedup:
            def filter_new(self, items, key_fn):
                return items
            def mark_seen(self, keys):
                pass
            def stats(self):
                return {}

        with patch("ai_trending.tools.github_trending_tool.safe_request", return_value=mock_resp), \
             patch("ai_trending.tools.github_trending_tool.DedupCache", return_value=_NoopDedup()):
            return tool._run(query="AI", top_n=top_n)

    def test_good_repos_appear_in_output(self):
        """有代表性的技术仓库应出现在输出中."""
        all_repos = self.GOOD_REPOS + self.BAD_REPOS
        output = self._run_with_mock(all_repos)
        assert "vllm-project/vllm" in output
        assert "langchain-ai/langchain" in output
        assert "microsoft/autogen" in output

    def test_bad_repos_filtered_from_output(self):
        """垃圾仓库（清单/教程/面试题/fork）不应出现在输出中."""
        all_repos = self.GOOD_REPOS + self.BAD_REPOS
        output = self._run_with_mock(all_repos)
        assert "awesome-llm-list" not in output
        assert "llm-tutorials" not in output
        assert "ai-interview-questions" not in output
        assert "awesome-chatgpt-prompts" not in output
        assert "forked-langchain" not in output

    def test_output_contains_stars_info(self):
        """输出应包含 Star 数信息."""
        output = self._run_with_mock(self.GOOD_REPOS)
        assert "⭐" in output

    def test_output_contains_repo_links(self):
        """输出应包含仓库链接."""
        output = self._run_with_mock(self.GOOD_REPOS)
        assert "https://github.com/" in output

    def test_top_n_limits_results(self):
        """top_n 参数应限制返回数量."""
        repos = self.GOOD_REPOS  # 3 个好仓库
        output = self._run_with_mock(repos, top_n=2)
        # 输出中最多只有 2 个排名
        assert "### 3." not in output
        assert "### 1." in output
        assert "### 2." in output

    def test_empty_api_response_returns_warning(self):
        """API 返回空结果时，应返回友好的提示信息而非崩溃."""
        tool = GitHubTrendingTool()
        mock_resp = _make_response([])
        with patch("ai_trending.tools.github_trending_tool.safe_request", return_value=mock_resp), \
             patch("ai_trending.tools.github_trending_tool.DedupCache"):
            output = tool._run(query="AI", top_n=5)
        assert "未能从 GitHub 搜索到" in output

    def test_api_failure_returns_warning(self):
        """API 请求失败（safe_request 返回 None）时，应返回友好提示."""
        tool = GitHubTrendingTool()
        with patch("ai_trending.tools.github_trending_tool.safe_request", return_value=None), \
             patch("ai_trending.tools.github_trending_tool.DedupCache"):
            output = tool._run(query="AI", top_n=5)
        assert "未能从 GitHub 搜索到" in output

    def test_deduplication_across_queries(self):
        """同一仓库在多次查询中出现时，结果中只保留一份（排名条目不重复）."""
        # 模拟 3 次查询都返回同一批仓库
        tool = GitHubTrendingTool()
        mock_resp = _make_response(self.GOOD_REPOS)

        class _NoopDedup:
            def filter_new(self, items, key_fn):
                return items
            def mark_seen(self, keys):
                pass
            def stats(self):
                return {}

        with patch("ai_trending.tools.github_trending_tool.safe_request", return_value=mock_resp), \
             patch("ai_trending.tools.github_trending_tool.DedupCache", return_value=_NoopDedup()):
            output = tool._run(query="AI", top_n=10)
        # 仓库名会出现在标题（### N. owner/repo）和链接行中，共 2 次
        # 去重后 vllm 只有 1 个排名条目，即标题行只出现 1 次
        import re
        heading_matches = re.findall(r"### \d+\. vllm-project/vllm", output)
        assert len(heading_matches) == 1, f"vllm 排名条目应只出现 1 次，实际出现 {len(heading_matches)} 次"

    def test_output_format_has_required_fields(self):
        """输出格式应包含链接、描述、Stars、语言、创建时间、更新时间等字段."""
        output = self._run_with_mock(self.GOOD_REPOS)
        assert "**链接**" in output
        assert "**描述**" in output
        assert "**Stars**" in output
        assert "**语言**" in output
        assert "**创建**" in output
        assert "**更新**" in output

    def test_recently_updated_repos_ranked_higher(self):
        """近期更新的仓库应排在未近期更新的仓库前面（Star 数相近时）."""
        recent_repo = _make_repo(
            full_name="user/recent-agent",
            name="recent-agent",
            description="A new AI agent framework",
            stars=2000,
            updated_at=(datetime.now() - timedelta(days=5)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        )
        old_repo = _make_repo(
            full_name="user/old-agent",
            name="old-agent",
            description="An old AI agent framework",
            stars=2500,  # Star 略多，但很久没更新
            updated_at=(datetime.now() - timedelta(days=90)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        )
        tool = GitHubTrendingTool()
        mock_resp = _make_response([old_repo, recent_repo])
        with patch("ai_trending.tools.github_trending_tool.safe_request", return_value=mock_resp):
            output = tool._run(query="AI", top_n=5)
        # recent_repo 应排在 old_repo 前面
        recent_pos = output.find("user/recent-agent")
        old_pos = output.find("user/old-agent")
        assert recent_pos < old_pos, "近期更新的仓库应排在更前面"

    def test_trend_topic_repos_ranked_higher(self):
        """命中趋势话题标签的仓库应排在无标签仓库前面（Star 数相近时）."""
        trend_repo = _make_repo(
            full_name="user/agentic-framework",
            name="agentic-framework",
            description="An agentic AI framework",
            stars=3000,
            updated_at=(datetime.now() - timedelta(days=5)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            topics=["agentic", "multi-agent", "llm"],  # 命中趋势话题
        )
        no_topic_repo = _make_repo(
            full_name="user/plain-llm",
            name="plain-llm",
            description="A plain LLM tool",
            stars=3500,  # Star 略多，但无趋势话题
            updated_at=(datetime.now() - timedelta(days=5)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            topics=[],
        )
        tool = GitHubTrendingTool()
        mock_resp = _make_response([no_topic_repo, trend_repo])
        with patch("ai_trending.tools.github_trending_tool.safe_request", return_value=mock_resp):
            output = tool._run(query="AI", top_n=5)
        trend_pos = output.find("user/agentic-framework")
        plain_pos = output.find("user/plain-llm")
        assert trend_pos < plain_pos, "命中趋势话题标签的仓库应排在前面"

    def test_high_star_repos_ranked_higher_when_both_recent(self):
        """两个仓库都是近期更新时，Star 数更多的应排在前面."""
        high_star = _make_repo(
            full_name="user/high-star-llm",
            name="high-star-llm",
            description="Popular LLM framework",
            stars=50000,
            updated_at=(datetime.now() - timedelta(days=2)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        )
        low_star = _make_repo(
            full_name="user/low-star-llm",
            name="low-star-llm",
            description="Less popular LLM framework",
            stars=5000,
            updated_at=(datetime.now() - timedelta(days=3)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        )
        tool = GitHubTrendingTool()
        mock_resp = _make_response([low_star, high_star])
        with patch("ai_trending.tools.github_trending_tool.safe_request", return_value=mock_resp):
            output = tool._run(query="AI", top_n=5)
        high_pos = output.find("user/high-star-llm")
        low_pos = output.find("user/low-star-llm")
        assert high_pos < low_pos, "Star 数更多的仓库应排在前面"


# ─────────────────────────────────────────────────────────────
# 4. 边界情况测试
# ─────────────────────────────────────────────────────────────

class TestEdgeCases:
    """边界情况和异常输入测试."""

    def test_repo_with_empty_name(self):
        """名称为空字符串的仓库不应崩溃."""
        repo = _make_repo(full_name="user/", name="", description="Some AI tool")
        # 空名称不匹配任何过滤规则，不应被过滤
        result = _is_excluded(repo)
        assert isinstance(result, bool)

    def test_repo_with_very_long_description(self):
        """超长描述不应导致崩溃."""
        repo = _make_repo(
            full_name="user/ai-tool",
            name="ai-tool",
            description="A" * 10000,
        )
        result = _is_excluded(repo)
        assert isinstance(result, bool)

    def test_build_keywords_with_empty_string(self):
        """空字符串查询不应崩溃."""
        keywords = _build_trend_keywords("")
        assert isinstance(keywords, list)

    def test_build_keywords_with_whitespace(self):
        """纯空格查询不应崩溃."""
        keywords = _build_trend_keywords("   ")
        assert isinstance(keywords, list)

    def test_tool_without_github_token(self):
        """没有 GITHUB_TOKEN 时工具应正常运行（只是速率限制更严格）."""
        import os
        tool = GitHubTrendingTool()
        mock_resp = _make_response([
            _make_repo(
                full_name="user/ai-framework",
                name="ai-framework",
                description="An AI framework",
                stars=1000,
            )
        ])
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("GITHUB_TOKEN", None)
            with patch("ai_trending.tools.github_trending_tool.safe_request", return_value=mock_resp):
                output = tool._run(query="AI", top_n=5)
        assert "ai-framework" in output

    def test_exclude_learning_resources_in_description(self):
        """描述含 'learning resources' 的仓库应被过滤."""
        repo = _make_repo(
            full_name="user/ai-learn",
            name="ai-learn",
            description="Learning resources for AI and machine learning",
        )
        assert _is_excluded(repo) is True

    def test_exclude_study_guide_in_description(self):
        """描述含 'study guide' 的仓库应被过滤."""
        repo = _make_repo(
            full_name="user/llm-guide",
            name="llm-guide",
            description="A comprehensive study guide for LLMs",
        )
        assert _is_excluded(repo) is True
