"""tests/unit/nodes/test_nodes.py — LangGraph 节点单元测试。"""

import json
import pytest
from unittest.mock import MagicMock, patch

from ai_trending.nodes import (
    collect_github_node,
    collect_news_node,
    score_trends_node,
    write_report_node,
    publish_node,
)
from ai_trending.crew.trend_scoring.models import (
    DailySummary,
    TrendScoringOutput,
)
from ai_trending.crew.report_writing.models import ReportOutput


# ── fixtures ──────────────────────────────────────────────────────────────────

SAMPLE_GITHUB_DATA = "## GitHub 热点\n1. owner/test-repo ⭐ 5000"
SAMPLE_NEWS_DATA = "1. OpenAI 发布 GPT-5"
SAMPLE_SCORING_RESULT = json.dumps({
    "scored_repos": [{"repo": "owner/test-repo", "stars": 5000}],
    "scored_news": [],
    "daily_summary": {"top_trend": "LLM 推理优化", "hot_directions": [], "overall_sentiment": "积极"},
})
SAMPLE_REPORT = "# 🤖 AI 日报 · 2025-01-01\n\n测试日报内容"


# ── collect_github_node 测试 ───────────────────────────────────────────────────

class TestCollectGithubNode:
    """测试 collect_github_node 的 State 更新行为。"""

    def test_returns_github_data_key(self):
        """节点应返回包含 github_data 键的字典。"""
        with patch("ai_trending.tools.github_trending_tool.GitHubTrendingTool") as mock_cls:
            mock_cls.return_value._run.return_value = SAMPLE_GITHUB_DATA

            state = {"current_date": "2025-01-01"}
            result = collect_github_node(state)

            assert "github_data" in result

    def test_tool_failure_records_error(self):
        """GitHubTrendingTool 失败时，应记录错误到 errors 字段，不崩溃。"""
        with patch("ai_trending.tools.github_trending_tool.GitHubTrendingTool") as mock_cls:
            mock_cls.return_value._run.side_effect = Exception("GitHub API 超时")

            state = {"current_date": "2025-01-01"}
            result = collect_github_node(state)

            assert isinstance(result, dict)
            assert "errors" in result
            assert "github_data" in result

    def test_empty_tool_result_records_error(self):
        """GitHubTrendingTool 返回空字符串时，应记录错误。"""
        with patch("ai_trending.tools.github_trending_tool.GitHubTrendingTool") as mock_cls:
            mock_cls.return_value._run.return_value = ""

            state = {"current_date": "2025-01-01"}
            result = collect_github_node(state)

            assert "errors" in result

    def test_result_is_dict(self):
        """节点返回值必须是字典。"""
        with patch("ai_trending.tools.github_trending_tool.GitHubTrendingTool") as mock_cls:
            mock_cls.return_value._run.return_value = SAMPLE_GITHUB_DATA

            result = collect_github_node({"current_date": "2025-01-01"})
            assert isinstance(result, dict)


# ── collect_news_node 测试 ─────────────────────────────────────────────────────

class TestCollectNewsNode:
    """测试 collect_news_node 的 State 更新行为。"""

    def test_returns_news_data_key(self):
        """节点应返回包含 news_data 键的字典。"""
        with patch("ai_trending.tools.ai_news_tool.AINewsTool") as mock_cls:
            mock_cls.return_value._run.return_value = SAMPLE_NEWS_DATA

            state = {"current_date": "2025-01-01"}
            result = collect_news_node(state)

            assert "news_data" in result

    def test_tool_failure_records_error(self):
        """AINewsTool 失败时，应记录错误，不崩溃。"""
        with patch("ai_trending.tools.ai_news_tool.AINewsTool") as mock_cls:
            mock_cls.return_value._run.side_effect = Exception("新闻 API 超时")

            state = {"current_date": "2025-01-01"}
            result = collect_news_node(state)

            assert isinstance(result, dict)
            assert "errors" in result

    def test_failed_tool_result_records_error(self):
        """AINewsTool 返回 ❌ 开头的失败结果时，应记录错误。"""
        with patch("ai_trending.tools.ai_news_tool.AINewsTool") as mock_cls:
            mock_cls.return_value._run.return_value = "❌ 新闻采集失败"

            state = {"current_date": "2025-01-01"}
            result = collect_news_node(state)

            assert "errors" in result


# ── score_trends_node 测试 ─────────────────────────────────────────────────────

class TestScoreTrendsNode:
    """测试 score_trends_node 的 State 更新行为（验证已改为调用 TrendScoringCrew）。"""

    def test_returns_scoring_result_key(self):
        """节点应返回包含 scoring_result 键的字典。"""
        fake_output = TrendScoringOutput(
            scored_repos=[],
            scored_news=[],
            daily_summary=DailySummary(top_trend="测试趋势"),
        )
        with patch("ai_trending.crew.trend_scoring.TrendScoringCrew") as mock_cls:
            mock_cls.return_value.run.return_value = fake_output

            state = {
                "current_date": "2025-01-01",
                "github_data": SAMPLE_GITHUB_DATA,
                "news_data": SAMPLE_NEWS_DATA,
            }
            result = score_trends_node(state)

            assert "scoring_result" in result

    def test_scoring_result_is_valid_json(self):
        """scoring_result 应是可解析的 JSON 字符串。"""
        fake_output = TrendScoringOutput(
            scored_repos=[],
            scored_news=[],
            daily_summary=DailySummary(top_trend="测试趋势"),
        )
        with patch("ai_trending.crew.trend_scoring.TrendScoringCrew") as mock_cls:
            mock_cls.return_value.run.return_value = fake_output

            state = {
                "current_date": "2025-01-01",
                "github_data": SAMPLE_GITHUB_DATA,
                "news_data": SAMPLE_NEWS_DATA,
            }
            result = score_trends_node(state)

            # scoring_result 必须是可解析的 JSON
            parsed = json.loads(result["scoring_result"])
            assert "scored_repos" in parsed
            assert "scored_news" in parsed
            assert "daily_summary" in parsed

    def test_crew_failure_records_error_and_fallback(self):
        """TrendScoringCrew 失败时，应记录错误并返回兜底 JSON。"""
        with patch("ai_trending.crew.trend_scoring.TrendScoringCrew") as mock_cls:
            mock_cls.return_value.run.side_effect = Exception("LLM 超时")

            state = {
                "current_date": "2025-01-01",
                "github_data": SAMPLE_GITHUB_DATA,
                "news_data": SAMPLE_NEWS_DATA,
            }
            result = score_trends_node(state)

            assert isinstance(result, dict)
            assert "errors" in result
            assert "scoring_result" in result
            # 兜底 JSON 应可解析
            parsed = json.loads(result["scoring_result"])
            assert parsed["scored_repos"] == []

    def test_does_not_call_llm_directly(self):
        """节点不应直接调用 call_llm_with_usage（架构规范验证）。"""
        fake_output = TrendScoringOutput(
            scored_repos=[],
            scored_news=[],
            daily_summary=DailySummary(),
        )
        with patch("ai_trending.crew.trend_scoring.TrendScoringCrew") as mock_cls:
            mock_cls.return_value.run.return_value = fake_output
            with patch("ai_trending.llm_client.call_llm_with_usage") as mock_llm:
                state = {
                    "current_date": "2025-01-01",
                    "github_data": SAMPLE_GITHUB_DATA,
                    "news_data": SAMPLE_NEWS_DATA,
                }
                score_trends_node(state)
                # 节点层不应直接调用 call_llm_with_usage
                mock_llm.assert_not_called()


# ── write_report_node 测试 ─────────────────────────────────────────────────────

class TestWriteReportNode:
    """测试 write_report_node 的 State 更新行为。"""

    def test_returns_report_content_key(self, tmp_path, monkeypatch):
        """节点应返回包含 report_content 键的字典。"""
        monkeypatch.chdir(tmp_path)
        fake_output = ReportOutput(content=SAMPLE_REPORT, validation_issues=[])

        with patch("ai_trending.crew.report_writing.ReportWritingCrew") as mock_cls:
            mock_cls.return_value.run.return_value = fake_output

            state = {
                "current_date": "2025-01-01",
                "github_data": SAMPLE_GITHUB_DATA,
                "news_data": SAMPLE_NEWS_DATA,
                "scoring_result": SAMPLE_SCORING_RESULT,
            }
            result = write_report_node(state)

            assert "report_content" in result
            assert result["report_content"] == SAMPLE_REPORT

    def test_validation_issues_recorded_as_errors(self, tmp_path, monkeypatch):
        """格式校验问题应记录到 errors 字段，但不阻断返回。"""
        monkeypatch.chdir(tmp_path)
        fake_output = ReportOutput(
            content=SAMPLE_REPORT,
            validation_issues=["缺少必要 Section：## 趋势洞察"],
        )

        with patch("ai_trending.crew.report_writing.ReportWritingCrew") as mock_cls:
            mock_cls.return_value.run.return_value = fake_output

            state = {
                "current_date": "2025-01-01",
                "github_data": SAMPLE_GITHUB_DATA,
                "news_data": SAMPLE_NEWS_DATA,
                "scoring_result": SAMPLE_SCORING_RESULT,
            }
            result = write_report_node(state)

            assert "report_content" in result
            assert "errors" in result
            assert any("格式校验" in e for e in result["errors"])

    def test_crew_failure_records_error(self, tmp_path, monkeypatch):
        """ReportWritingCrew 失败时，应记录错误，返回兜底内容。"""
        monkeypatch.chdir(tmp_path)

        with patch("ai_trending.crew.report_writing.ReportWritingCrew") as mock_cls:
            mock_cls.return_value.run.side_effect = Exception("LLM 超时")

            state = {
                "current_date": "2025-01-01",
                "github_data": SAMPLE_GITHUB_DATA,
                "news_data": SAMPLE_NEWS_DATA,
                "scoring_result": SAMPLE_SCORING_RESULT,
            }
            result = write_report_node(state)

            assert isinstance(result, dict)
            assert "errors" in result
            assert "report_content" in result


# ── publish_node 测试 ──────────────────────────────────────────────────────────

class TestPublishNode:
    """测试 publish_node 的发布行为。"""

    def test_empty_report_skips_publish(self):
        """report_content 为空时，应跳过发布并记录错误。"""
        state = {"report_content": "", "current_date": "2025-01-01"}
        result = publish_node(state)

        assert isinstance(result, dict)
        assert "publish_results" in result

    def test_github_publish_failure_does_not_stop_wechat(self):
        """GitHub 发布失败时，微信发布应继续执行（独立容错）。"""
        with patch("ai_trending.tools.github_publish_tool.GitHubPublishTool") as mock_gh:
            mock_gh.return_value._run.side_effect = Exception("GitHub API 失败")

            with patch("ai_trending.tools.wechat_publish_tool.WeChatPublishTool") as mock_wx:
                mock_wx.return_value._run.return_value = "✅ 微信草稿创建成功"

                state = {
                    "report_content": SAMPLE_REPORT,
                    "current_date": "2025-01-01",
                }
                result = publish_node(state)

                assert "publish_results" in result
                # 微信发布结果应在列表中
                results_str = str(result["publish_results"])
                assert "微信" in results_str

    def test_publish_results_is_list(self):
        """publish_results 应是列表类型。"""
        with patch("ai_trending.tools.github_publish_tool.GitHubPublishTool") as mock_gh:
            mock_gh.return_value._run.return_value = "✅ 发布成功"
            with patch("ai_trending.tools.wechat_publish_tool.WeChatPublishTool") as mock_wx:
                mock_wx.return_value._run.return_value = "✅ 草稿创建成功"

                state = {
                    "report_content": SAMPLE_REPORT,
                    "current_date": "2025-01-01",
                }
                result = publish_node(state)

                assert isinstance(result["publish_results"], list)

    def test_result_is_dict(self):
        """节点返回值必须是字典。"""
        state = {"report_content": SAMPLE_REPORT, "current_date": "2025-01-01"}
        with patch("ai_trending.tools.github_publish_tool.GitHubPublishTool") as mock_gh:
            mock_gh.return_value._run.return_value = "✅ 成功"
            with patch("ai_trending.tools.wechat_publish_tool.WeChatPublishTool") as mock_wx:
                mock_wx.return_value._run.return_value = "✅ 成功"
                result = publish_node(state)
                assert isinstance(result, dict)
