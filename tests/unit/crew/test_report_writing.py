"""tests/unit/crew/test_report_writing.py — ReportWritingCrew 单元测试。"""

import pytest
from unittest.mock import MagicMock, patch

from ai_trending.crew.report_writing import ReportWritingCrew
from ai_trending.crew.report_writing.models import ReportOutput
from ai_trending.crew.report_writing.crew import _validate_report


# ── fixtures ──────────────────────────────────────────────────────────────────

VALID_REPORT = """# 🤖 AI 日报 · 2025-01-01

**[今日一句话]** LLM 推理成本持续下降，开源追赶闭源趋势明显。

🟡 常规更新日

---

## 今日头条

一个月前还没人听过这个名字，现在它是最热门的推理框架。
实测吞吐量高出 40%，值得关注如果你在做本地推理。

---

## GitHub 热点项目

### 1. [owner/test-repo](https://github.com/owner/test-repo) ⭐ 5000（+500）

**一个用于构建 AI Agent 的轻量框架**

- 🏷️ **类别**：Agent框架
- 💻 **语言**：Python
- 📈 **趋势信号**：近期 Star 增速明显，社区活跃
- 🔗 https://github.com/owner/test-repo

---

## AI 热点新闻

**[产品发布]** OpenAI 发布 GPT-5
> 值得注意的是推理成本下降了 50%，这意味着更多企业可以负担得起
来源：OpenAI Blog | 🟢 一手信源 | 时间窗口：短期（1-3个月）

---

## 趋势洞察

- **推理成本竞争**：数据显示过去一个月推理框架增速明显高于其他类别，对比去年同期增长显著。

---

## 本周行动建议

**[本周作业]** 尝试使用新的推理框架替换现有方案，对比性能差异。

**[参与方式]** 欢迎在评论区分享你的测试结果。

*数据时间：2025-01-01 | 由 AI Agent 自动生成*
"""


@pytest.fixture
def mock_llm():
    """Mock build_crewai_llm，避免真实 LLM 调用。"""
    with patch("ai_trending.llm_client.build_crewai_llm") as mock:
        mock.return_value = MagicMock()
        yield mock


@pytest.fixture
def mock_crew_kickoff_with_report():
    """Mock Crew.kickoff，返回预设的 ReportOutput。"""
    with patch("crewai.Crew.kickoff") as mock:
        fake_output = ReportOutput(content=VALID_REPORT, validation_issues=[])
        mock_result = MagicMock()
        mock_result.pydantic = fake_output
        mock_result.tasks_output = []
        mock_result.raw = VALID_REPORT
        mock.return_value = mock_result
        yield mock


# ── _validate_report 测试 ──────────────────────────────────────────────────────

class TestValidateReport:
    """测试 _validate_report 校验函数。"""

    def test_valid_report_passes(self):
        """符合规范的日报应通过校验（问题列表为空或仅有少量非关键问题）。"""
        issues = _validate_report(VALID_REPORT)
        # 允许有少量非关键问题（如叙事风格检查），但不应有结构性问题
        structural_issues = [i for i in issues if "缺少必要 Section" in i]
        assert structural_issues == [], f"结构性问题: {structural_issues}"

    def test_missing_github_section(self):
        """缺少 GitHub 热点项目 Section 时应报错。"""
        content = VALID_REPORT.replace("## GitHub 热点项目", "## 其他内容")
        issues = _validate_report(content)
        assert any("GitHub 热点项目" in i for i in issues)

    def test_missing_news_section(self):
        """缺少 AI 热点新闻 Section 时应报错。"""
        content = VALID_REPORT.replace("## AI 热点新闻", "## 其他内容")
        issues = _validate_report(content)
        assert any("AI 热点新闻" in i for i in issues)

    def test_missing_trend_section(self):
        """缺少趋势洞察 Section 时应报错。"""
        content = VALID_REPORT.replace("## 趋势洞察", "## 其他内容")
        issues = _validate_report(content)
        assert any("趋势洞察" in i for i in issues)

    def test_banned_word_detected(self):
        """包含禁用词时应报错。"""
        content = VALID_REPORT + "\n这是一个重磅发布。"
        issues = _validate_report(content)
        assert any("重磅" in i for i in issues)

    def test_content_too_short(self):
        """内容过短时应报错。"""
        issues = _validate_report("# 短内容")
        assert any("过短" in i for i in issues)

    def test_returns_list(self):
        """_validate_report 始终返回列表。"""
        result = _validate_report("")
        assert isinstance(result, list)


# ── ReportOutput 模型测试 ──────────────────────────────────────────────────────

class TestReportOutputModel:
    """测试 ReportOutput Pydantic 模型。"""

    def test_default_values(self):
        """空构造不报错，默认值合理。"""
        output = ReportOutput()
        assert output.content == ""
        assert output.validation_issues == []

    def test_with_content(self):
        """正常构造包含内容的 ReportOutput。"""
        output = ReportOutput(content="# 测试日报", validation_issues=["问题1"])
        assert output.content == "# 测试日报"
        assert len(output.validation_issues) == 1


# ── ReportWritingCrew 行为测试 ─────────────────────────────────────────────────

class TestReportWritingCrew:
    """测试 ReportWritingCrew 的核心行为。"""

    def test_run_returns_report_output(self, mock_llm, mock_crew_kickoff_with_report):
        """正常输入时，run() 应返回 ReportOutput 实例。"""
        crew = ReportWritingCrew()
        result = crew.run(
            github_data="## GitHub 热点\n1. owner/test-repo",
            news_data="1. OpenAI 发布 GPT-5",
            scoring_result='{"scored_repos": [], "scored_news": [], "daily_summary": {}}',
            current_date="2025-01-01",
        )

        assert isinstance(result, ReportOutput)
        assert len(result.content) > 0

    def test_run_with_empty_data(self, mock_llm, mock_crew_kickoff_with_report):
        """空数据输入时，run() 不应崩溃。"""
        crew = ReportWritingCrew()
        result = crew.run(
            github_data="",
            news_data="",
            scoring_result="",
            current_date="2025-01-01",
        )
        assert isinstance(result, ReportOutput)

    def test_run_raises_on_crew_failure(self, mock_llm):
        """Crew.kickoff 抛出异常时，run() 应向上传播异常。"""
        with patch("crewai.Crew.kickoff") as mock:
            mock.side_effect = Exception("LLM API 超时")

            crew = ReportWritingCrew()
            with pytest.raises(Exception, match="LLM API 超时"):
                crew.run(
                    github_data="test",
                    news_data="test",
                    scoring_result="{}",
                    current_date="2025-01-01",
                )

    def test_run_fallback_from_raw_text(self, mock_llm):
        """pydantic 输出为 None 时，应从 raw 文本构造 ReportOutput。"""
        with patch("crewai.Crew.kickoff") as mock:
            mock_result = MagicMock()
            mock_result.pydantic = None
            mock_result.tasks_output = []
            mock_result.raw = "# 测试日报\n内容..."
            mock.return_value = mock_result

            crew = ReportWritingCrew()
            result = crew.run(
                github_data="test",
                news_data="test",
                scoring_result="{}",
                current_date="2025-01-01",
            )

        assert isinstance(result, ReportOutput)
        assert "测试日报" in result.content

    def test_run_records_validation_issues(self, mock_llm):
        """格式校验失败时，validation_issues 应记录问题，但不阻断返回。"""
        bad_content = "# 短内容"  # 缺少必要 Section，内容过短
        with patch("crewai.Crew.kickoff") as mock:
            mock_result = MagicMock()
            mock_result.pydantic = ReportOutput(content=bad_content)
            mock_result.tasks_output = []
            mock_result.raw = bad_content
            mock.return_value = mock_result

            crew = ReportWritingCrew()
            result = crew.run(
                github_data="test",
                news_data="test",
                scoring_result="{}",
                current_date="2025-01-01",
            )

        assert isinstance(result, ReportOutput)
        assert len(result.validation_issues) > 0  # 应记录校验问题
        assert result.content == bad_content  # 内容不被修改
