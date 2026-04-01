"""tests/unit/crew/test_editorial_planning.py — EditorialPlanningCrew 单元测试。

覆盖场景：
  - EditorialPlan 模型默认值和完整构造
  - HeadlineDecision 和 AngleAssignment 模型
  - format_for_prompt 格式化输出
  - EditorialPlanningCrew.run() 正常路径和兜底路径
  - _build_scoring_summary 摘要构建
  - editorial_planning_node 状态更新
"""

import json
from unittest.mock import MagicMock, patch

from ai_trending.crew.editorial_planning.models import (
    AngleAssignment,
    EditorialPlan,
    HeadlineDecision,
)

# =========================================================================
# HeadlineDecision 测试
# =========================================================================


class TestHeadlineDecision:
    """测试 HeadlineDecision 模型。"""

    def test_default_values(self):
        """默认构造不报错。"""
        h = HeadlineDecision()
        assert h.chosen_item == ""
        assert h.reason == ""
        assert h.angle == ""

    def test_full_construction(self):
        """全字段构造。"""
        h = HeadlineDecision(
            chosen_item="openai/gpt-5",
            reason="发布首日星数破万",
            angle="规模切入",
        )
        assert h.chosen_item == "openai/gpt-5"
        assert h.reason == "发布首日星数破万"

    def test_all_fields_have_description(self):
        for name, field_info in HeadlineDecision.model_fields.items():
            assert field_info.description, f"字段 '{name}' 缺少 description"


# =========================================================================
# AngleAssignment 测试
# =========================================================================


class TestAngleAssignment:
    """测试 AngleAssignment 模型。"""

    def test_default_values(self):
        a = AngleAssignment()
        assert a.item_name == ""
        assert a.angle == ""
        assert a.key_point == ""

    def test_full_construction(self):
        a = AngleAssignment(
            item_name="langchain/langchain",
            angle="痛点切入",
            key_point="解决了 Agent 编排的复杂性问题",
        )
        assert a.item_name == "langchain/langchain"
        assert a.angle == "痛点切入"

    def test_all_fields_have_description(self):
        for name, field_info in AngleAssignment.model_fields.items():
            assert field_info.description, f"字段 '{name}' 缺少 description"


# =========================================================================
# EditorialPlan 测试
# =========================================================================


class TestEditorialPlan:
    """测试 EditorialPlan 模型。"""

    def test_default_values(self):
        plan = EditorialPlan()
        assert plan.signal_strength == "yellow"
        assert plan.signal_reason == ""
        assert isinstance(plan.headline, HeadlineDecision)
        assert plan.repo_angles == []
        assert plan.news_angles == []
        assert plan.kill_list == []
        assert plan.today_hook == ""

    def test_full_construction(self):
        plan = EditorialPlan(
            signal_strength="red",
            signal_reason="GPT-5 发布引爆社区",
            headline=HeadlineDecision(
                chosen_item="openai/gpt-5",
                reason="里程碑事件",
                angle="规模切入",
            ),
            repo_angles=[
                AngleAssignment(
                    item_name="repo1", angle="痛点切入", key_point="解决了X"
                ),
                AngleAssignment(
                    item_name="repo2", angle="成本切入", key_point="降低了Y"
                ),
            ],
            news_angles=[
                AngleAssignment(
                    item_name="news1", angle="对比切入", key_point="与Z不同"
                ),
            ],
            kill_list=["old_repo: 与昨日重复"],
            today_hook="GPT-5 改变了游戏规则",
        )
        assert plan.signal_strength == "red"
        assert plan.headline.chosen_item == "openai/gpt-5"
        assert len(plan.repo_angles) == 2
        assert len(plan.news_angles) == 1
        assert len(plan.kill_list) == 1

    def test_all_fields_have_description(self):
        for name, field_info in EditorialPlan.model_fields.items():
            assert field_info.description, f"字段 '{name}' 缺少 description"


# =========================================================================
# format_for_prompt 测试
# =========================================================================


class TestFormatForPrompt:
    """测试 EditorialPlan.format_for_prompt()。"""

    def test_empty_plan(self):
        """空 Plan 格式化不报错。"""
        text = EditorialPlan().format_for_prompt()
        assert "编辑决策" in text
        assert "🟡 常规更新日" in text

    def test_red_signal(self):
        plan = EditorialPlan(signal_strength="red")
        text = plan.format_for_prompt()
        assert "🔴 重大变化日" in text

    def test_green_signal(self):
        plan = EditorialPlan(signal_strength="green")
        text = plan.format_for_prompt()
        assert "🟢 平静日" in text

    def test_unknown_signal_defaults_to_yellow(self):
        plan = EditorialPlan(signal_strength="unknown")
        text = plan.format_for_prompt()
        assert "🟡 常规更新日" in text

    def test_headline_displayed(self):
        plan = EditorialPlan(
            headline=HeadlineDecision(
                chosen_item="test/repo",
                reason="测试理由",
                angle="痛点切入",
            )
        )
        text = plan.format_for_prompt()
        assert "test/repo" in text
        assert "痛点切入" in text
        assert "测试理由" in text

    def test_today_hook_displayed(self):
        plan = EditorialPlan(today_hook="AI 编程工具从辅助走向主导")
        text = plan.format_for_prompt()
        assert "AI 编程工具从辅助走向主导" in text

    def test_repo_angles_displayed(self):
        plan = EditorialPlan(
            repo_angles=[
                AngleAssignment(
                    item_name="repo1", angle="痛点切入", key_point="解决了X"
                ),
            ]
        )
        text = plan.format_for_prompt()
        assert "repo1" in text
        assert "痛点切入" in text
        assert "解决了X" in text

    def test_news_angles_displayed(self):
        plan = EditorialPlan(
            news_angles=[
                AngleAssignment(item_name="news1", angle="对比切入"),
            ]
        )
        text = plan.format_for_prompt()
        assert "news1" in text
        assert "对比切入" in text

    def test_kill_list_displayed(self):
        plan = EditorialPlan(kill_list=["MCP: 连续报道2天"])
        text = plan.format_for_prompt()
        assert "排除内容" in text
        assert "MCP" in text

    def test_signal_reason_displayed(self):
        plan = EditorialPlan(
            signal_strength="red",
            signal_reason="GPT-5 发布",
        )
        text = plan.format_for_prompt()
        assert "GPT-5 发布" in text


# =========================================================================
# EditorialPlanningCrew 测试
# =========================================================================


class TestEditorialPlanningCrew:
    """测试 EditorialPlanningCrew 的核心行为。"""

    def test_build_scoring_summary_basic(self):
        """_build_scoring_summary 基本功能。"""
        from ai_trending.crew.editorial_planning.crew import EditorialPlanningCrew

        scoring_result = json.dumps(
            {
                "scored_repos": [
                    {
                        "name": "test/repo",
                        "stars": 5000,
                        "stars_growth_7d": 1000,
                        "scores": {"综合": 8.5},
                        "story_hook": "这个项目很厉害",
                    }
                ],
                "scored_news": [
                    {
                        "title": "AI 重大突破",
                        "impact_score": 9.0,
                        "source": "Hacker News",
                        "so_what_analysis": "改变了行业格局",
                    }
                ],
                "daily_summary": {
                    "top_trend": "Agent 框架爆发",
                    "hot_directions": ["MCP", "RAG"],
                },
            }
        )
        summary = EditorialPlanningCrew()._build_scoring_summary(scoring_result)
        assert "test/repo" in summary
        assert "5000" in summary
        assert "AI 重大突破" in summary
        assert "Agent 框架爆发" in summary

    def test_build_scoring_summary_empty_json(self):
        """空 JSON 时返回提示文本。"""
        from ai_trending.crew.editorial_planning.crew import EditorialPlanningCrew

        summary = EditorialPlanningCrew()._build_scoring_summary("")
        assert "不可用" in summary or "为空" in summary

    def test_build_scoring_summary_invalid_json(self):
        """无效 JSON 时返回提示文本。"""
        from ai_trending.crew.editorial_planning.crew import EditorialPlanningCrew

        summary = EditorialPlanningCrew()._build_scoring_summary("not json")
        assert "不可用" in summary

    def test_fallback_plan_basic(self):
        """兜底 Plan 从评分数据中提取头条。"""
        from ai_trending.crew.editorial_planning.crew import EditorialPlanningCrew

        scoring_result = json.dumps(
            {
                "scored_repos": [{"name": "top/repo"}],
            }
        )
        plan = EditorialPlanningCrew._fallback_plan(scoring_result)
        assert isinstance(plan, EditorialPlan)
        assert plan.signal_strength == "yellow"
        assert plan.headline.chosen_item == "top/repo"

    def test_fallback_plan_empty_json(self):
        """空 JSON 时兜底 Plan 为默认值。"""
        from ai_trending.crew.editorial_planning.crew import EditorialPlanningCrew

        plan = EditorialPlanningCrew._fallback_plan("")
        assert isinstance(plan, EditorialPlan)
        assert plan.headline.chosen_item == ""

    @patch("ai_trending.llm_client.build_crewai_llm")
    def test_run_success(self, mock_llm):
        """正常运行时返回 EditorialPlan 和 token 用量。"""
        from ai_trending.crew.editorial_planning.crew import EditorialPlanningCrew

        # Mock Crew.kickoff 返回值
        fake_plan = EditorialPlan(
            signal_strength="red",
            headline=HeadlineDecision(chosen_item="test/repo"),
            today_hook="AI 时代到来",
        )
        mock_result = MagicMock()
        mock_result.pydantic = fake_plan
        mock_result.token_usage = MagicMock(
            prompt_tokens=100,
            completion_tokens=50,
            total_tokens=150,
            successful_requests=1,
        )
        mock_result.tasks_output = []

        crew_obj = EditorialPlanningCrew()
        # 直接 mock 实例的 crew 方法，避免 @CrewBase 描述符问题
        mock_crew_instance = MagicMock()
        mock_crew_instance.kickoff.return_value = mock_result
        crew_obj.crew = MagicMock(return_value=mock_crew_instance)

        plan, usage = crew_obj.run(
            scoring_result='{"scored_repos": []}', current_date="2026-04-01"
        )

        assert isinstance(plan, EditorialPlan)
        assert plan.signal_strength == "red"
        assert usage.get("total_tokens") == 150

    @patch("ai_trending.llm_client.build_crewai_llm")
    def test_run_crew_failure_returns_fallback(self, mock_llm):
        """Crew 调用失败时返回兜底 Plan。"""
        from ai_trending.crew.editorial_planning.crew import EditorialPlanningCrew

        scoring = json.dumps({"scored_repos": [{"name": "fallback/repo"}]})
        crew_obj = EditorialPlanningCrew()
        # 直接 mock 实例的 crew 方法，使其 kickoff 抛异常
        mock_crew_instance = MagicMock()
        mock_crew_instance.kickoff.side_effect = Exception("LLM 超时")
        crew_obj.crew = MagicMock(return_value=mock_crew_instance)

        plan, usage = crew_obj.run(scoring_result=scoring, current_date="2026-04-01")

        # 应返回兜底 Plan，不崩溃
        assert isinstance(plan, EditorialPlan)
        assert plan.signal_strength == "yellow"  # 兜底默认
        assert plan.headline.chosen_item == "fallback/repo"
        assert usage == {}


# =========================================================================
# editorial_planning_node 测试
# =========================================================================


class TestEditorialPlanningNode:
    """测试 editorial_planning_node 的 State 更新行为。"""

    @patch("ai_trending.crew.editorial_planning.EditorialPlanningCrew")
    def test_returns_editorial_plan_key(self, MockCrew):
        """节点应返回包含 editorial_plan 键的字典。"""
        from ai_trending.nodes import editorial_planning_node

        mock_plan = EditorialPlan(signal_strength="yellow", today_hook="测试")
        mock_instance = MagicMock()
        mock_instance.run.return_value = (mock_plan, {"total_tokens": 100})
        MockCrew.return_value = mock_instance

        state = {"current_date": "2026-04-01", "scoring_result": "{}"}
        result = editorial_planning_node(state)

        assert "editorial_plan" in result
        assert isinstance(result["editorial_plan"], str)
        assert len(result["editorial_plan"]) > 0

    @patch("ai_trending.crew.editorial_planning.EditorialPlanningCrew")
    def test_crew_failure_records_error(self, MockCrew):
        """Crew 失败时记录错误到 errors 字段。"""
        from ai_trending.nodes import editorial_planning_node

        MockCrew.return_value.run.side_effect = Exception("Crew 调用失败")

        state = {"current_date": "2026-04-01", "scoring_result": "{}"}
        result = editorial_planning_node(state)

        assert "editorial_plan" in result
        assert result["editorial_plan"] == ""
        assert "errors" in result
        assert any("editorial_planning" in e for e in result["errors"])

    @patch("ai_trending.crew.editorial_planning.EditorialPlanningCrew")
    def test_editorial_plan_contains_signal(self, MockCrew):
        """输出文本应包含信号强度信息。"""
        from ai_trending.nodes import editorial_planning_node

        mock_plan = EditorialPlan(
            signal_strength="red",
            signal_reason="重大事件",
            headline=HeadlineDecision(chosen_item="test/repo"),
        )
        mock_instance = MagicMock()
        mock_instance.run.return_value = (mock_plan, {})
        MockCrew.return_value = mock_instance

        state = {"current_date": "2026-04-01", "scoring_result": "{}"}
        result = editorial_planning_node(state)

        assert "🔴" in result["editorial_plan"]
        assert "test/repo" in result["editorial_plan"]


# =========================================================================
# write_report_node 与 editorial_plan 集成测试
# =========================================================================


class TestWriteReportWithEditorialPlan:
    """测试 write_report_node 将 editorial_plan 独立传递给 ReportWritingCrew。"""

    @patch("ai_trending.crew.report_writing.ReportWritingCrew")
    @patch("ai_trending.crew.report_writing.tracker.PreviousReportTracker")
    def test_editorial_plan_passed_as_separate_param(self, MockTracker, MockCrew):
        """editorial_plan 应作为独立参数传递给 Crew.run()，不合并到 writing_brief。"""
        from ai_trending.nodes import write_report_node

        mock_tracker_instance = MagicMock()
        mock_tracker_instance.get_previous_report_context.return_value = ""
        MockTracker.return_value = mock_tracker_instance

        mock_output = MagicMock()
        mock_output.content = "# AI 日报 · 2026-04-01\n\n测试内容"
        mock_output.validation_issues = []
        mock_crew_instance = MagicMock()
        mock_crew_instance.run.return_value = (mock_output, {"total_tokens": 200})
        MockCrew.return_value = mock_crew_instance

        editorial_plan_text = "## 编辑决策\n**信号强度**: 🔴 重大变化日"
        state = {
            "current_date": "2026-04-01",
            "github_data": "GitHub 数据",
            "news_data": "新闻数据",
            "scoring_result": '{"scored_repos": [], "scored_news": []}',
            "editorial_plan": editorial_plan_text,
        }
        write_report_node(state)

        # 验证 editorial_plan 作为独立参数传递
        call_kwargs = mock_crew_instance.run.call_args
        assert call_kwargs.kwargs.get("editorial_plan") == editorial_plan_text
        # 验证 writing_brief 不包含 editorial_plan 内容（独立传递）
        writing_brief_arg = call_kwargs.kwargs.get("writing_brief", "")
        assert "编辑决策" not in writing_brief_arg

    @patch("ai_trending.crew.report_writing.ReportWritingCrew")
    @patch("ai_trending.crew.report_writing.tracker.PreviousReportTracker")
    def test_empty_editorial_plan_still_works(self, MockTracker, MockCrew):
        """editorial_plan 为空时不影响报告生成。"""
        from ai_trending.nodes import write_report_node

        mock_tracker_instance = MagicMock()
        mock_tracker_instance.get_previous_report_context.return_value = ""
        MockTracker.return_value = mock_tracker_instance

        mock_output = MagicMock()
        mock_output.content = "# AI 日报 · 2026-04-01\n\n测试内容"
        mock_output.validation_issues = []
        mock_crew_instance = MagicMock()
        mock_crew_instance.run.return_value = (mock_output, {"total_tokens": 200})
        MockCrew.return_value = mock_crew_instance

        state = {
            "current_date": "2026-04-01",
            "github_data": "GitHub 数据",
            "news_data": "新闻数据",
            "scoring_result": '{"scored_repos": [], "scored_news": []}',
            "editorial_plan": "",  # 空 plan
        }
        result = write_report_node(state)

        assert "report_content" in result
        assert len(result["report_content"]) > 0
        # 验证空 editorial_plan 被传递
        call_kwargs = mock_crew_instance.run.call_args
        assert call_kwargs.kwargs.get("editorial_plan") == ""

    @patch("ai_trending.crew.report_writing.ReportWritingCrew")
    @patch("ai_trending.crew.report_writing.tracker.PreviousReportTracker")
    def test_missing_editorial_plan_defaults_to_empty(self, MockTracker, MockCrew):
        """state 中无 editorial_plan 字段时，默认传递空字符串。"""
        from ai_trending.nodes import write_report_node

        mock_tracker_instance = MagicMock()
        mock_tracker_instance.get_previous_report_context.return_value = ""
        MockTracker.return_value = mock_tracker_instance

        mock_output = MagicMock()
        mock_output.content = "# AI 日报 · 2026-04-01\n\n测试内容"
        mock_output.validation_issues = []
        mock_crew_instance = MagicMock()
        mock_crew_instance.run.return_value = (mock_output, {"total_tokens": 200})
        MockCrew.return_value = mock_crew_instance

        state = {
            "current_date": "2026-04-01",
            "github_data": "GitHub 数据",
            "news_data": "新闻数据",
            "scoring_result": '{"scored_repos": [], "scored_news": []}',
            # 无 editorial_plan 字段
        }
        result = write_report_node(state)

        assert "report_content" in result
        call_kwargs = mock_crew_instance.run.call_args
        assert call_kwargs.kwargs.get("editorial_plan") == ""
