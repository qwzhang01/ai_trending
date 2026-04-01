"""tests/unit/crew/test_writing_brief.py — WritingBrief 模型 & _build_writing_brief 单元测试。

覆盖 TASK-004 的所有新增代码：
- RepoBrief / NewsBrief / WritingBrief 模型
- WritingBrief.format_for_prompt() 方法
- nodes.py 中的 _build_writing_brief() 函数
- nodes.py 中的 _decide_signal_strength() 函数
- write_report_node 对 WritingBrief 的集成
"""

import json
from unittest.mock import MagicMock, patch

import pytest

from ai_trending.crew.report_writing.models import (
    NewsBrief,
    RepoBrief,
    ReportOutput,
    WritingBrief,
)
from ai_trending.nodes import (
    _build_writing_brief,
    _decide_signal_strength,
    write_report_node,
)

# ── RepoBrief 模型测试 ───────────────────────────────────────────────────────


class TestRepoBrief:
    """测试 RepoBrief Pydantic 模型。"""

    def test_default_values(self):
        """空构造不报错，默认值合理。"""
        repo = RepoBrief()
        assert repo.name == ""
        assert repo.url == ""
        assert repo.stars == 0
        assert repo.stars_growth_7d is None
        assert repo.language == ""
        assert repo.readme_summary == ""
        assert repo.story_hook == ""
        assert repo.technical_detail == ""
        assert repo.target_audience == ""
        assert repo.suggested_angle == ""
        assert repo.one_line_reason == ""

    def test_full_construction(self):
        """完整构造包含所有字段的 RepoBrief。"""
        repo = RepoBrief(
            name="test-repo",
            url="https://github.com/owner/test-repo",
            stars=5000,
            stars_growth_7d=500,
            language="Python",
            readme_summary="一个测试项目",
            story_hook="一个月前还没人听过",
            technical_detail="支持多种推理后端",
            target_audience="做本地推理的开发者",
            suggested_angle="痛点切入",
            one_line_reason="解决本地推理的性能瓶颈",
        )
        assert repo.name == "test-repo"
        assert repo.stars == 5000
        assert repo.stars_growth_7d == 500

    def test_stars_growth_none(self):
        """stars_growth_7d 为 None 时不报错。"""
        repo = RepoBrief(name="test", stars=100, stars_growth_7d=None)
        assert repo.stars_growth_7d is None


# ── NewsBrief 模型测试 ───────────────────────────────────────────────────────


class TestNewsBrief:
    """测试 NewsBrief Pydantic 模型。"""

    def test_default_values(self):
        """空构造不报错，默认值合理。"""
        news = NewsBrief()
        assert news.title == ""
        assert news.url == ""
        assert news.source == ""
        assert news.content_excerpt == ""
        assert news.so_what_analysis == ""
        assert news.credibility_label == "🟡 社区讨论"
        assert news.category == ""

    def test_full_construction(self):
        """完整构造包含所有字段的 NewsBrief。"""
        news = NewsBrief(
            title="OpenAI 发布 GPT-5",
            url="https://openai.com/blog/gpt-5",
            source="OpenAI Blog",
            content_excerpt="GPT-5 在推理能力上有了质的飞跃...",
            so_what_analysis="推理成本下降 50%，更多中小企业可以负担",
            credibility_label="🟢 一手信源",
            category="大厂动态",
        )
        assert news.title == "OpenAI 发布 GPT-5"
        assert news.credibility_label == "🟢 一手信源"


# ── WritingBrief 模型测试 ────────────────────────────────────────────────────


class TestWritingBrief:
    """测试 WritingBrief Pydantic 模型。"""

    def test_default_values(self):
        """空构造不报错，默认值合理。"""
        brief = WritingBrief()
        assert brief.signal_strength_suggestion == "yellow"
        assert brief.headline_candidate == ""
        assert brief.headline_story_hook == ""
        assert brief.top_repos == []
        assert brief.top_news == []
        assert brief.trend_summary == ""
        assert brief.causal_explanation == ""
        assert brief.data_support == ""
        assert brief.forward_looking == ""
        assert brief.hot_directions == []

    def test_full_construction(self):
        """完整构造 WritingBrief。"""
        brief = WritingBrief(
            signal_strength_suggestion="red",
            headline_candidate="test-repo",
            headline_story_hook="一个月前还没人听过",
            top_repos=[RepoBrief(name="test-repo", stars=5000)],
            top_news=[NewsBrief(title="GPT-5 发布")],
            trend_summary="LLM 推理成本持续下降",
            causal_explanation="开源模型追赶闭源速度加快",
            data_support="过去一个月开源推理框架增长 200%",
            forward_looking="下一季度端侧部署将成主流",
            hot_directions=["推理优化", "Agent 框架"],
        )
        assert brief.signal_strength_suggestion == "red"
        assert len(brief.top_repos) == 1
        assert len(brief.top_news) == 1
        assert len(brief.hot_directions) == 2


# ── WritingBrief.format_for_prompt() 测试 ────────────────────────────────────


class TestFormatForPrompt:
    """测试 WritingBrief.format_for_prompt() 格式化方法。"""

    def test_empty_brief_produces_output(self):
        """空 WritingBrief 也应生成有效输出。"""
        brief = WritingBrief()
        text = brief.format_for_prompt()
        assert isinstance(text, str)
        assert len(text) > 0
        # 应包含信号强度
        assert "今日信号强度建议" in text

    def test_signal_strength_red(self):
        """signal_strength_suggestion='red' 应渲染为 🔴 重大变化日。"""
        brief = WritingBrief(signal_strength_suggestion="red")
        text = brief.format_for_prompt()
        assert "🔴 重大变化日" in text

    def test_signal_strength_yellow(self):
        """signal_strength_suggestion='yellow' 应渲染为 🟡 常规更新日。"""
        brief = WritingBrief(signal_strength_suggestion="yellow")
        text = brief.format_for_prompt()
        assert "🟡 常规更新日" in text

    def test_signal_strength_green(self):
        """signal_strength_suggestion='green' 应渲染为 🟢 平静日。"""
        brief = WritingBrief(signal_strength_suggestion="green")
        text = brief.format_for_prompt()
        assert "🟢 平静日" in text

    def test_signal_strength_unknown_fallback(self):
        """未知信号强度应回退到 🟡 常规更新日。"""
        brief = WritingBrief(signal_strength_suggestion="unknown")
        text = brief.format_for_prompt()
        assert "🟡 常规更新日" in text

    def test_headline_info_in_output(self):
        """头条候选和故事钩子应出现在输出中。"""
        brief = WritingBrief(
            headline_candidate="awesome-repo",
            headline_story_hook="改变推理格局",
        )
        text = brief.format_for_prompt()
        assert "awesome-repo" in text
        assert "改变推理格局" in text

    def test_repos_formatted(self):
        """top_repos 列表应被格式化为可读文本。"""
        brief = WritingBrief(
            top_repos=[
                RepoBrief(
                    name="repo-a",
                    url="https://github.com/owner/repo-a",
                    stars=3000,
                    stars_growth_7d=300,
                    language="Python",
                    story_hook="改变游戏规则",
                    technical_detail="支持 Metal 后端",
                    target_audience="AI 研究者",
                    one_line_reason="性能提升 3 倍",
                    readme_summary="这是一个推理框架",
                    suggested_angle="痛点切入",
                ),
            ]
        )
        text = brief.format_for_prompt()
        assert "repo-a" in text
        assert "3000" in text
        assert "+300" in text
        assert "改变游戏规则" in text
        assert "支持 Metal 后端" in text
        assert "AI 研究者" in text
        assert "推理框架" in text
        assert "痛点切入" in text
        assert "请直接使用上方的钩子" in text  # OPT-001 精简后的文案

    def test_repos_without_growth(self):
        """stars_growth_7d 为 None 时不显示增长信息。"""
        brief = WritingBrief(
            top_repos=[RepoBrief(name="repo-b", stars=1000, stars_growth_7d=None)]
        )
        text = brief.format_for_prompt()
        assert "1000" in text
        assert "（+" not in text

    def test_news_formatted(self):
        """top_news 列表应被格式化为可读文本。"""
        brief = WritingBrief(
            top_news=[
                NewsBrief(
                    title="GPT-5 发布",
                    url="https://example.com/news",
                    source="OpenAI Blog",
                    so_what_analysis="推理成本暴降",
                    credibility_label="🟢 一手信源",
                    category="大厂动态",
                    content_excerpt="GPT-5 推理速度提升 10 倍",
                ),
            ]
        )
        text = brief.format_for_prompt()
        assert "GPT-5 发布" in text
        assert "OpenAI Blog" in text
        assert "推理成本暴降" in text
        assert "🟢 一手信源" in text
        assert "大厂动态" in text
        # content_excerpt 已从 format_for_prompt 中移除（OPT-001 精简噪音字段）
        assert "推理速度提升 10 倍" not in text
        assert "请直接使用上方 So What 分析" in text  # OPT-001 精简后的文案

    def test_trend_section_formatted(self):
        """趋势判断相关字段应出现在输出中。"""
        brief = WritingBrief(
            trend_summary="推理成本下降",
            causal_explanation="开源追赶闭源",
            data_support="增长 200%",
            forward_looking="端侧部署成主流",
            hot_directions=["推理优化", "Agent 框架"],
        )
        text = brief.format_for_prompt()
        assert "推理成本下降" in text
        assert "开源追赶闭源" in text
        assert "增长 200%" in text
        assert "端侧部署成主流" in text
        assert "推理优化" in text
        assert "Agent 框架" in text


# ── _decide_signal_strength 测试 ─────────────────────────────────────────────


class TestDecideSignalStrength:
    """测试信号强度判断函数。"""

    def test_red_on_high_repo_score(self):
        """项目综合分 >= 9.0 时返回 red。"""
        repo = MagicMock()
        repo.scores = {"综合": 9.5}
        result = _decide_signal_strength([repo], [])
        assert result == "red"

    def test_red_on_high_news_score(self):
        """新闻影响力分 >= 9.0 时返回 red。"""
        news = MagicMock()
        news.impact_score = 9.0
        result = _decide_signal_strength([], [news])
        assert result == "red"

    def test_yellow_on_medium_score(self):
        """项目综合分 >= 7.0 但 < 9.0 时返回 yellow。"""
        repo = MagicMock()
        repo.scores = {"综合": 7.5}
        result = _decide_signal_strength([repo], [])
        assert result == "yellow"

    def test_yellow_on_medium_news_score(self):
        """新闻影响力分 >= 7.0 但 < 9.0 时返回 yellow。"""
        news = MagicMock()
        news.impact_score = 7.5
        result = _decide_signal_strength([], [news])
        assert result == "yellow"

    def test_green_on_low_scores(self):
        """所有分数 < 7.0 时返回 green。"""
        repo = MagicMock()
        repo.scores = {"综合": 5.0}
        news = MagicMock()
        news.impact_score = 4.0
        result = _decide_signal_strength([repo], [news])
        assert result == "green"

    def test_empty_lists_return_green(self):
        """空列表时返回 green。"""
        result = _decide_signal_strength([], [])
        assert result == "green"

    def test_uses_overall_key(self):
        """支持 'overall' 作为 scores 字典的 key。"""
        repo = MagicMock()
        repo.scores = {"overall": 9.0}
        result = _decide_signal_strength([repo], [])
        assert result == "red"

    def test_missing_scores_attribute(self):
        """scores 属性为 None 时不崩溃。"""
        repo = MagicMock()
        repo.scores = None
        result = _decide_signal_strength([repo], [])
        assert result == "green"


# ── _build_writing_brief 测试 ────────────────────────────────────────────────


class TestBuildWritingBrief:
    """测试从评分 JSON 构建写作简报的函数。"""

    @pytest.fixture
    def sample_scoring_json(self):
        """标准评分 JSON 数据。"""
        return json.dumps(
            {
                "scored_repos": [
                    {
                        "repo": "owner/repo-a",
                        "name": "repo-a",
                        "url": "https://github.com/owner/repo-a",
                        "stars": 5000,
                        "stars_growth_7d": 500,
                        "language": "Python",
                        "readme_summary": "一个推理框架",
                        "story_hook": "改变推理格局",
                        "technical_detail": "支持 Metal 后端",
                        "target_audience": "AI 研究者",
                        "one_line_reason": "性能提升 3 倍",
                        "scores": {"综合": 8.5},
                    },
                    {
                        "repo": "owner/repo-b",
                        "name": "repo-b",
                        "url": "https://github.com/owner/repo-b",
                        "stars": 3000,
                        "language": "Rust",
                        "story_hook": "速度之王",
                        "technical_detail": "零拷贝架构",
                        "target_audience": "系统工程师",
                        "one_line_reason": "内存占用降低 80%",
                        "scores": {"综合": 7.0},
                    },
                ],
                "scored_news": [
                    {
                        "title": "GPT-5 发布",
                        "url": "https://openai.com/gpt-5",
                        "source": "OpenAI Blog",
                        "so_what_analysis": "推理成本暴降",
                        "credibility_label": "🟢 一手信源",
                        "category": "大厂动态",
                        "impact_score": 8.0,
                        "content_excerpt": "推理速度提升 10 倍",
                    },
                ],
                "daily_summary": {
                    "top_trend": "推理成本持续下降",
                    "causal_explanation": "开源模型追赶闭源速度加快",
                    "data_support": "月增长 200%",
                    "forward_looking": "端侧部署将成主流",
                    "hot_directions": ["推理优化", "Agent 框架", "多模态"],
                },
            },
            ensure_ascii=False,
        )

    def test_basic_construction(self, sample_scoring_json):
        """正常 JSON 应构建出有效的 WritingBrief。"""
        brief = _build_writing_brief(sample_scoring_json, "", "")
        assert isinstance(brief, WritingBrief)
        assert len(brief.top_repos) == 2
        assert len(brief.top_news) == 1
        assert brief.trend_summary == "推理成本持续下降"

    def test_signal_strength_from_scores(self, sample_scoring_json):
        """信号强度应基于评分数据自动判断。"""
        brief = _build_writing_brief(sample_scoring_json, "", "")
        # 最高综合分 8.5，最高新闻分 8.0 → yellow
        assert brief.signal_strength_suggestion == "yellow"

    def test_signal_strength_red(self):
        """高分数据应判断为 red。"""
        data = json.dumps(
            {
                "scored_repos": [{"name": "hot", "scores": {"综合": 9.5}}],
                "scored_news": [],
                "daily_summary": {},
            }
        )
        brief = _build_writing_brief(data, "", "")
        assert brief.signal_strength_suggestion == "red"

    def test_signal_strength_green(self):
        """低分数据应判断为 green。"""
        data = json.dumps(
            {
                "scored_repos": [{"name": "meh", "scores": {"综合": 3.0}}],
                "scored_news": [{"title": "小事", "impact_score": 2.0}],
                "daily_summary": {},
            }
        )
        brief = _build_writing_brief(data, "", "")
        assert brief.signal_strength_suggestion == "green"

    def test_headline_from_first_repo(self, sample_scoring_json):
        """头条候选应取评分最高（第一个）的项目。"""
        brief = _build_writing_brief(sample_scoring_json, "", "")
        assert brief.headline_candidate == "repo-a"
        assert brief.headline_story_hook == "改变推理格局"

    def test_repo_brief_fields(self, sample_scoring_json):
        """RepoBrief 应包含所有叙事字段。"""
        brief = _build_writing_brief(sample_scoring_json, "", "")
        repo = brief.top_repos[0]
        assert repo.name == "repo-a"
        assert repo.stars == 5000
        assert repo.stars_growth_7d == 500
        assert repo.language == "Python"
        assert repo.readme_summary == "一个推理框架"
        assert repo.story_hook == "改变推理格局"
        assert repo.technical_detail == "支持 Metal 后端"
        assert repo.target_audience == "AI 研究者"
        assert repo.one_line_reason == "性能提升 3 倍"

    def test_suggested_angles_rotate(self, sample_scoring_json):
        """每个项目应被分配不同的切入角度（轮转）。"""
        brief = _build_writing_brief(sample_scoring_json, "", "")
        assert brief.top_repos[0].suggested_angle == "痛点切入"
        assert brief.top_repos[1].suggested_angle == "规模切入"

    def test_news_brief_fields(self, sample_scoring_json):
        """NewsBrief 应包含所有叙事字段。"""
        brief = _build_writing_brief(sample_scoring_json, "", "")
        news = brief.top_news[0]
        assert news.title == "GPT-5 发布"
        assert news.so_what_analysis == "推理成本暴降"
        assert news.credibility_label == "🟢 一手信源"
        assert news.category == "大厂动态"
        assert news.content_excerpt == "推理速度提升 10 倍"

    def test_daily_summary_fields(self, sample_scoring_json):
        """趋势判断字段应正确提取。"""
        brief = _build_writing_brief(sample_scoring_json, "", "")
        assert brief.trend_summary == "推理成本持续下降"
        assert brief.causal_explanation == "开源模型追赶闭源速度加快"
        assert brief.data_support == "月增长 200%"
        assert brief.forward_looking == "端侧部署将成主流"
        assert brief.hot_directions == ["推理优化", "Agent 框架", "多模态"]

    def test_empty_json(self):
        """空 JSON 应返回有效的默认 WritingBrief。"""
        brief = _build_writing_brief("{}", "", "")
        assert isinstance(brief, WritingBrief)
        assert brief.top_repos == []
        assert brief.top_news == []
        assert brief.signal_strength_suggestion == "green"

    def test_invalid_json(self):
        """无效 JSON 不应崩溃，返回默认 WritingBrief。"""
        brief = _build_writing_brief("not valid json", "", "")
        assert isinstance(brief, WritingBrief)
        assert brief.top_repos == []

    def test_none_input(self):
        """None 输入不应崩溃。"""
        brief = _build_writing_brief(None, "", "")
        assert isinstance(brief, WritingBrief)

    def test_empty_string_input(self):
        """空字符串输入不应崩溃。"""
        brief = _build_writing_brief("", "", "")
        assert isinstance(brief, WritingBrief)

    def test_max_5_repos(self):
        """最多只取前 5 个项目。"""
        repos = [
            {"name": f"repo-{i}", "scores": {"综合": 8.0 - i * 0.1}} for i in range(10)
        ]
        data = json.dumps(
            {"scored_repos": repos, "scored_news": [], "daily_summary": {}}
        )
        brief = _build_writing_brief(data, "", "")
        assert len(brief.top_repos) == 5

    def test_max_8_news(self):
        """最多只取前 8 条新闻。"""
        news = [
            {"title": f"news-{i}", "impact_score": 8.0 - i * 0.1} for i in range(15)
        ]
        data = json.dumps(
            {"scored_repos": [], "scored_news": news, "daily_summary": {}}
        )
        brief = _build_writing_brief(data, "", "")
        assert len(brief.top_news) == 8

    def test_format_for_prompt_round_trip(self, sample_scoring_json):
        """构建 → 格式化 → 包含关键信息的端到端验证。"""
        brief = _build_writing_brief(sample_scoring_json, "", "")
        text = brief.format_for_prompt()
        # 关键素材应在格式化输出中
        assert "repo-a" in text
        assert "改变推理格局" in text
        assert "GPT-5 发布" in text
        assert "推理成本暴降" in text
        assert "推理成本持续下降" in text


# ── write_report_node 集成测试 ───────────────────────────────────────────────


class TestWriteReportNodeWithBrief:
    """测试 write_report_node 使用 WritingBrief 的集成行为。"""

    SAMPLE_SCORING = json.dumps(
        {
            "scored_repos": [
                {
                    "name": "test-repo",
                    "url": "https://github.com/owner/test-repo",
                    "stars": 5000,
                    "story_hook": "改变推理格局",
                    "technical_detail": "支持 Metal",
                    "target_audience": "AI 开发者",
                    "one_line_reason": "性能提升",
                    "scores": {"综合": 8.0},
                }
            ],
            "scored_news": [
                {
                    "title": "GPT-5",
                    "so_what_analysis": "成本下降",
                    "credibility_label": "🟢 一手信源",
                    "category": "大厂动态",
                    "impact_score": 7.5,
                }
            ],
            "daily_summary": {
                "top_trend": "推理优化",
                "causal_explanation": "开源追赶",
                "data_support": "增长 200%",
                "forward_looking": "端侧部署",
                "hot_directions": ["推理优化"],
            },
        }
    )

    def test_passes_writing_brief_to_crew(self, tmp_path, monkeypatch):
        """write_report_node 应将 writing_brief 传递给 ReportWritingCrew.run()。"""
        monkeypatch.chdir(tmp_path)
        fake_output = ReportOutput(content="# 日报\n测试内容", validation_issues=[])
        fake_token_usage = {"total_tokens": 100}

        with patch("ai_trending.crew.report_writing.ReportWritingCrew") as mock_cls:
            mock_cls.return_value.run.return_value = (fake_output, fake_token_usage)

            state = {
                "current_date": "2025-01-01",
                "github_data": "test github",
                "news_data": "test news",
                "scoring_result": self.SAMPLE_SCORING,
            }
            write_report_node(state)

            # 验证 run() 被调用时包含 writing_brief 参数
            call_kwargs = mock_cls.return_value.run.call_args
            assert "writing_brief" in call_kwargs.kwargs or (len(call_kwargs.args) > 5)
            # 获取 writing_brief 参数值
            if call_kwargs.kwargs.get("writing_brief"):
                brief_text = call_kwargs.kwargs["writing_brief"]
            else:
                brief_text = call_kwargs.args[5] if len(call_kwargs.args) > 5 else ""

            # writing_brief 应包含关键素材
            assert "test-repo" in brief_text
            assert "改变推理格局" in brief_text
            assert "GPT-5" in brief_text
            assert "成本下降" in brief_text

    def test_writing_brief_contains_signal_strength(self, tmp_path, monkeypatch):
        """writing_brief 文本应包含信号强度建议。"""
        monkeypatch.chdir(tmp_path)
        fake_output = ReportOutput(content="# 日报\n内容", validation_issues=[])

        with patch("ai_trending.crew.report_writing.ReportWritingCrew") as mock_cls:
            mock_cls.return_value.run.return_value = (fake_output, {"total_tokens": 0})

            state = {
                "current_date": "2025-01-01",
                "github_data": "",
                "news_data": "",
                "scoring_result": self.SAMPLE_SCORING,
            }
            write_report_node(state)

            call_kwargs = mock_cls.return_value.run.call_args.kwargs
            brief_text = call_kwargs.get("writing_brief", "")
            assert "今日信号强度建议" in brief_text

    def test_empty_scoring_result_still_works(self, tmp_path, monkeypatch):
        """scoring_result 为空时，write_report_node 不崩溃。"""
        monkeypatch.chdir(tmp_path)
        fake_output = ReportOutput(content="# 日报\n内容", validation_issues=[])

        with patch("ai_trending.crew.report_writing.ReportWritingCrew") as mock_cls:
            mock_cls.return_value.run.return_value = (fake_output, {"total_tokens": 0})

            state = {
                "current_date": "2025-01-01",
                "github_data": "",
                "news_data": "",
                "scoring_result": "",
            }
            result = write_report_node(state)
            assert "report_content" in result
