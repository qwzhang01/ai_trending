"""tests/unit/crew/test_quality_review.py — QualityReviewCrew 单元测试。

覆盖场景：
  - QualityIssue 模型默认值和完整构造
  - QualityReviewResult 模型及属性
  - format_summary 格式化输出
  - QualityReviewCrew.run() 正常路径和兜底路径
  - _build_scoring_summary 摘要构建
  - quality_review_node 状态更新
"""

import json
from unittest.mock import MagicMock, patch

from ai_trending.crew.quality_review.models import (
    QualityIssue,
    QualityReviewResult,
)

# =========================================================================
# QualityIssue 测试
# =========================================================================


class TestQualityIssue:
    """测试 QualityIssue 模型。"""

    def test_default_values(self):
        """默认构造不报错。"""
        issue = QualityIssue()
        assert issue.severity == "info"
        assert issue.location == ""
        assert issue.description == ""
        assert issue.suggestion == ""

    def test_full_construction(self):
        """全字段构造。"""
        issue = QualityIssue(
            severity="error",
            location="今日头条",
            description="引用了'占比30%'但源数据中无此数据",
            suggestion="删除该统计数字或注明来源",
        )
        assert issue.severity == "error"
        assert issue.location == "今日头条"
        assert "30%" in issue.description

    def test_all_fields_have_description(self):
        """所有字段必须有 description（LLM 依赖它理解输出格式）。"""
        for name, field_info in QualityIssue.model_fields.items():
            assert field_info.description, f"字段 '{name}' 缺少 description"


# =========================================================================
# QualityReviewResult 测试
# =========================================================================


class TestQualityReviewResult:
    """测试 QualityReviewResult 模型。"""

    def test_default_values(self):
        """默认构造不报错。"""
        result = QualityReviewResult()
        assert result.passed is True
        assert result.overall_assessment == ""
        assert result.issues == []
        assert result.suggestions == []

    def test_full_construction(self):
        """全字段构造。"""
        result = QualityReviewResult(
            passed=False,
            overall_assessment="发现 2 处虚构数据",
            issues=[
                QualityIssue(
                    severity="error", location="今日头条", description="虚构数据"
                ),
                QualityIssue(
                    severity="warning", location="趋势洞察", description="风格问题"
                ),
                QualityIssue(
                    severity="info", location="GitHub 热点项目", description="建议优化"
                ),
            ],
            suggestions=["建议人工检查统计数据来源"],
        )
        assert result.passed is False
        assert len(result.issues) == 3
        assert len(result.suggestions) == 1

    def test_all_fields_have_description(self):
        """所有字段必须有 description。"""
        for name, field_info in QualityReviewResult.model_fields.items():
            assert field_info.description, f"字段 '{name}' 缺少 description"

    def test_error_count(self):
        """error_count 属性正确计数。"""
        result = QualityReviewResult(
            issues=[
                QualityIssue(severity="error"),
                QualityIssue(severity="error"),
                QualityIssue(severity="warning"),
                QualityIssue(severity="info"),
            ]
        )
        assert result.error_count == 2

    def test_warning_count(self):
        """warning_count 属性正确计数。"""
        result = QualityReviewResult(
            issues=[
                QualityIssue(severity="error"),
                QualityIssue(severity="warning"),
                QualityIssue(severity="warning"),
                QualityIssue(severity="info"),
            ]
        )
        assert result.warning_count == 2

    def test_error_and_warning_count_empty(self):
        """无 issues 时计数为 0。"""
        result = QualityReviewResult()
        assert result.error_count == 0
        assert result.warning_count == 0


# =========================================================================
# format_summary 测试
# =========================================================================


class TestFormatSummary:
    """测试 QualityReviewResult.format_summary()。"""

    def test_passed_summary(self):
        """通过时包含'通过'。"""
        result = QualityReviewResult(passed=True, overall_assessment="内容质量良好")
        text = result.format_summary()
        assert "通过" in text
        assert "内容质量良好" in text

    def test_failed_summary(self):
        """未通过时包含'未通过'。"""
        result = QualityReviewResult(passed=False)
        text = result.format_summary()
        assert "未通过" in text

    def test_summary_includes_issues(self):
        """摘要包含问题列表。"""
        result = QualityReviewResult(
            issues=[
                QualityIssue(
                    severity="error",
                    location="今日头条",
                    description="虚构数据",
                ),
            ]
        )
        text = result.format_summary()
        assert "[error]" in text
        assert "今日头条" in text
        assert "虚构数据" in text

    def test_summary_includes_suggestions(self):
        """摘要包含改进建议。"""
        result = QualityReviewResult(
            suggestions=["建议人工检查"],
        )
        text = result.format_summary()
        assert "建议人工检查" in text

    def test_summary_counts(self):
        """摘要包含问题数量统计。"""
        result = QualityReviewResult(
            issues=[
                QualityIssue(severity="error"),
                QualityIssue(severity="warning"),
                QualityIssue(severity="warning"),
                QualityIssue(severity="info"),
            ]
        )
        text = result.format_summary()
        assert "1 error" in text
        assert "2 warning" in text


# =========================================================================
# QualityReviewCrew 测试
# =========================================================================


class TestQualityReviewCrew:
    """测试 QualityReviewCrew 的核心行为。"""

    def test_build_scoring_summary_basic(self):
        """_build_scoring_summary 基本功能。"""
        from ai_trending.crew.quality_review.crew import QualityReviewCrew

        scoring_result = json.dumps(
            {
                "scored_repos": [
                    {
                        "name": "test/repo",
                        "stars": 5000,
                        "stars_growth_7d": 1000,
                        "language": "Python",
                    }
                ],
                "scored_news": [
                    {
                        "title": "AI 重大突破",
                        "source": "Hacker News",
                    }
                ],
                "daily_summary": {
                    "top_trend": "Agent 框架爆发",
                    "hot_directions": ["MCP", "RAG"],
                },
            }
        )
        summary = QualityReviewCrew()._build_scoring_summary(scoring_result)
        assert "test/repo" in summary
        assert "5000" in summary
        assert "AI 重大突破" in summary
        assert "Agent 框架爆发" in summary

    def test_build_scoring_summary_empty_json(self):
        """空 JSON 时返回提示文本。"""
        from ai_trending.crew.quality_review.crew import QualityReviewCrew

        summary = QualityReviewCrew()._build_scoring_summary("")
        assert "不可用" in summary or "为空" in summary

    def test_build_scoring_summary_invalid_json(self):
        """无效 JSON 时返回提示文本。"""
        from ai_trending.crew.quality_review.crew import QualityReviewCrew

        summary = QualityReviewCrew()._build_scoring_summary("not json")
        assert "不可用" in summary

    def test_fallback_review(self):
        """兜底审核结果默认通过。"""
        from ai_trending.crew.quality_review.crew import QualityReviewCrew

        review = QualityReviewCrew._fallback_review("测试错误")
        assert isinstance(review, QualityReviewResult)
        assert review.passed is True
        assert "测试错误" in review.overall_assessment

    @patch("ai_trending.llm_client.build_crewai_llm")
    def test_run_success(self, mock_llm):
        """正常运行时返回 QualityReviewResult 和 token 用量。"""
        from ai_trending.crew.quality_review.crew import QualityReviewCrew

        # Mock Crew.kickoff 返回值
        fake_review = QualityReviewResult(
            passed=True,
            overall_assessment="内容质量良好",
            issues=[
                QualityIssue(
                    severity="info", location="趋势洞察", description="可优化"
                ),
            ],
        )
        mock_result = MagicMock()
        mock_result.pydantic = fake_review
        mock_result.token_usage = MagicMock(
            prompt_tokens=200,
            completion_tokens=100,
            total_tokens=300,
            successful_requests=1,
        )
        mock_result.tasks_output = []

        crew_obj = QualityReviewCrew()
        # 直接 mock 实例的 crew 方法，避免 @CrewBase 描述符问题
        mock_crew_instance = MagicMock()
        mock_crew_instance.kickoff.return_value = mock_result
        crew_obj.crew = MagicMock(return_value=mock_crew_instance)

        review, usage = crew_obj.run(
            report_content="# AI 日报\n\n测试内容",
            scoring_result='{"scored_repos": []}',
            current_date="2026-04-01",
        )

        assert isinstance(review, QualityReviewResult)
        assert review.passed is True
        assert usage.get("total_tokens") == 300

    @patch("ai_trending.llm_client.build_crewai_llm")
    def test_run_crew_failure_returns_fallback(self, mock_llm):
        """Crew 调用失败时返回兜底结果（默认通过，不阻断发布）。"""
        from ai_trending.crew.quality_review.crew import QualityReviewCrew

        crew_obj = QualityReviewCrew()
        mock_crew_instance = MagicMock()
        mock_crew_instance.kickoff.side_effect = Exception("LLM 超时")
        crew_obj.crew = MagicMock(return_value=mock_crew_instance)

        review, usage = crew_obj.run(
            report_content="# AI 日报\n\n测试内容",
            scoring_result="{}",
            current_date="2026-04-01",
        )

        # 应返回兜底结果，不崩溃，且默认通过
        assert isinstance(review, QualityReviewResult)
        assert review.passed is True
        assert "失败" in review.overall_assessment
        assert usage == {}

    @patch("ai_trending.llm_client.build_crewai_llm")
    def test_run_empty_content_skips_review(self, mock_llm):
        """日报内容为空时跳过审核。"""
        from ai_trending.crew.quality_review.crew import QualityReviewCrew

        crew_obj = QualityReviewCrew()

        review, usage = crew_obj.run(
            report_content="",
            scoring_result="{}",
            current_date="2026-04-01",
        )

        assert isinstance(review, QualityReviewResult)
        assert review.passed is False
        assert "为空" in review.overall_assessment
        assert usage == {}


# =========================================================================
# quality_review_node 测试
# =========================================================================


class TestQualityReviewNode:
    """测试 quality_review_node 的 State 更新行为。"""

    @patch("ai_trending.crew.quality_review.QualityReviewCrew")
    def test_returns_quality_review_key(self, MockCrew):
        """节点应返回包含 quality_review 键的字典。"""
        from ai_trending.nodes import quality_review_node

        mock_review = QualityReviewResult(
            passed=True,
            overall_assessment="质量良好",
        )
        mock_instance = MagicMock()
        mock_instance.run.return_value = (mock_review, {"total_tokens": 100})
        MockCrew.return_value = mock_instance

        state = {
            "current_date": "2026-04-01",
            "report_content": "# AI 日报\n\n测试内容",
            "scoring_result": "{}",
        }
        result = quality_review_node(state)

        assert "quality_review" in result
        assert isinstance(result["quality_review"], str)
        assert "通过" in result["quality_review"]

    @patch("ai_trending.crew.quality_review.QualityReviewCrew")
    def test_crew_failure_records_error(self, MockCrew):
        """Crew 失败时记录错误到 errors 字段，不崩溃。"""
        from ai_trending.nodes import quality_review_node

        MockCrew.return_value.run.side_effect = Exception("Crew 调用失败")

        state = {
            "current_date": "2026-04-01",
            "report_content": "# AI 日报\n\n测试内容",
            "scoring_result": "{}",
        }
        result = quality_review_node(state)

        assert "quality_review" in result
        assert "errors" in result
        assert any("quality_review" in e for e in result["errors"])

    @patch("ai_trending.crew.quality_review.QualityReviewCrew")
    def test_empty_report_skips_review(self, MockCrew):
        """日报内容为空时跳过审核。"""
        from ai_trending.nodes import quality_review_node

        state = {
            "current_date": "2026-04-01",
            "report_content": "",
            "scoring_result": "{}",
        }
        result = quality_review_node(state)

        assert "quality_review" in result
        assert "跳过" in result["quality_review"]
        # Crew 不应被调用
        MockCrew.return_value.run.assert_not_called()

    @patch("ai_trending.crew.quality_review.QualityReviewCrew")
    def test_failed_report_skips_review(self, MockCrew):
        """报告生成失败时跳过审核。"""
        from ai_trending.nodes import quality_review_node

        state = {
            "current_date": "2026-04-01",
            "report_content": "# 🤖 AI 日报 · 2026-04-01\n\n报告生成失败: 某个错误",
            "scoring_result": "{}",
        }
        result = quality_review_node(state)

        assert "quality_review" in result
        assert "跳过" in result["quality_review"]
        MockCrew.return_value.run.assert_not_called()

    @patch("ai_trending.crew.quality_review.QualityReviewCrew")
    def test_review_not_passed_records_warning(self, MockCrew):
        """审核未通过时记录 warning 到 errors，但不阻断。"""
        from ai_trending.nodes import quality_review_node

        mock_review = QualityReviewResult(
            passed=False,
            overall_assessment="发现虚构数据",
            issues=[
                QualityIssue(
                    severity="error", location="今日头条", description="虚构数据"
                ),
            ],
        )
        mock_instance = MagicMock()
        mock_instance.run.return_value = (mock_review, {"total_tokens": 150})
        MockCrew.return_value = mock_instance

        state = {
            "current_date": "2026-04-01",
            "report_content": "# AI 日报\n\n测试内容",
            "scoring_result": "{}",
        }
        result = quality_review_node(state)

        assert "quality_review" in result
        assert "errors" in result
        assert any("审核未通过" in e for e in result["errors"])
        # 节点仍然正常返回，不崩溃
        assert "未通过" in result["quality_review"]

    @patch("ai_trending.crew.quality_review.QualityReviewCrew")
    def test_review_passed_with_warnings(self, MockCrew):
        """审核通过但有 warning 时记录信息。"""
        from ai_trending.nodes import quality_review_node

        mock_review = QualityReviewResult(
            passed=True,
            overall_assessment="基本合格",
            issues=[
                QualityIssue(
                    severity="warning", location="趋势洞察", description="风格偏离"
                ),
            ],
        )
        mock_instance = MagicMock()
        mock_instance.run.return_value = (mock_review, {})
        MockCrew.return_value = mock_instance

        state = {
            "current_date": "2026-04-01",
            "report_content": "# AI 日报\n\n测试内容",
            "scoring_result": "{}",
        }
        result = quality_review_node(state)

        assert "quality_review" in result
        # 有 warning 时也记录到 errors
        assert "errors" in result
        assert any("warning" in e for e in result["errors"])

    @patch("ai_trending.crew.quality_review.QualityReviewCrew")
    def test_token_usage_merged(self, MockCrew):
        """token 用量正确累加到 State。"""
        from ai_trending.nodes import quality_review_node

        mock_review = QualityReviewResult(passed=True)
        mock_instance = MagicMock()
        mock_instance.run.return_value = (
            mock_review,
            {
                "total_tokens": 200,
                "prompt_tokens": 150,
                "completion_tokens": 50,
                "successful_requests": 1,
            },
        )
        MockCrew.return_value = mock_instance

        state = {
            "current_date": "2026-04-01",
            "report_content": "# AI 日报\n\n测试内容",
            "scoring_result": "{}",
            "token_usage": {
                "total_tokens": 1000,
                "prompt_tokens": 800,
                "completion_tokens": 200,
                "successful_requests": 3,
            },
        }
        result = quality_review_node(state)

        assert "token_usage" in result
        assert result["token_usage"]["total_tokens"] == 1200
        assert result["token_usage"]["prompt_tokens"] == 950
        assert "quality_review" in result["token_usage"].get("by_node", {})
