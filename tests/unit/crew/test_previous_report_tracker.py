"""tests/unit/crew/test_previous_report_tracker.py — PreviousReportTracker 单元测试。"""

import json
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from ai_trending.crew.report_writing.tracker import PreviousReportTracker, TrackedRepo


# ── fixtures ──────────────────────────────────────────────────────────────────

SAMPLE_REPORT_CONTENT = """# AI 日报 · 2026-03-25

**[今日信号强度]** 🟡 常规更新日
> **[今日一句话]** MCP生态爆发，端侧Agent落地提速

---

## 今日头条

### [firerpa/lamda](https://github.com/firerpa/lamda) ⭐ 7691（+1240）
移动端自动化此前一直面临操作碎片化的问题...

---

## GitHub 热点项目

### 1. [calesthio/Crucix](https://github.com/calesthio/Crucix) ⭐ 6779（+4200）
一句话：个人情报自动监测助手

### 2. [firecrawl/firecrawl-mcp-server](https://github.com/firecrawl/firecrawl-mcp-server) ⭐ 5849（+920）
一句话：LLM网页数据接入工具

### 3. [can1357/oh-my-pi](https://github.com/can1357/oh-my-pi) ⭐ 2361（+870）
一句话：终端原生AI编码助手
"""

SAMPLE_GITHUB_API_RESPONSE = {
    "full_name": "firerpa/lamda",
    "stargazers_count": 8200,
    "description": "测试仓库",
}


@pytest.fixture
def tmp_reports_dir(tmp_path):
    """创建临时 reports 目录并写入示例报告。"""
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()
    report_file = reports_dir / "2026-03-25.md"
    report_file.write_text(SAMPLE_REPORT_CONTENT, encoding="utf-8")
    return reports_dir


@pytest.fixture
def tracker(tmp_reports_dir):
    """创建指向临时目录的 PreviousReportTracker 实例。"""
    return PreviousReportTracker(reports_dir=tmp_reports_dir)


# ── _find_previous_report 测试 ─────────────────────────────────────────────────

class TestFindPreviousReport:
    """测试 _find_previous_report 的文件查找逻辑。"""

    def test_finds_most_recent_report(self, tracker, tmp_reports_dir):
        """应找到最近一期报告（2026-03-25）。"""
        path, found_date = tracker._find_previous_report("2026-03-26")
        assert path is not None
        assert found_date == "2026-03-25"
        assert path.name == "2026-03-25.md"

    def test_skips_current_date(self, tracker, tmp_reports_dir):
        """不应返回当天的报告。"""
        # 创建当天报告
        (tmp_reports_dir / "2026-03-26.md").write_text("今天的报告", encoding="utf-8")
        path, found_date = tracker._find_previous_report("2026-03-26")
        # 应返回 2026-03-25，而不是 2026-03-26
        assert found_date == "2026-03-25"

    def test_returns_none_when_no_reports(self, tmp_path):
        """reports 目录为空时，应返回 (None, '')。"""
        empty_dir = tmp_path / "empty_reports"
        empty_dir.mkdir()
        tracker = PreviousReportTracker(reports_dir=empty_dir)
        path, found_date = tracker._find_previous_report("2026-03-26")
        assert path is None
        assert found_date == ""

    def test_returns_none_when_dir_not_exists(self, tmp_path):
        """reports 目录不存在时，应返回 (None, '')。"""
        tracker = PreviousReportTracker(reports_dir=tmp_path / "nonexistent")
        path, found_date = tracker._find_previous_report("2026-03-26")
        assert path is None
        assert found_date == ""

    def test_invalid_date_format(self, tracker):
        """日期格式错误时，应返回 (None, '')。"""
        path, found_date = tracker._find_previous_report("not-a-date")
        assert path is None
        assert found_date == ""

    def test_looks_back_multiple_days(self, tmp_path):
        """应向前查找多天，找到最近的报告。"""
        reports_dir = tmp_path / "reports"
        reports_dir.mkdir()
        # 只有 3 天前的报告
        (reports_dir / "2026-03-23.md").write_text("三天前的报告", encoding="utf-8")
        tracker = PreviousReportTracker(reports_dir=reports_dir)
        path, found_date = tracker._find_previous_report("2026-03-26")
        assert found_date == "2026-03-23"


# ── _parse_recommended_repos 测试 ─────────────────────────────────────────────

class TestParseRecommendedRepos:
    """测试 _parse_recommended_repos 的解析逻辑。"""

    def test_parses_repos_from_report(self, tracker, tmp_reports_dir):
        """应从报告中解析出 GitHub 项目。"""
        report_path = tmp_reports_dir / "2026-03-25.md"
        repos = tracker._parse_recommended_repos(report_path)
        assert len(repos) > 0
        # 检查第一个项目（头条）
        repo_names = [r[0] for r in repos]
        assert "firerpa/lamda" in repo_names

    def test_extracts_star_count(self, tracker, tmp_reports_dir):
        """应正确提取 Star 数。"""
        report_path = tmp_reports_dir / "2026-03-25.md"
        repos = tracker._parse_recommended_repos(report_path)
        lamda = next((r for r in repos if r[0] == "firerpa/lamda"), None)
        assert lamda is not None
        assert lamda[2] == 7691  # prev_stars

    def test_deduplicates_repos(self, tracker, tmp_path):
        """同一个仓库出现多次时，只保留第一次。"""
        reports_dir = tmp_path / "reports"
        reports_dir.mkdir(exist_ok=True)
        content = """
### [owner/repo](https://github.com/owner/repo) ⭐ 1000
### [owner/repo](https://github.com/owner/repo) ⭐ 1000
"""
        (reports_dir / "2026-03-25.md").write_text(content, encoding="utf-8")
        tracker = PreviousReportTracker(reports_dir=reports_dir)
        repos = tracker._parse_recommended_repos(reports_dir / "2026-03-25.md")
        assert len([r for r in repos if r[0] == "owner/repo"]) == 1

    def test_limits_to_max_repos(self, tracker, tmp_path):
        """最多返回 _MAX_TRACK_REPOS 个项目。"""
        from ai_trending.crew.report_writing.tracker import _MAX_TRACK_REPOS
        reports_dir = tmp_path / "reports"
        reports_dir.mkdir(exist_ok=True)
        # 创建超过限制数量的项目
        lines = []
        for i in range(_MAX_TRACK_REPOS + 3):
            lines.append(f"### [owner/repo{i}](https://github.com/owner/repo{i}) ⭐ {1000 + i}")
        content = "\n".join(lines)
        (reports_dir / "2026-03-25.md").write_text(content, encoding="utf-8")
        tracker = PreviousReportTracker(reports_dir=reports_dir)
        repos = tracker._parse_recommended_repos(reports_dir / "2026-03-25.md")
        assert len(repos) <= _MAX_TRACK_REPOS

    def test_returns_empty_for_nonexistent_file(self, tracker, tmp_path):
        """文件不存在时，应返回空列表。"""
        repos = tracker._parse_recommended_repos(tmp_path / "nonexistent.md")
        assert repos == []

    def test_filters_invalid_repo_names(self, tracker, tmp_path):
        """过滤含特殊字符的非法 repo 名。"""
        reports_dir = tmp_path / "reports"
        reports_dir.mkdir(exist_ok=True)
        content = "### [test](https://github.com/owner/repo#section) ⭐ 1000\n"
        (reports_dir / "2026-03-25.md").write_text(content, encoding="utf-8")
        tracker = PreviousReportTracker(reports_dir=reports_dir)
        repos = tracker._parse_recommended_repos(reports_dir / "2026-03-25.md")
        # 含 # 的 repo 名应被过滤
        assert all("#" not in r[0] for r in repos)


# ── _fetch_current_stars 测试 ──────────────────────────────────────────────────

class TestFetchCurrentStars:
    """测试 _fetch_current_stars 的 GitHub API 调用逻辑。"""

    def test_returns_tracked_repos_on_success(self, tracker):
        """API 调用成功时，应返回 TrackedRepo 列表。"""
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"stargazers_count": 8200}

        with patch("ai_trending.crew.report_writing.tracker.safe_request") as mock_req:
            mock_req.return_value = mock_resp
            repos = [("firerpa/lamda", "lamda", 7691)]
            tracked = tracker._fetch_current_stars(repos, "2026-03-25")

        assert len(tracked) == 1
        assert tracked[0].repo == "firerpa/lamda"
        assert tracked[0].curr_stars == 8200
        assert tracked[0].prev_stars == 7691
        assert tracked[0].growth == 509

    def test_skips_failed_requests(self, tracker):
        """API 调用失败时，应跳过该项目，不崩溃。"""
        with patch("ai_trending.crew.report_writing.tracker.safe_request") as mock_req:
            mock_req.return_value = None  # safe_request 失败返回 None
            repos = [("owner/repo", "repo", 1000)]
            tracked = tracker._fetch_current_stars(repos, "2026-03-25")

        assert tracked == []

    def test_calculates_negative_growth(self, tracker):
        """星数下降时，growth 应为负数。"""
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"stargazers_count": 900}

        with patch("ai_trending.crew.report_writing.tracker.safe_request") as mock_req:
            mock_req.return_value = mock_resp
            repos = [("owner/repo", "repo", 1000)]
            tracked = tracker._fetch_current_stars(repos, "2026-03-25")

        assert tracked[0].growth == -100

    def test_uses_github_token_when_available(self, tracker, monkeypatch):
        """有 GITHUB_TOKEN 时，应在请求头中携带 Authorization。"""
        monkeypatch.setenv("GITHUB_TOKEN", "test-token-123")
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"stargazers_count": 1000}

        with patch("ai_trending.crew.report_writing.tracker.safe_request") as mock_req:
            mock_req.return_value = mock_resp
            tracker._fetch_current_stars([("owner/repo", "repo", 900)], "2026-03-25")

            # 验证请求头中包含 Authorization
            call_kwargs = mock_req.call_args[1]
            assert "headers" in call_kwargs
            assert "Authorization" in call_kwargs["headers"]
            assert "test-token-123" in call_kwargs["headers"]["Authorization"]


# ── _format_context 测试 ──────────────────────────────────────────────────────

class TestFormatContext:
    """测试 _format_context 的格式化逻辑。"""

    def test_returns_non_empty_string(self, tracker):
        """有追踪数据时，应返回非空字符串。"""
        tracked = [
            TrackedRepo(
                repo="owner/repo",
                name="repo",
                prev_stars=1000,
                curr_stars=1500,
                growth=500,
                report_date="2026-03-25",
            )
        ]
        context = tracker._format_context(tracked, "2026-03-25")
        assert isinstance(context, str)
        assert len(context) > 0

    def test_contains_star_numbers(self, tracker):
        """上下文应包含真实的星数数字。"""
        tracked = [
            TrackedRepo(
                repo="owner/repo",
                name="repo",
                prev_stars=7691,
                curr_stars=8200,
                growth=509,
                report_date="2026-03-25",
            )
        ]
        context = tracker._format_context(tracked, "2026-03-25")
        assert "7,691" in context or "7691" in context
        assert "8,200" in context or "8200" in context

    def test_contains_growth_trend_hint(self, tracker):
        """上下文应包含趋势判断提示。"""
        # 增长强劲（>500）
        tracked_strong = [TrackedRepo("r/r", "r", 1000, 2000, 1000, "2026-03-25")]
        context = tracker._format_context(tracked_strong, "2026-03-25")
        assert "增长强劲" in context

        # 增长放缓（0-100）
        tracked_slow = [TrackedRepo("r/r", "r", 1000, 1050, 50, "2026-03-25")]
        context = tracker._format_context(tracked_slow, "2026-03-25")
        assert "增长放缓" in context

        # 星数下降（<0）
        tracked_down = [TrackedRepo("r/r", "r", 1000, 900, -100, "2026-03-25")]
        context = tracker._format_context(tracked_down, "2026-03-25")
        assert "星数下降" in context

    def test_contains_writing_guidelines(self, tracker):
        """上下文应包含撰写指引。"""
        tracked = [TrackedRepo("r/r", "r", 1000, 1500, 500, "2026-03-25")]
        context = tracker._format_context(tracked, "2026-03-25")
        assert "撰写指引" in context
        assert "禁止修改数字" in context


# ── get_previous_report_context 集成测试 ──────────────────────────────────────

class TestGetPreviousReportContext:
    """测试 get_previous_report_context 的完整流程。"""

    def test_returns_context_on_success(self, tracker):
        """正常流程下，应返回非空上下文字符串。"""
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"stargazers_count": 8200}

        with patch("ai_trending.crew.report_writing.tracker.safe_request") as mock_req:
            mock_req.return_value = mock_resp
            context = tracker.get_previous_report_context("2026-03-26")

        assert isinstance(context, str)
        assert len(context) > 0
        assert "上期回顾数据" in context

    def test_returns_empty_when_no_history(self, tmp_path):
        """无历史报告时，应返回空字符串。"""
        empty_dir = tmp_path / "reports"
        empty_dir.mkdir()
        tracker = PreviousReportTracker(reports_dir=empty_dir)
        context = tracker.get_previous_report_context("2026-03-26")
        assert context == ""

    def test_returns_empty_on_api_failure(self, tracker):
        """GitHub API 全部失败时，应返回空字符串（不崩溃）。"""
        with patch("ai_trending.crew.report_writing.tracker.safe_request") as mock_req:
            mock_req.return_value = None
            context = tracker.get_previous_report_context("2026-03-26")

        assert context == ""

    def test_returns_empty_on_unexpected_exception(self, tracker):
        """意外异常时，应返回空字符串（不崩溃）。"""
        with patch.object(tracker, "_find_previous_report", side_effect=Exception("意外错误")):
            context = tracker.get_previous_report_context("2026-03-26")

        assert context == ""

    def test_result_is_string_type(self, tracker):
        """返回值必须是字符串类型。"""
        with patch("ai_trending.crew.report_writing.tracker.safe_request") as mock_req:
            mock_req.return_value = None
            result = tracker.get_previous_report_context("2026-03-26")

        assert isinstance(result, str)
