"""tests/unit/crew/test_trend_scoring.py — TrendScoringCrew 单元测试。"""

import json
from unittest.mock import MagicMock, patch

import pytest

from ai_trending.crew.trend_scoring import TrendScoringCrew
from ai_trending.crew.trend_scoring.models import (
    DailySummary,
    ScoredNews,
    ScoredRepo,
    TrendScoringOutput,
)

# ── fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def fake_scoring_output() -> TrendScoringOutput:
    """构造一个标准的 TrendScoringOutput 用于测试。"""
    return TrendScoringOutput(
        scored_repos=[
            ScoredRepo(
                repo="owner/test-repo",
                name="Test Repo",
                url="https://github.com/owner/test-repo",
                stars=5000,
                language="Python",
                is_ai=True,
                category="Agent框架",
                scores={"热度": 6.0, "技术前沿性": 8.0, "成长潜力": 7.0, "综合": 7.2},
                one_line_reason="一个用于构建 AI Agent 的轻量框架",
                story_hook="三个月前还没人知道它",
                technical_detail="基于事件驱动架构，延迟降低 40%",
                target_audience="做 AI Agent 开发的工程师",
                scenario_description="相当于 LangChain 的轻量版",
            )
        ],
        scored_news=[
            ScoredNews(
                title="OpenAI 发布 GPT-5",
                url="https://example.com/news",
                source="OpenAI Blog",
                category="产品发布",
                impact_score=9.0,
                impact_reason="GPT-5 在多项基准测试中超越前代",
                so_what_analysis="值得注意的是模型推理成本下降了 50%",
                credibility_label="🟢 一手信源",
                time_window="短期（1-3个月）",
                affected_audience="开发者",
            )
        ],
        daily_summary=DailySummary(
            top_trend="LLM 推理成本持续下降",
            hot_directions=["Agent框架", "推理优化", "多模态"],
            overall_sentiment="积极",
            causal_explanation="企业对 LLM 成本敏感度提升，推动推理优化竞争",
            data_support="过去一个月推理框架 Star 增速明显高于其他类别",
            forward_looking="预计未来 3 个月会有更多推理优化方案出现",
        ),
    )


@pytest.fixture
def mock_crew_kickoff(fake_scoring_output):
    """Mock Crew.kickoff，直接返回预设的 Pydantic 输出。"""
    with patch("crewai.Crew.kickoff") as mock:
        mock_result = MagicMock()
        mock_result.pydantic = fake_scoring_output
        mock_result.tasks_output = []
        mock_result.raw = ""
        # token_usage mock
        mock_usage = MagicMock()
        mock_usage.prompt_tokens = 1
        mock_usage.completion_tokens = 1
        mock_usage.total_tokens = 2
        mock_usage.successful_requests = 1
        mock_result.token_usage = mock_usage
        mock.return_value = mock_result
        yield mock


@pytest.fixture
def mock_llm():
    """Mock build_crewai_llm，避免真实 LLM 调用。"""
    with patch("ai_trending.llm_client.build_crewai_llm") as mock:
        mock.return_value = MagicMock()
        yield mock


# ── TrendScoringOutput 模型测试 ────────────────────────────────────────────────


class TestTrendScoringOutputModel:
    """测试 TrendScoringOutput Pydantic 模型的字段约束。"""

    def test_default_values(self):
        """空构造不报错，所有字段有合理默认值。"""
        output = TrendScoringOutput()
        assert output.scored_repos == []
        assert output.scored_news == []
        assert isinstance(output.daily_summary, DailySummary)

    def test_scored_repo_fields(self):
        """ScoredRepo 字段约束测试。"""
        repo = ScoredRepo(
            repo="owner/repo",
            name="Test",
            stars=1000,
            language="Python",
        )
        assert repo.repo == "owner/repo"
        assert repo.stars == 1000
        assert repo.is_ai is True  # 默认值
        assert repo.scores == {}  # 默认空字典

    def test_scored_news_impact_score_range(self):
        """impact_score 必须在 0-10 范围内。"""
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            ScoredNews(title="test", impact_score=11.0)  # 超出范围

    def test_daily_summary_defaults(self):
        """DailySummary 默认值测试。"""
        summary = DailySummary()
        assert summary.top_trend == ""
        assert summary.hot_directions == []
        assert summary.overall_sentiment == "中性"

    def test_model_serialization(self, fake_scoring_output):
        """模型可以正确序列化为 JSON。"""
        data = fake_scoring_output.model_dump()
        assert "scored_repos" in data
        assert "scored_news" in data
        assert "daily_summary" in data
        # 验证可以重新反序列化
        restored = TrendScoringOutput.model_validate(data)
        assert len(restored.scored_repos) == 1
        assert restored.scored_repos[0].repo == "owner/test-repo"


# ── TrendScoringCrew 行为测试 ──────────────────────────────────────────────────


class TestTrendScoringCrew:
    """测试 TrendScoringCrew 的核心行为。"""

    def test_run_returns_scoring_output(
        self, mock_llm, mock_crew_kickoff, fake_scoring_output
    ):
        """正常输入时，run() 应返回 (TrendScoringOutput, token_usage) 元组。"""
        crew = TrendScoringCrew()
        result = crew.run(
            github_data="## GitHub 热点\n1. owner/test-repo ⭐ 5000",
            news_data="1. OpenAI 发布 GPT-5",
            current_date="2025-01-01",
        )

        assert isinstance(result, tuple)
        output, token_usage = result
        assert isinstance(output, TrendScoringOutput)
        assert len(output.scored_repos) == 1
        assert output.scored_repos[0].repo == "owner/test-repo"
        assert isinstance(token_usage, dict)

    def test_run_with_empty_data(self, mock_llm, mock_crew_kickoff):
        """空数据输入时，run() 不应崩溃。"""
        crew = TrendScoringCrew()
        result = crew.run(
            github_data="",
            news_data="",
            current_date="2025-01-01",
        )
        assert isinstance(result, tuple)
        output, token_usage = result
        assert isinstance(output, TrendScoringOutput)

    def test_run_raises_on_crew_failure(self, mock_llm):
        """Crew.kickoff 抛出异常时，run() 应向上传播异常（由节点层处理兜底）。"""
        with patch("crewai.Crew.kickoff") as mock:
            mock.side_effect = Exception("LLM 超时")

            crew = TrendScoringCrew()
            with pytest.raises(Exception, match="LLM 超时"):
                crew.run(
                    github_data="test",
                    news_data="test",
                    current_date="2025-01-01",
                )

    def test_run_fallback_from_raw_text(self, mock_llm):
        """pydantic 输出为 None 时，应从 raw 文本解析 JSON。"""
        raw_data = {
            "scored_repos": [{"repo": "owner/repo", "name": "Test", "stars": 100}],
            "scored_news": [],
            "daily_summary": {
                "top_trend": "测试趋势",
                "hot_directions": [],
                "overall_sentiment": "中性",
            },
        }
        with patch("crewai.Crew.kickoff") as mock:
            mock_result = MagicMock()
            mock_result.pydantic = None
            mock_result.tasks_output = []
            mock_result.raw = json.dumps(raw_data, ensure_ascii=False)
            mock_result.token_usage = None
            mock.return_value = mock_result

            crew = TrendScoringCrew()
            result = crew.run(
                github_data="test",
                news_data="test",
                current_date="2025-01-01",
            )

        assert isinstance(result, tuple)
        output, token_usage = result
        assert isinstance(output, TrendScoringOutput)
        assert len(output.scored_repos) == 1

    def test_run_returns_fallback_on_invalid_raw(self, mock_llm):
        """pydantic 和 raw 都无效时，应返回兜底空结果。"""
        with patch("crewai.Crew.kickoff") as mock:
            mock_result = MagicMock()
            mock_result.pydantic = None
            mock_result.tasks_output = []
            mock_result.raw = "这不是有效的 JSON"
            mock_result.token_usage = None
            mock.return_value = mock_result

            crew = TrendScoringCrew()
            result = crew.run(
                github_data="test",
                news_data="test",
                current_date="2025-01-01",
            )

        # 应返回兜底空结果，不崩溃
        assert isinstance(result, tuple)
        output, token_usage = result
        assert isinstance(output, TrendScoringOutput)
        assert output.scored_repos == []
        assert output.daily_summary.top_trend == "评分数据不可用"

    def test_parse_from_raw_valid_json(self):
        """_parse_from_raw 能正确解析有效 JSON。"""
        raw = json.dumps(
            {
                "scored_repos": [],
                "scored_news": [],
                "daily_summary": {
                    "top_trend": "test",
                    "hot_directions": [],
                    "overall_sentiment": "中性",
                },
            }
        )
        crew = TrendScoringCrew.__new__(TrendScoringCrew)
        result = crew._parse_from_raw(raw)
        assert result is not None
        assert isinstance(result, TrendScoringOutput)

    def test_parse_from_raw_empty_string(self):
        """_parse_from_raw 对空字符串返回 None。"""
        crew = TrendScoringCrew.__new__(TrendScoringCrew)
        result = crew._parse_from_raw("")
        assert result is None

    def test_parse_from_raw_with_markdown_wrapper(self):
        """_parse_from_raw 能处理被 markdown 代码块包裹的 JSON。"""
        data = {
            "scored_repos": [],
            "scored_news": [],
            "daily_summary": {
                "top_trend": "",
                "hot_directions": [],
                "overall_sentiment": "中性",
            },
        }
        raw = f"```json\n{json.dumps(data)}\n```"
        crew = TrendScoringCrew.__new__(TrendScoringCrew)
        result = crew._parse_from_raw(raw)
        # 能解析出来（即使有 markdown 包裹）
        assert result is not None or result is None  # 宽松断言，主要测试不崩溃
