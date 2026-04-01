"""tests/unit/crew/test_rich_data_models.py — RichRepoData & RichNewsData 单元测试。

覆盖场景：
  - 默认值构造
  - 完整字段构造
  - 字段 description 存在性
  - from_candidate / from_dict 转换
  - 向后兼容性（新增字段有默认值）
"""

import pytest
from pydantic import ValidationError

from ai_trending.crew.github_trending.models import (
    RepoCandidate,
    RichRepoData,
)
from ai_trending.crew.new_collect.models import RichNewsData


# =========================================================================
# RichRepoData 测试
# =========================================================================


class TestRichRepoDataDefaults:
    """测试 RichRepoData 使用默认值构造。"""

    def test_minimal_construction(self):
        """只提供必填字段 full_name，其余应取默认值。"""
        repo = RichRepoData(full_name="owner/repo")
        assert repo.full_name == "owner/repo"
        assert repo.description == ""
        assert repo.language == "未知"
        assert repo.stars == 0
        assert repo.topics == []
        assert repo.html_url == ""
        assert repo.created_at == ""
        assert repo.updated_at == ""
        assert repo.stars_7d_ago is None
        assert repo.stars_growth_7d is None
        assert repo.forks == 0
        assert repo.contributors_count is None
        assert repo.commits_last_30d is None
        assert repo.readme_summary == ""

    def test_missing_full_name_raises(self):
        """full_name 是必填字段，缺少时应报错。"""
        with pytest.raises(ValidationError):
            RichRepoData()


class TestRichRepoDataFullConstruction:
    """测试 RichRepoData 全字段构造。"""

    def test_all_fields(self):
        """全字段构造不报错。"""
        repo = RichRepoData(
            full_name="openai/gpt-5",
            description="Next gen language model",
            language="Python",
            stars=50000,
            topics=["ai", "llm", "nlp"],
            html_url="https://github.com/openai/gpt-5",
            created_at="2025-01-01",
            updated_at="2026-03-30",
            stars_7d_ago=45000,
            stars_growth_7d=5000,
            forks=3000,
            contributors_count=120,
            commits_last_30d=85,
            readme_summary="GPT-5 is the next generation...",
        )
        assert repo.full_name == "openai/gpt-5"
        assert repo.stars == 50000
        assert repo.stars_growth_7d == 5000
        assert repo.forks == 3000
        assert repo.contributors_count == 120
        assert repo.commits_last_30d == 85
        assert repo.readme_summary == "GPT-5 is the next generation..."

    def test_none_growth_fields(self):
        """增长字段为 None 时正常工作（无历史数据场景）。"""
        repo = RichRepoData(
            full_name="test/repo",
            stars_7d_ago=None,
            stars_growth_7d=None,
            contributors_count=None,
            commits_last_30d=None,
        )
        assert repo.stars_7d_ago is None
        assert repo.stars_growth_7d is None


class TestRichRepoDataDescriptions:
    """测试所有字段都有 description。"""

    def test_all_fields_have_description(self):
        """RichRepoData 的每个字段都应有 description。"""
        for name, field_info in RichRepoData.model_fields.items():
            assert field_info.description is not None and len(field_info.description) > 0, (
                f"字段 '{name}' 缺少 description"
            )


class TestRichRepoDataFromCandidate:
    """测试从 RepoCandidate 构建 RichRepoData。"""

    def test_basic_conversion(self):
        """基本转换：共有字段正确映射。"""
        candidate = RepoCandidate(
            full_name="owner/repo",
            description="A test repo",
            language="Python",
            stars=1000,
            topics=["ai"],
            html_url="https://github.com/owner/repo",
            created_at="2025-06-01",
            updated_at="2026-03-01",
            readme_summary="This is a test project...",
            stars_7d_ago=900,
            stars_growth_7d=100,
        )
        rich = RichRepoData.from_candidate(candidate)
        assert rich.full_name == "owner/repo"
        assert rich.description == "A test repo"
        assert rich.language == "Python"
        assert rich.stars == 1000
        assert rich.topics == ["ai"]
        assert rich.html_url == "https://github.com/owner/repo"
        assert rich.readme_summary == "This is a test project..."
        assert rich.stars_7d_ago == 900
        assert rich.stars_growth_7d == 100

    def test_conversion_with_none_growth(self):
        """增长数据为 None 时转换正常。"""
        candidate = RepoCandidate(full_name="owner/repo")
        rich = RichRepoData.from_candidate(candidate)
        assert rich.stars_7d_ago is None
        assert rich.stars_growth_7d is None

    def test_new_fields_have_defaults_after_conversion(self):
        """从 RepoCandidate 转换后，新增字段应取默认值。"""
        candidate = RepoCandidate(full_name="owner/repo")
        rich = RichRepoData.from_candidate(candidate)
        assert rich.forks == 0
        assert rich.contributors_count is None
        assert rich.commits_last_30d is None


class TestRichRepoDataBackwardCompat:
    """测试向后兼容性。"""

    def test_serialization_includes_new_fields(self):
        """序列化后包含新增字段。"""
        repo = RichRepoData(full_name="test/repo")
        data = repo.model_dump()
        assert "forks" in data
        assert "contributors_count" in data
        assert "commits_last_30d" in data
        assert "readme_summary" in data

    def test_deserialization_ignores_extra_fields(self):
        """从 dict 反序列化时忽略未知字段（向后兼容）。"""
        data = {
            "full_name": "test/repo",
            "stars": 100,
            "unknown_field": "should_be_ignored",
        }
        # Pydantic v2 默认忽略 extra 字段
        repo = RichRepoData.model_validate(data)
        assert repo.full_name == "test/repo"
        assert repo.stars == 100


# =========================================================================
# RichNewsData 测试
# =========================================================================


class TestRichNewsDataDefaults:
    """测试 RichNewsData 使用默认值构造。"""

    def test_minimal_construction(self):
        """只提供必填字段 title，其余应取默认值。"""
        news = RichNewsData(title="AI breakthrough")
        assert news.title == "AI breakthrough"
        assert news.url == ""
        assert news.score == 0
        assert news.source == ""
        assert news.summary == ""
        assert news.time == ""
        assert news.content_excerpt == ""

    def test_missing_title_raises(self):
        """title 是必填字段，缺少时应报错。"""
        with pytest.raises(ValidationError):
            RichNewsData()


class TestRichNewsDataFullConstruction:
    """测试 RichNewsData 全字段构造。"""

    def test_all_fields(self):
        """全字段构造不报错。"""
        news = RichNewsData(
            title="OpenAI releases GPT-5",
            url="https://openai.com/blog/gpt-5",
            score=500,
            source="Hacker News",
            summary="OpenAI has released GPT-5...",
            time="2026-04-01",
            content_excerpt="Today we are excited to announce GPT-5...",
        )
        assert news.title == "OpenAI releases GPT-5"
        assert news.score == 500
        assert news.source == "Hacker News"
        assert news.content_excerpt.startswith("Today we are")


class TestRichNewsDataDescriptions:
    """测试所有字段都有 description。"""

    def test_all_fields_have_description(self):
        """RichNewsData 的每个字段都应有 description。"""
        for name, field_info in RichNewsData.model_fields.items():
            assert field_info.description is not None and len(field_info.description) > 0, (
                f"字段 '{name}' 缺少 description"
            )


class TestRichNewsDataFromDict:
    """测试从 dict 构建 RichNewsData。"""

    def test_basic_conversion(self):
        """标准 fetcher 输出 dict 转换正确。"""
        data = {
            "title": "AI News",
            "url": "https://example.com/news",
            "score": 100,
            "source": "Hacker News",
            "summary": "Some summary...",
            "time": "2026-04-01",
        }
        news = RichNewsData.from_dict(data)
        assert news.title == "AI News"
        assert news.url == "https://example.com/news"
        assert news.score == 100
        assert news.source == "Hacker News"
        assert news.summary == "Some summary..."
        assert news.time == "2026-04-01"
        assert news.content_excerpt == ""  # fetcher 不输出此字段

    def test_conversion_with_content_excerpt(self):
        """包含 content_excerpt 的 dict 转换正确。"""
        data = {
            "title": "AI News",
            "content_excerpt": "Full article text...",
        }
        news = RichNewsData.from_dict(data)
        assert news.content_excerpt == "Full article text..."

    def test_conversion_with_empty_dict(self):
        """空 dict 时 title 为空字符串（不报错，保持宽容）。"""
        news = RichNewsData.from_dict({})
        assert news.title == ""
        assert news.url == ""
        assert news.score == 0

    def test_conversion_ignores_unknown_keys(self):
        """未知 key 被忽略，不报错。"""
        data = {
            "title": "Test",
            "unknown_key": "should_be_ignored",
            "another_unknown": 42,
        }
        news = RichNewsData.from_dict(data)
        assert news.title == "Test"

    def test_conversion_with_none_values(self):
        """值为 None 时自动回退为默认值。"""
        data = {
            "title": None,
            "url": None,
            "summary": None,
            "score": None,
        }
        news = RichNewsData.from_dict(data)
        assert news.title == ""
        assert news.url == ""
        assert news.summary == ""
        assert news.score == 0


class TestRichNewsDataBackwardCompat:
    """测试向后兼容性。"""

    def test_serialization_includes_new_fields(self):
        """序列化后包含 content_excerpt 字段。"""
        news = RichNewsData(title="Test")
        data = news.model_dump()
        assert "content_excerpt" in data

    def test_model_dump_matches_dict_format(self):
        """model_dump() 输出与 fetcher dict 格式兼容。"""
        news = RichNewsData(
            title="Test",
            url="https://example.com",
            score=50,
            source="Reddit",
            summary="Summary",
            time="2026-04-01",
        )
        data = news.model_dump()
        # 所有 fetcher 标准字段都应在输出中
        assert all(k in data for k in ["title", "url", "score", "source", "summary", "time"])
