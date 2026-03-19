"""WeChatArticleTool 测试."""

import os
from datetime import datetime
from unittest.mock import patch

import pytest

from ai_trending.tools.wechat_article_tool import WeChatArticleInput, WeChatArticleTool


# ── fixtures ──────────────────────────────────────────────────────

@pytest.fixture
def tool():
    return WeChatArticleTool()


SAMPLE_MD = """# AI 日报

## 今日热点

### 1. GPT-5 发布
- **来源**: OpenAI
- **链接**: https://openai.com/gpt5
- **热度**: 500 分
- **摘要**: OpenAI 发布了 GPT-5 模型

---

> 这是一段引用内容

1. 第一条有序列表
2. 第二条有序列表

普通段落内容，包含 `行内代码` 和 **加粗文字** 以及 *斜体文字*。
"""


# ── WeChatArticleInput schema ─────────────────────────────────────

class TestWeChatArticleInput:
    def test_required_content(self):
        inp = WeChatArticleInput(content="some content")
        assert inp.content == "some content"

    def test_default_title_empty(self):
        inp = WeChatArticleInput(content="x")
        assert inp.title == ""

    def test_default_author(self):
        inp = WeChatArticleInput(content="x")
        assert inp.author == "AI Trending Bot"

    def test_custom_values(self):
        inp = WeChatArticleInput(content="x", title="My Title", author="Custom Author")
        assert inp.title == "My Title"
        assert inp.author == "Custom Author"


# ── _inline_format ────────────────────────────────────────────────

class TestInlineFormat:
    def test_bold_text(self, tool):
        result = tool._inline_format("**加粗文字**")
        assert "<strong" in result
        assert "加粗文字" in result

    def test_italic_text(self, tool):
        result = tool._inline_format("*斜体文字*")
        assert "<em>" in result
        assert "斜体文字" in result

    def test_inline_code(self, tool):
        result = tool._inline_format("`code snippet`")
        assert "<code" in result
        assert "code snippet" in result

    def test_markdown_link(self, tool):
        result = tool._inline_format("[OpenAI](https://openai.com)")
        assert '<a href="https://openai.com"' in result
        assert "OpenAI" in result

    def test_bare_url(self, tool):
        result = tool._inline_format("访问 https://openai.com 了解更多")
        assert '<a href="https://openai.com"' in result

    def test_star_emoji_styled(self, tool):
        result = tool._inline_format("⭐ 500 分")
        assert 'style="color: #e0a84c;"' in result

    def test_plain_text_unchanged(self, tool):
        result = tool._inline_format("普通文字")
        assert result == "普通文字"

    def test_combined_formats(self, tool):
        result = tool._inline_format("**加粗** 和 `代码` 以及 [链接](https://example.com)")
        assert "<strong" in result
        assert "<code" in result
        assert "<a href" in result


# ── _markdown_to_wechat_html ──────────────────────────────────────

class TestMarkdownToWechatHtml:
    def test_h2_converted(self, tool):
        html = tool._markdown_to_wechat_html("## 今日热点")
        assert "<h2" in html
        assert "今日热点" in html

    def test_h3_creates_card(self, tool):
        html = tool._markdown_to_wechat_html("### 项目标题")
        assert "<h3" in html
        assert "项目标题" in html
        # 卡片容器
        assert "border-radius: 8px" in html

    def test_h1_skipped(self, tool):
        html = tool._markdown_to_wechat_html("# 主标题")
        assert "<h1" not in html

    def test_unordered_list(self, tool):
        md = "- 第一项\n- 第二项\n- 第三项"
        html = tool._markdown_to_wechat_html(md)
        assert "<ul" in html
        assert html.count("<li") == 3

    def test_ordered_list(self, tool):
        md = "1. 第一条\n2. 第二条"
        html = tool._markdown_to_wechat_html(md)
        assert html.count("<span") >= 2  # 序号 span

    def test_blockquote(self, tool):
        html = tool._markdown_to_wechat_html("> 引用内容")
        assert "border-left" in html
        assert "引用内容" in html

    def test_horizontal_rule(self, tool):
        html = tool._markdown_to_wechat_html("---")
        assert "<hr" in html

    def test_paragraph(self, tool):
        html = tool._markdown_to_wechat_html("普通段落文字")
        assert "<p" in html
        assert "普通段落文字" in html

    def test_empty_lines_close_lists(self, tool):
        md = "- 列表项\n\n普通段落"
        html = tool._markdown_to_wechat_html(md)
        assert "</ul>" in html

    def test_full_markdown_conversion(self, tool):
        html = tool._markdown_to_wechat_html(SAMPLE_MD)
        assert "<h2" in html
        assert "<h3" in html
        assert "<li" in html
        assert "<hr" in html


# ── _run ──────────────────────────────────────────────────────────

class TestWeChatArticleToolRun:
    def test_run_creates_html_file(self, tool, tmp_output_dir):
        result = tool._run(content=SAMPLE_MD)
        output_dir = tmp_output_dir / "output"
        html_files = list(output_dir.glob("wechat_*.html"))
        assert len(html_files) == 1

    def test_run_returns_success_message(self, tool, tmp_output_dir):
        result = tool._run(content=SAMPLE_MD)
        assert "✅" in result
        assert "微信公众号文章已生成" in result

    def test_run_auto_generates_title(self, tool, tmp_output_dir):
        result = tool._run(content=SAMPLE_MD, title="")
        today = datetime.now().strftime("%Y-%m-%d")
        assert today in result

    def test_run_uses_custom_title(self, tool, tmp_output_dir):
        result = tool._run(content=SAMPLE_MD, title="自定义标题")
        assert "自定义标题" in result

    def test_run_uses_custom_author(self, tool, tmp_output_dir):
        result = tool._run(content=SAMPLE_MD, author="测试作者")
        # 读取生成的 HTML 文件验证
        output_dir = tmp_output_dir / "output"
        html_file = list(output_dir.glob("wechat_*.html"))[0]
        html_content = html_file.read_text(encoding="utf-8")
        assert "测试作者" in html_content

    def test_run_html_contains_body_content(self, tool, tmp_output_dir):
        result = tool._run(content="## 测试章节\n\n测试内容")
        output_dir = tmp_output_dir / "output"
        html_file = list(output_dir.glob("wechat_*.html"))[0]
        html_content = html_file.read_text(encoding="utf-8")
        assert "测试章节" in html_content
        assert "测试内容" in html_content

    def test_run_html_has_wechat_template_structure(self, tool, tmp_output_dir):
        """生成的 HTML 应包含微信公众号模板的关键结构."""
        tool._run(content=SAMPLE_MD)
        output_dir = tmp_output_dir / "output"
        html_file = list(output_dir.glob("wechat_*.html"))[0]
        html_content = html_file.read_text(encoding="utf-8")
        assert "<!DOCTYPE html>" in html_content
        assert "DAILY REPORT" in html_content
        assert "END" in html_content

    def test_run_result_contains_html_preview(self, tool, tmp_output_dir):
        """返回结果应包含 HTML 内容预览."""
        result = tool._run(content=SAMPLE_MD)
        assert "<!DOCTYPE html>" in result
