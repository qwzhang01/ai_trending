"""tests/unit/crew/test_topic_tracker.py — TopicTracker 话题追踪器单元测试。

覆盖场景：
  - TopicRecord 模型和表格行序列化/反序列化
  - TopicTracker 读写 TOPIC_TRACKER.md
  - get_recent_topics / get_kill_list / get_topic_context
  - record_today 和自动清理旧记录
  - extract_* 从日报内容中提取信息
  - editorial_planning_node 注入话题上下文
  - write_report_node 记录今日话题
"""

import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from unittest.mock import MagicMock, patch

from ai_trending.crew.report_writing.topic_tracker import (
    TopicRecord,
    TopicTracker,
)


# =========================================================================
# TopicRecord 测试
# =========================================================================


class TestTopicRecord:
    """测试 TopicRecord 数据模型。"""

    def test_to_table_row(self):
        """序列化为 Markdown 表格行。"""
        record = TopicRecord(
            date="2026-03-31",
            headline="MCP 工具链整合",
            keywords=["MCP", "Agent", "工具链"],
            hook="MCP生态正从概念验证走向工具链整合",
        )
        row = record.to_table_row()
        assert "2026-03-31" in row
        assert "MCP 工具链整合" in row
        assert "MCP, Agent, 工具链" in row

    def test_from_table_row(self):
        """从 Markdown 表格行反序列化。"""
        row = "| 2026-03-31 | MCP 工具链整合 | MCP, Agent, 工具链 | MCP生态正从概念验证走向工具链整合 |"
        record = TopicRecord.from_table_row(row)
        assert record is not None
        assert record.date == "2026-03-31"
        assert record.headline == "MCP 工具链整合"
        assert "MCP" in record.keywords
        assert "Agent" in record.keywords

    def test_from_table_row_header(self):
        """表头行应返回 None。"""
        assert TopicRecord.from_table_row("| 日期 | 头条话题 | 覆盖关键词 | 今日一句话 |") is None

    def test_from_table_row_separator(self):
        """分隔行应返回 None。"""
        assert TopicRecord.from_table_row("|------|---------|-----------|-----------|") is None

    def test_from_table_row_insufficient_columns(self):
        """列数不足时返回 None。"""
        assert TopicRecord.from_table_row("| 2026-03-31 | 标题 |") is None

    def test_empty_keywords(self):
        """空关键词时正常序列化。"""
        record = TopicRecord(date="2026-03-31", headline="test", keywords=[], hook="hook")
        row = record.to_table_row()
        assert "2026-03-31" in row


# =========================================================================
# TopicTracker 读写测试
# =========================================================================


class TestTopicTrackerReadWrite:
    """测试 TopicTracker 的文件读写功能。"""

    def test_load_empty_file(self, tmp_path):
        """文件不存在时返回空列表。"""
        tracker = TopicTracker(tracker_path=tmp_path / "TOPIC_TRACKER.md")
        records = tracker.get_recent_topics()
        assert records == []

    def test_record_and_load(self, tmp_path):
        """记录后能正确加载。"""
        tracker_path = tmp_path / "TOPIC_TRACKER.md"
        tracker = TopicTracker(tracker_path=tracker_path)

        today = datetime.now().strftime("%Y-%m-%d")
        tracker.record_today(
            date=today,
            headline="Test Headline",
            keywords=["AI", "LLM"],
            hook="Test hook",
        )

        records = tracker.get_recent_topics()
        assert len(records) == 1
        assert records[0].date == today
        assert records[0].headline == "Test Headline"

    def test_record_updates_existing(self, tmp_path):
        """同日记录应更新而非重复。"""
        tracker_path = tmp_path / "TOPIC_TRACKER.md"
        tracker = TopicTracker(tracker_path=tracker_path)

        today = datetime.now().strftime("%Y-%m-%d")
        tracker.record_today(date=today, headline="V1", keywords=["AI"], hook="hook1")
        tracker.record_today(date=today, headline="V2", keywords=["LLM"], hook="hook2")

        records = tracker.get_recent_topics()
        assert len(records) == 1
        assert records[0].headline == "V2"

    def test_records_sorted_by_date_desc(self, tmp_path):
        """记录按日期倒序排列。"""
        tracker_path = tmp_path / "TOPIC_TRACKER.md"
        tracker = TopicTracker(tracker_path=tracker_path)

        today = datetime.now()
        for i in range(3):
            d = (today - timedelta(days=i)).strftime("%Y-%m-%d")
            tracker.record_today(date=d, headline=f"Day{i}", keywords=[], hook="")

        records = tracker.get_recent_topics()
        assert len(records) == 3
        assert records[0].date > records[1].date > records[2].date

    def test_old_records_cleaned(self, tmp_path):
        """超过 7 天的记录被清理。"""
        tracker_path = tmp_path / "TOPIC_TRACKER.md"
        tracker = TopicTracker(tracker_path=tracker_path)

        today = datetime.now()
        # 添加 10 天前的记录
        old_date = (today - timedelta(days=10)).strftime("%Y-%m-%d")
        tracker.record_today(date=old_date, headline="Old", keywords=[], hook="")

        # 添加今天的记录，应触发清理
        today_str = today.strftime("%Y-%m-%d")
        tracker.record_today(date=today_str, headline="New", keywords=[], hook="")

        records = tracker.get_recent_topics()
        assert all(r.headline != "Old" for r in records)
        assert any(r.headline == "New" for r in records)


# =========================================================================
# Kill List 测试
# =========================================================================


class TestKillList:
    """测试 Kill List 生成逻辑。"""

    def test_empty_when_no_records(self, tmp_path):
        """无记录时返回空 Kill List。"""
        tracker = TopicTracker(tracker_path=tmp_path / "TOPIC_TRACKER.md")
        assert tracker.get_kill_list() == []

    def test_repeated_keywords_in_kill_list(self, tmp_path):
        """关键词出现 >= 2 次时进入 Kill List。"""
        tracker_path = tmp_path / "TOPIC_TRACKER.md"
        tracker = TopicTracker(tracker_path=tracker_path)

        today = datetime.now()
        for i in range(2):
            d = (today - timedelta(days=i)).strftime("%Y-%m-%d")
            tracker.record_today(date=d, headline=f"Day{i}", keywords=["MCP", "Agent"], hook="")

        kill_list = tracker.get_kill_list()
        assert len(kill_list) > 0
        # MCP 应在 Kill List 中
        assert any("mcp" in item.lower() for item in kill_list)

    def test_recent_headline_in_kill_list(self, tmp_path):
        """近 2 天的头条话题进入 Kill List。"""
        tracker_path = tmp_path / "TOPIC_TRACKER.md"
        tracker = TopicTracker(tracker_path=tracker_path)

        today = datetime.now().strftime("%Y-%m-%d")
        tracker.record_today(date=today, headline="UniqueHeadline", keywords=[], hook="")

        kill_list = tracker.get_kill_list()
        assert any("UniqueHeadline" in item for item in kill_list)


# =========================================================================
# get_topic_context 测试
# =========================================================================


class TestGetTopicContext:
    """测试 get_topic_context 格式化输出。"""

    def test_no_records(self, tmp_path):
        """无记录时返回提示文本。"""
        tracker = TopicTracker(tracker_path=tmp_path / "TOPIC_TRACKER.md")
        context = tracker.get_topic_context()
        assert "无近期" in context

    def test_with_records(self, tmp_path):
        """有记录时包含表格和 Kill List。"""
        tracker_path = tmp_path / "TOPIC_TRACKER.md"
        tracker = TopicTracker(tracker_path=tracker_path)

        today = datetime.now()
        for i in range(2):
            d = (today - timedelta(days=i)).strftime("%Y-%m-%d")
            tracker.record_today(
                date=d,
                headline=f"Topic{i}",
                keywords=["AI", "LLM"],
                hook=f"Hook{i}",
            )

        context = tracker.get_topic_context()
        assert "近期话题追踪" in context
        assert "Topic0" in context
        assert "Topic1" in context


# =========================================================================
# 提取方法测试
# =========================================================================


class TestExtractMethods:
    """测试从日报内容中提取信息的静态方法。"""

    def test_extract_headline_from_report(self):
        """提取头条话题。"""
        report = """# AI 日报 · 2026-04-01

## 今日头条

### [awesome-project](https://github.com/owner/awesome-project) ⭐ 5000（+1000）

这是一段描述。

## GitHub 热点项目
"""
        headline = TopicTracker.extract_headline_from_report(report)
        assert "awesome-project" in headline

    def test_extract_headline_no_match(self):
        """无头条时返回空字符串。"""
        report = "# AI 日报\n\n## 趋势洞察"
        assert TopicTracker.extract_headline_from_report(report) == ""

    def test_extract_keywords_from_report(self):
        """提取关键词。"""
        report = """# AI 日报

### [langchain](https://github.com/langchain-ai/langchain) ⭐ 5000

这个项目使用 LLM 和 RAG 技术，支持 Agent 开发。
"""
        keywords = TopicTracker.extract_keywords_from_report(report)
        assert "langchain" in keywords
        assert any(kw.upper() == "AI" for kw in keywords)
        assert any(kw.upper() == "LLM" for kw in keywords)

    def test_extract_hook_from_report(self):
        """提取今日一句话。"""
        report = """# AI 日报

**[今日一句话]** AI编程工具从辅助走向主导

## 今日头条
"""
        hook = TopicTracker.extract_hook_from_report(report)
        assert "AI编程工具" in hook

    def test_extract_hook_no_match(self):
        """无今日一句话时返回空字符串。"""
        report = "# AI 日报\n\n## 趋势洞察"
        assert TopicTracker.extract_hook_from_report(report) == ""


# =========================================================================
# editorial_planning_node 话题上下文注入测试
# =========================================================================


class TestEditorialPlanningNodeWithTopicContext:
    """测试 editorial_planning_node 注入话题上下文。"""

    @patch("ai_trending.crew.report_writing.topic_tracker.TopicTracker")
    @patch("ai_trending.crew.editorial_planning.EditorialPlanningCrew")
    def test_topic_context_passed_to_crew(self, MockCrew, MockTracker):
        """话题上下文应传递给 EditorialPlanningCrew.run()。"""
        from ai_trending.nodes import editorial_planning_node
        from ai_trending.crew.editorial_planning.models import (
            EditorialPlan,
            HeadlineDecision,
        )

        mock_tracker_instance = MagicMock()
        mock_tracker_instance.get_topic_context.return_value = "## 近期话题追踪\n测试数据"
        MockTracker.return_value = mock_tracker_instance

        mock_plan = EditorialPlan(signal_strength="yellow", today_hook="测试")
        mock_crew_instance = MagicMock()
        mock_crew_instance.run.return_value = (mock_plan, {"total_tokens": 100})
        MockCrew.return_value = mock_crew_instance

        state = {"current_date": "2026-04-01", "scoring_result": "{}"}
        result = editorial_planning_node(state)

        # 验证 topic_context 被传递给 Crew
        call_kwargs = mock_crew_instance.run.call_args
        assert "topic_context" in call_kwargs.kwargs
        assert "近期话题追踪" in call_kwargs.kwargs["topic_context"]

    @patch("ai_trending.crew.report_writing.topic_tracker.TopicTracker")
    @patch("ai_trending.crew.editorial_planning.EditorialPlanningCrew")
    def test_topic_tracker_failure_does_not_block(self, MockCrew, MockTracker):
        """TopicTracker 失败时不阻断编辑规划。"""
        from ai_trending.nodes import editorial_planning_node
        from ai_trending.crew.editorial_planning.models import EditorialPlan

        MockTracker.return_value.get_topic_context.side_effect = Exception("读取失败")

        mock_plan = EditorialPlan(signal_strength="yellow")
        mock_crew_instance = MagicMock()
        mock_crew_instance.run.return_value = (mock_plan, {})
        MockCrew.return_value = mock_crew_instance

        state = {"current_date": "2026-04-01", "scoring_result": "{}"}
        result = editorial_planning_node(state)

        # 节点不应崩溃
        assert "editorial_plan" in result
        # topic_context 应为空字符串（兜底）
        call_kwargs = mock_crew_instance.run.call_args
        assert call_kwargs.kwargs.get("topic_context") == ""


# =========================================================================
# write_report_node 话题记录测试
# =========================================================================


class TestWriteReportNodeTopicRecording:
    """测试 write_report_node 在报告生成后记录话题。"""

    @patch("ai_trending.crew.report_writing.topic_tracker.TopicTracker")
    @patch("ai_trending.crew.report_writing.ReportWritingCrew")
    @patch("ai_trending.crew.report_writing.tracker.PreviousReportTracker")
    def test_topic_recorded_after_report(self, MockPrevTracker, MockCrew, MockTopicTracker):
        """报告生成后应调用 TopicTracker.record_today。"""
        from ai_trending.nodes import write_report_node

        mock_prev = MagicMock()
        mock_prev.get_previous_report_context.return_value = ""
        MockPrevTracker.return_value = mock_prev

        mock_output = MagicMock()
        mock_output.content = "# AI 日报 · 2026-04-01\n\n## 今日头条\n\n### [test](https://github.com/test) ⭐ 100\n\n测试"
        mock_output.validation_issues = []
        mock_crew_instance = MagicMock()
        mock_crew_instance.run.return_value = (mock_output, {"total_tokens": 200})
        MockCrew.return_value = mock_crew_instance

        mock_topic_tracker = MagicMock()
        mock_topic_tracker.extract_headline_from_report.return_value = "test"
        mock_topic_tracker.extract_keywords_from_report.return_value = ["AI"]
        mock_topic_tracker.extract_hook_from_report.return_value = "hook"
        MockTopicTracker.return_value = mock_topic_tracker

        state = {
            "current_date": "2026-04-01",
            "github_data": "data",
            "news_data": "data",
            "scoring_result": '{"scored_repos": [], "scored_news": []}',
            "editorial_plan": "",
        }
        result = write_report_node(state)

        assert "report_content" in result
        mock_topic_tracker.record_today.assert_called_once()

    @patch("ai_trending.crew.report_writing.topic_tracker.TopicTracker")
    @patch("ai_trending.crew.report_writing.ReportWritingCrew")
    @patch("ai_trending.crew.report_writing.tracker.PreviousReportTracker")
    def test_topic_tracker_failure_does_not_block_report(self, MockPrevTracker, MockCrew, MockTopicTracker):
        """TopicTracker 记录失败不影响报告发布。"""
        from ai_trending.nodes import write_report_node

        mock_prev = MagicMock()
        mock_prev.get_previous_report_context.return_value = ""
        MockPrevTracker.return_value = mock_prev

        mock_output = MagicMock()
        mock_output.content = "# AI 日报 · 2026-04-01"
        mock_output.validation_issues = []
        mock_crew_instance = MagicMock()
        mock_crew_instance.run.return_value = (mock_output, {"total_tokens": 200})
        MockCrew.return_value = mock_crew_instance

        MockTopicTracker.return_value.record_today.side_effect = Exception("写入失败")
        MockTopicTracker.return_value.extract_headline_from_report.return_value = ""
        MockTopicTracker.return_value.extract_keywords_from_report.return_value = []
        MockTopicTracker.return_value.extract_hook_from_report.return_value = ""

        state = {
            "current_date": "2026-04-01",
            "github_data": "data",
            "news_data": "data",
            "scoring_result": '{"scored_repos": [], "scored_news": []}',
            "editorial_plan": "",
        }
        result = write_report_node(state)

        # 报告仍然成功
        assert "report_content" in result
        assert result["report_content"] == "# AI 日报 · 2026-04-01"
