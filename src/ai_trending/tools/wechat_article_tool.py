"""WeChat Article Tool — 将报告转换为微信公众号可发布的 HTML 格式文章."""

import os
from datetime import datetime
from typing import Type

from crewai.tools import BaseTool
from pydantic import BaseModel, Field


class WeChatArticleInput(BaseModel):
    """Input schema for WeChatArticleTool."""

    content: str = Field(
        ...,
        description="要转换为微信文章的 Markdown 报告内容",
    )
    title: str = Field(
        default="",
        description="文章标题，留空则自动生成",
    )
    author: str = Field(
        default="AI Trending Bot",
        description="文章作者名",
    )


# 微信公众号文章 HTML 模板 — 适配微信编辑器的内联样式
WECHAT_HTML_TEMPLATE = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
</head>
<body>
<div style="max-width: 680px; margin: 0 auto; padding: 20px; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif; color: #333; line-height: 1.8;">

<!-- 头部 Banner -->
<div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); border-radius: 12px; padding: 30px; margin-bottom: 24px; text-align: center;">
    <h1 style="color: #fff; font-size: 22px; margin: 0 0 8px 0; font-weight: 700;">{title}</h1>
    <p style="color: rgba(255,255,255,0.85); font-size: 13px; margin: 0;">{date} | 作者: {author}</p>
</div>

<!-- 导读 -->
<div style="background: #f0f4ff; border-left: 4px solid #667eea; padding: 16px 20px; border-radius: 0 8px 8px 0; margin-bottom: 24px;">
    <p style="margin: 0; font-size: 14px; color: #555;">📌 <strong>导读</strong>：本文整理了今日最热门的 AI 开源项目与行业新闻，涵盖大模型、AI Agent 等前沿领域的最新动态。</p>
</div>

<!-- 正文内容 -->
{body}

<!-- 尾部 -->
<div style="margin-top: 32px; padding-top: 20px; border-top: 1px solid #e5e5e5; text-align: center;">
    <p style="font-size: 13px; color: #999;">— END —</p>
    <p style="font-size: 12px; color: #bbb;">由 AI Trending Bot 自动生成 | {date}</p>
    <p style="font-size: 12px; color: #bbb;">觉得有用？欢迎转发分享给你的朋友 🚀</p>
</div>

</div>
</body>
</html>"""


class WeChatArticleTool(BaseTool):
    """将 Markdown 报告内容转换为微信公众号适配的 HTML 文章."""

    name: str = "wechat_article_tool"
    description: str = (
        "将 AI 趋势报告转换为适合微信公众号发布的 HTML 文章格式。"
        "输出包含美观的内联样式，可直接复制到微信公众号编辑器。"
        "同时保存为本地 HTML 文件。"
    )
    args_schema: Type[BaseModel] = WeChatArticleInput

    def _run(
        self,
        content: str,
        title: str = "",
        author: str = "AI Trending Bot",
    ) -> str:
        """将 Markdown 内容转换为微信公众号文章 HTML."""
        today = datetime.now().strftime("%Y-%m-%d")

        if not title:
            title = f"🔥 AI 日报 | {today} 最热 AI 开源项目与行业新闻"

        # 将 Markdown 内容转换为微信适配的 HTML
        body_html = self._markdown_to_wechat_html(content)

        # 渲染模板
        article_html = WECHAT_HTML_TEMPLATE.format(
            title=title,
            date=today,
            author=author,
            body=body_html,
        )

        # 保存到本地
        output_dir = os.path.join(os.getcwd(), "output")
        os.makedirs(output_dir, exist_ok=True)
        html_path = os.path.join(output_dir, f"wechat_{today}.html")

        with open(html_path, "w", encoding="utf-8") as f:
            f.write(article_html)

        return (
            f"✅ 微信公众号文章已生成！\n"
            f"- **标题**: {title}\n"
            f"- **本地文件**: {html_path}\n"
            f"- **使用方式**: 打开 HTML 文件，复制全部内容，粘贴到微信公众号编辑器中即可发布。\n\n"
            f"---\n\n"
            f"以下是生成的 HTML 文章内容预览:\n\n{article_html[:2000]}...\n"
        )

    def _markdown_to_wechat_html(self, md_text: str) -> str:
        """简易 Markdown → 微信公众号 HTML 转换器（内联样式）."""
        lines = md_text.split("\n")
        html_parts: list[str] = []
        in_list = False

        for line in lines:
            stripped = line.strip()

            if not stripped:
                if in_list:
                    html_parts.append("</ul>")
                    in_list = False
                html_parts.append("")
                continue

            # 标题
            if stripped.startswith("#### "):
                text = stripped[5:]
                html_parts.append(
                    f'<h4 style="font-size: 14px; color: #7c3aed; margin: 16px 0 8px 0; font-weight: 600;">{self._inline_format(text)}</h4>'
                )
            elif stripped.startswith("### "):
                text = stripped[4:]
                html_parts.append(
                    f'<h3 style="font-size: 16px; color: #5a67d8; margin: 20px 0 12px 0; padding-left: 12px; border-left: 3px solid #667eea; font-weight: 700;">{self._inline_format(text)}</h3>'
                )
            elif stripped.startswith("## "):
                text = stripped[3:]
                html_parts.append(
                    f'<h2 style="font-size: 18px; color: #667eea; margin: 28px 0 16px 0; padding-bottom: 8px; border-bottom: 2px solid #667eea; font-weight: 700;">{self._inline_format(text)}</h2>'
                )
            elif stripped.startswith("# "):
                text = stripped[2:]
                html_parts.append(
                    f'<h1 style="font-size: 22px; color: #4c51bf; margin: 32px 0 16px 0; font-weight: 700; text-align: center;">{self._inline_format(text)}</h1>'
                )
            # 分隔线
            elif stripped in ("---", "***", "___"):
                html_parts.append(
                    '<hr style="border: none; border-top: 1px solid #e5e5e5; margin: 24px 0;">'
                )
            # 列表项
            elif stripped.startswith("- ") or stripped.startswith("* "):
                if not in_list:
                    html_parts.append('<ul style="padding-left: 20px; margin: 8px 0;">')
                    in_list = True
                text = stripped[2:]
                html_parts.append(
                    f'<li style="font-size: 14px; color: #444; margin: 4px 0; line-height: 1.8;">{self._inline_format(text)}</li>'
                )
            # 有序列表
            elif len(stripped) > 2 and stripped[0].isdigit() and ". " in stripped[:4]:
                idx = stripped.index(". ")
                text = stripped[idx + 2 :]
                num = stripped[:idx]
                html_parts.append(
                    f'<p style="font-size: 14px; color: #444; margin: 4px 0; padding-left: 4px; line-height: 1.8;">'
                    f'<span style="color: #667eea; font-weight: 700;">{num}.</span> {self._inline_format(text)}</p>'
                )
            # 普通段落
            else:
                html_parts.append(
                    f'<p style="font-size: 15px; color: #333; margin: 12px 0; line-height: 1.8; text-align: justify;">{self._inline_format(stripped)}</p>'
                )

        if in_list:
            html_parts.append("</ul>")

        return "\n".join(html_parts)

    def _inline_format(self, text: str) -> str:
        """处理内联格式: 加粗、斜体、行内代码、链接."""
        import re

        # 链接 [text](url)
        text = re.sub(
            r'\[([^\]]+)\]\(([^)]+)\)',
            r'<a href="\2" style="color: #667eea; text-decoration: none; font-weight: 500;">\1</a>',
            text,
        )
        # 加粗 **text**
        text = re.sub(
            r'\*\*([^*]+)\*\*',
            r'<strong style="color: #333;">\1</strong>',
            text,
        )
        # 斜体 *text*
        text = re.sub(
            r'\*([^*]+)\*',
            r'<em>\1</em>',
            text,
        )
        # 行内代码 `code`
        text = re.sub(
            r'`([^`]+)`',
            r'<code style="background: #f5f5f5; padding: 2px 6px; border-radius: 3px; font-size: 13px; color: #e74c3c;">\1</code>',
            text,
        )

        return text
