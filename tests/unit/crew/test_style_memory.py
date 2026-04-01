"""tests/unit/crew/test_style_memory.py — StyleMemory 风格记忆管理器单元测试。

覆盖场景：
  - QualityRecord 模型和表格行序列化/反序列化
  - StyleMemory 读写 STYLE_MEMORY.md
  - get_style_guidance 格式化输出
  - record_quality_result 质量记录
  - detect_repeated_patterns 重复模式检测
  - extract_patterns_from_report 好/坏表达提取
  - _extract_main_issues 问题分类
  - write_report_node 风格记忆注入和记录
"""

from datetime import datetime, timedelta
from pathlib import Path

import pytest
from unittest.mock import MagicMock, patch

from ai_trending.crew.report_writing.style_memory import (
    QualityRecord,
    StyleMemory,
)


# =========================================================================
# QualityRecord 测试
# =========================================================================


class TestQualityRecord:
    """测试 QualityRecord 数据模型。"""

    def test_to_table_row(self):
        """序列化为 Markdown 表格行。"""
        record = QualityRecord(
            date="2026-03-31",
            passed_count=15,
            total_count=18,
            main_issues=["信号强度", "字数问题"],
        )
        row = record.to_table_row()
        assert "2026-03-31" in row
        assert "15/18" in row
        assert "信号强度" in row
        assert "字数问题" in row

    def test_to_table_row_no_issues(self):
        """无问题时显示"无"。"""
        record = QualityRecord(
            date="2026-03-31", passed_count=18, total_count=18, main_issues=[]
        )
        row = record.to_table_row()
        assert "18/18" in row
        assert "无" in row

    def test_from_table_row(self):
        """从 Markdown 表格行反序列化。"""
        row = "| 2026-03-31 | 15/18 | 信号强度; 字数问题 |"
        record = QualityRecord.from_table_row(row)
        assert record is not None
        assert record.date == "2026-03-31"
        assert record.passed_count == 15
        assert record.total_count == 18
        assert "信号强度" in record.main_issues
        assert "字数问题" in record.main_issues

    def test_from_table_row_no_issues(self):
        """主要问题为"无"时解析为空列表。"""
        row = "| 2026-03-31 | 18/18 | 无 |"
        record = QualityRecord.from_table_row(row)
        assert record is not None
        assert record.main_issues == []

    def test_from_table_row_header(self):
        """表头行返回 None。"""
        assert QualityRecord.from_table_row("| 日期 | 通过项 | 主要问题 |") is None

    def test_from_table_row_separator(self):
        """分隔行返回 None。"""
        assert QualityRecord.from_table_row("|------|-------|---------|") is None

    def test_from_table_row_insufficient(self):
        """列数不足返回 None。"""
        assert QualityRecord.from_table_row("| 2026-03-31 |") is None

    def test_from_table_row_invalid_score(self):
        """通过项格式无效时返回 None。"""
        assert QualityRecord.from_table_row("| 2026-03-31 | abc | 问题 |") is None


# =========================================================================
# StyleMemory 读写测试
# =========================================================================


class TestStyleMemoryReadWrite:
    """测试 StyleMemory 的文件读写功能。"""

    def test_load_empty_file(self, tmp_path):
        """文件不存在时返回空数据。"""
        mem = StyleMemory(memory_path=tmp_path / "STYLE_MEMORY.md")
        guidance = mem.get_style_guidance()
        assert "无风格记忆" in guidance

    def test_record_and_load(self, tmp_path):
        """记录后能正确加载。"""
        mem_path = tmp_path / "STYLE_MEMORY.md"
        mem = StyleMemory(memory_path=mem_path)

        today = datetime.now().strftime("%Y-%m-%d")
        mem.record_quality_result(
            date=today,
            validation_issues=["缺少必要 Section：## 今日头条"],
            good_patterns=['"发布 48 小时内" — 时间窗口制造紧迫感'],
            bad_patterns=['"核心原因是…" — 连续使用，模板感强'],
        )

        # 文件应被创建
        assert mem_path.exists()

        # 重新加载
        guidance = mem.get_style_guidance()
        assert "效果好的表达" in guidance
        assert "效果差的表达" in guidance
        assert "发布 48 小时内" in guidance

    def test_record_updates_existing(self, tmp_path):
        """同日记录应更新而非重复。"""
        mem_path = tmp_path / "STYLE_MEMORY.md"
        mem = StyleMemory(memory_path=mem_path)

        today = datetime.now().strftime("%Y-%m-%d")
        mem.record_quality_result(date=today, validation_issues=["问题1"])
        mem.record_quality_result(date=today, validation_issues=["问题2", "问题3"])

        # 重新加载
        good, bad, records = mem._load_all()
        # 同日应只有 1 条记录
        today_records = [r for r in records if r.date == today]
        assert len(today_records) == 1
        assert today_records[0].passed_count == 16  # 18 - 2

    def test_old_records_cleaned(self, tmp_path):
        """超过 14 天的记录被清理。"""
        mem_path = tmp_path / "STYLE_MEMORY.md"
        mem = StyleMemory(memory_path=mem_path)

        today = datetime.now()
        # 添加 20 天前的记录
        old_date = (today - timedelta(days=20)).strftime("%Y-%m-%d")
        mem.record_quality_result(date=old_date, validation_issues=[])

        # 添加今天的记录，应触发清理
        today_str = today.strftime("%Y-%m-%d")
        mem.record_quality_result(date=today_str, validation_issues=[])

        good, bad, records = mem._load_all()
        assert all(r.date >= (today - timedelta(days=14)).strftime("%Y-%m-%d") for r in records)

    def test_good_bad_patterns_accumulate(self, tmp_path):
        """好/坏表达应累积，不被覆盖。"""
        mem_path = tmp_path / "STYLE_MEMORY.md"
        mem = StyleMemory(memory_path=mem_path)

        today = datetime.now().strftime("%Y-%m-%d")
        mem.record_quality_result(
            date=today,
            validation_issues=[],
            good_patterns=["pattern1"],
            bad_patterns=["bad1"],
        )
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        mem.record_quality_result(
            date=yesterday,
            validation_issues=[],
            good_patterns=["pattern2"],
            bad_patterns=["bad2"],
        )

        good, bad, _ = mem._load_all()
        assert "pattern1" in good
        assert "pattern2" in good
        assert "bad1" in bad
        assert "bad2" in bad

    def test_patterns_max_limit(self, tmp_path):
        """好/坏表达列表不超过 20 条。"""
        mem_path = tmp_path / "STYLE_MEMORY.md"
        mem = StyleMemory(memory_path=mem_path)

        today = datetime.now().strftime("%Y-%m-%d")
        patterns = [f"pattern{i}" for i in range(25)]
        mem.record_quality_result(
            date=today, validation_issues=[], good_patterns=patterns
        )

        good, _, _ = mem._load_all()
        assert len(good) <= 20


# =========================================================================
# get_style_guidance 测试
# =========================================================================


class TestGetStyleGuidance:
    """测试 get_style_guidance 格式化输出。"""

    def test_no_records(self, tmp_path):
        """无记录时返回提示文本。"""
        mem = StyleMemory(memory_path=tmp_path / "STYLE_MEMORY.md")
        guidance = mem.get_style_guidance()
        assert "无风格记忆" in guidance

    def test_with_records(self, tmp_path):
        """有记录时包含好/坏表达和质量趋势。"""
        mem_path = tmp_path / "STYLE_MEMORY.md"
        mem = StyleMemory(memory_path=mem_path)

        today = datetime.now().strftime("%Y-%m-%d")
        mem.record_quality_result(
            date=today,
            validation_issues=["缺少信号强度标签"],
            good_patterns=['"实测吞吐量" — 数据说话'],
            bad_patterns=['"核心原因是" — 模板感'],
        )

        guidance = mem.get_style_guidance()
        assert "风格记忆" in guidance
        assert "实测吞吐量" in guidance
        assert "核心原因是" in guidance
        assert today in guidance

    def test_guidance_limits_items(self, tmp_path):
        """指导文本最多展示 5 条好/坏表达。"""
        mem_path = tmp_path / "STYLE_MEMORY.md"
        mem = StyleMemory(memory_path=mem_path)

        today = datetime.now().strftime("%Y-%m-%d")
        many_patterns = [f"good_pattern_{i}" for i in range(10)]
        mem.record_quality_result(
            date=today, validation_issues=[], good_patterns=many_patterns
        )

        guidance = mem.get_style_guidance()
        # 计算 guidance 中 good_pattern 出现次数
        import re
        matches = re.findall(r"good_pattern_\d+", guidance)
        assert len(matches) <= 5


# =========================================================================
# detect_repeated_patterns 测试
# =========================================================================


class TestDetectRepeatedPatterns:
    """测试重复模式检测。"""

    def test_no_patterns(self, tmp_path):
        """无坏表达时返回空列表。"""
        mem = StyleMemory(memory_path=tmp_path / "STYLE_MEMORY.md")
        result = mem.detect_repeated_patterns("一段正常的日报内容")
        assert result == []

    def test_detects_repeated(self, tmp_path):
        """能检测到内容中使用了坏表达。"""
        mem_path = tmp_path / "STYLE_MEMORY.md"
        mem = StyleMemory(memory_path=mem_path)

        today = datetime.now().strftime("%Y-%m-%d")
        mem.record_quality_result(
            date=today,
            validation_issues=[],
            bad_patterns=['"核心原因是" — 连续使用，模板感强'],
        )

        content = "这个项目的核心原因是技术创新..."
        result = mem.detect_repeated_patterns(content)
        assert len(result) > 0
        assert any("核心原因是" in item for item in result)

    def test_no_match(self, tmp_path):
        """内容中不包含坏表达时返回空。"""
        mem_path = tmp_path / "STYLE_MEMORY.md"
        mem = StyleMemory(memory_path=mem_path)

        today = datetime.now().strftime("%Y-%m-%d")
        mem.record_quality_result(
            date=today,
            validation_issues=[],
            bad_patterns=['"核心原因是" — 连续使用，模板感强'],
        )

        content = "这个项目实测性能提升 40%..."
        result = mem.detect_repeated_patterns(content)
        assert result == []


# =========================================================================
# extract_patterns_from_report 测试
# =========================================================================


class TestExtractPatternsFromReport:
    """测试从日报中提取好/坏表达模式。"""

    def test_extracts_good_time_window(self):
        """检测时间窗口表达。"""
        mem = StyleMemory()
        content = "发布 48 小时内 GitHub 星数突破 8000"
        good, bad = mem.extract_patterns_from_report(content)
        assert any("时间窗口" in p or "紧迫感" in p for p in good)

    def test_extracts_good_star_growth(self):
        """检测星数增长表达。"""
        mem = StyleMemory()
        content = "星数突破 6000，成为本周最热项目"
        good, bad = mem.extract_patterns_from_report(content)
        assert any("星数" in p for p in good)

    def test_extracts_good_benchmark(self):
        """检测实测数据表达。"""
        mem = StyleMemory()
        content = "实测吞吐量高出同类 40%"
        good, bad = mem.extract_patterns_from_report(content)
        assert any("实测" in p for p in good)

    def test_extracts_good_target_audience(self):
        """检测场景锚定表达。"""
        mem = StyleMemory()
        content = "如果你日常用 vim 开发，这个工具值得试"
        good, bad = mem.extract_patterns_from_report(content)
        assert any("场景锚定" in p or "目标读者" in p for p in good)

    def test_empty_content(self):
        """空内容返回空列表。"""
        mem = StyleMemory()
        good, bad = mem.extract_patterns_from_report("")
        assert good == []
        assert bad == []


# =========================================================================
# _extract_main_issues 测试
# =========================================================================


class TestExtractMainIssues:
    """测试问题分类。"""

    def test_categorizes_issues(self):
        """正确分类不同类型的问题。"""
        mem = StyleMemory()
        issues = [
            "缺少必要 Section：## 今日头条",
            "缺少今日信号强度标签",
            "内容过短：600 字（最少 800 字）",
        ]
        main = mem._extract_main_issues(issues)
        assert "Section" in main
        assert "信号强度" in main
        assert "字数问题" in main

    def test_max_count(self):
        """最多返回 max_count 条。"""
        mem = StyleMemory()
        issues = [
            "缺少必要 Section：## 今日头条",
            "缺少今日信号强度标签",
            "内容过短",
            "缺少 So What",
            "包含禁用词",
        ]
        main = mem._extract_main_issues(issues, max_count=2)
        assert len(main) <= 2

    def test_empty_issues(self):
        """空问题列表返回空。"""
        mem = StyleMemory()
        assert mem._extract_main_issues([]) == []


# =========================================================================
# write_report_node 风格记忆集成测试
# =========================================================================


class TestWriteReportNodeStyleMemory:
    """测试 write_report_node 中风格记忆的注入和记录。"""

    @patch("ai_trending.crew.report_writing.style_memory.StyleMemory")
    @patch("ai_trending.crew.report_writing.topic_tracker.TopicTracker")
    @patch("ai_trending.crew.report_writing.ReportWritingCrew")
    @patch("ai_trending.crew.report_writing.tracker.PreviousReportTracker")
    def test_style_guidance_passed_to_crew(
        self, MockPrevTracker, MockCrew, MockTopicTracker, MockStyleMemory
    ):
        """风格记忆指导应传递给 ReportWritingCrew.run()。"""
        from ai_trending.nodes import write_report_node

        mock_prev = MagicMock()
        mock_prev.get_previous_report_context.return_value = ""
        MockPrevTracker.return_value = mock_prev

        mock_style = MagicMock()
        mock_style.get_style_guidance.return_value = "## 风格记忆\n测试数据"
        mock_style.extract_patterns_from_report.return_value = ([], [])
        MockStyleMemory.return_value = mock_style

        mock_topic = MagicMock()
        mock_topic.extract_headline_from_report.return_value = ""
        mock_topic.extract_keywords_from_report.return_value = []
        mock_topic.extract_hook_from_report.return_value = ""
        MockTopicTracker.return_value = mock_topic

        mock_output = MagicMock()
        mock_output.content = "# AI 日报 · 2026-04-01\n\n测试内容"
        mock_output.validation_issues = []
        mock_crew_instance = MagicMock()
        mock_crew_instance.run.return_value = (mock_output, {"total_tokens": 200})
        MockCrew.return_value = mock_crew_instance

        state = {
            "current_date": "2026-04-01",
            "github_data": "data",
            "news_data": "data",
            "scoring_result": '{"scored_repos": [], "scored_news": []}',
            "editorial_plan": "",
        }
        result = write_report_node(state)

        # 验证 style_guidance 被传递给 Crew
        call_kwargs = mock_crew_instance.run.call_args
        assert "style_guidance" in call_kwargs.kwargs
        assert "风格记忆" in call_kwargs.kwargs["style_guidance"]

    @patch("ai_trending.crew.report_writing.style_memory.StyleMemory")
    @patch("ai_trending.crew.report_writing.topic_tracker.TopicTracker")
    @patch("ai_trending.crew.report_writing.ReportWritingCrew")
    @patch("ai_trending.crew.report_writing.tracker.PreviousReportTracker")
    def test_quality_result_recorded_after_report(
        self, MockPrevTracker, MockCrew, MockTopicTracker, MockStyleMemory
    ):
        """OPT-006: record_quality_result 已移到 publish_node（post-publish hook）。
        write_report_node 只调用 extract_patterns_from_report，不再调用 record_quality_result。
        验证 good_patterns_json 被写入 state，供 publish_node 使用。
        """
        from ai_trending.nodes import write_report_node

        mock_prev = MagicMock()
        mock_prev.get_previous_report_context.return_value = ""
        MockPrevTracker.return_value = mock_prev

        mock_style = MagicMock()
        mock_style.get_style_guidance.return_value = "（无风格记忆记录）"
        mock_style.extract_patterns_from_report.return_value = (
            ["good1"],
            ["bad1"],
        )
        MockStyleMemory.return_value = mock_style

        mock_topic = MagicMock()
        mock_topic.extract_headline_from_report.return_value = ""
        mock_topic.extract_keywords_from_report.return_value = []
        mock_topic.extract_hook_from_report.return_value = ""
        MockTopicTracker.return_value = mock_topic

        mock_output = MagicMock()
        mock_output.content = "# AI 日报 · 2026-04-01"
        mock_output.validation_issues = ["缺少信号强度"]
        mock_crew_instance = MagicMock()
        mock_crew_instance.run.return_value = (mock_output, {"total_tokens": 100})
        MockCrew.return_value = mock_crew_instance

        state = {
            "current_date": "2026-04-01",
            "github_data": "data",
            "news_data": "data",
            "scoring_result": '{"scored_repos": [], "scored_news": []}',
            "editorial_plan": "",
        }
        result = write_report_node(state)

        # OPT-006: write_report_node 不再调用 record_quality_result（已移到 publish_node）
        mock_style.record_quality_result.assert_not_called()
        # 验证 extract_patterns_from_report 被调用（提取动作仍在 write_report）
        mock_style.extract_patterns_from_report.assert_called_once()
        # 验证 good_patterns_json 写入 state
        assert "good_patterns_json" in result

    @patch("ai_trending.crew.report_writing.style_memory.StyleMemory")
    @patch("ai_trending.crew.report_writing.topic_tracker.TopicTracker")
    @patch("ai_trending.crew.report_writing.ReportWritingCrew")
    @patch("ai_trending.crew.report_writing.tracker.PreviousReportTracker")
    def test_style_memory_failure_does_not_block(
        self, MockPrevTracker, MockCrew, MockTopicTracker, MockStyleMemory
    ):
        """StyleMemory 失败时不阻断报告生成。"""
        from ai_trending.nodes import write_report_node

        mock_prev = MagicMock()
        mock_prev.get_previous_report_context.return_value = ""
        MockPrevTracker.return_value = mock_prev

        # StyleMemory 读取失败
        MockStyleMemory.return_value.get_style_guidance.side_effect = Exception(
            "读取失败"
        )
        MockStyleMemory.return_value.extract_patterns_from_report.return_value = ([], [])
        MockStyleMemory.return_value.record_quality_result.side_effect = Exception(
            "写入失败"
        )

        mock_topic = MagicMock()
        mock_topic.extract_headline_from_report.return_value = ""
        mock_topic.extract_keywords_from_report.return_value = []
        mock_topic.extract_hook_from_report.return_value = ""
        MockTopicTracker.return_value = mock_topic

        mock_output = MagicMock()
        mock_output.content = "# AI 日报 · 2026-04-01"
        mock_output.validation_issues = []
        mock_crew_instance = MagicMock()
        mock_crew_instance.run.return_value = (mock_output, {"total_tokens": 100})
        MockCrew.return_value = mock_crew_instance

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
        # style_guidance 应为空字符串（兜底）
        call_kwargs = mock_crew_instance.run.call_args
        assert call_kwargs.kwargs.get("style_guidance") == ""
