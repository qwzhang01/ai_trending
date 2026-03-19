"""WeChat Article Tool — 将报告转换为微信公众号可发布的 HTML 格式文章."""

import os
import re
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


# ── 微信公众号 HTML 模板 ──────────────────────────────────────────
WECHAT_HTML_TEMPLATE = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
</head>
<body style="margin: 0; padding: 0; background: #f5f5f5;">
<div style="max-width: 680px; margin: 0 auto; padding: 24px 16px; font-family: -apple-system, BlinkMacSystemFont, 'PingFang SC', 'Hiragino Sans GB', 'Microsoft YaHei', sans-serif; color: #2c2c2c; line-height: 1.75; background: #fff;">

<!-- 头部 -->
<div style="padding: 28px 24px; margin: -24px -16px 28px -16px; background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%); text-align: center;">
    <p style="margin: 0 0 4px 0; font-size: 12px; color: rgba(255,255,255,0.5); letter-spacing: 4px; text-transform: uppercase;">DAILY REPORT</p>
    <h1 style="color: #fff; font-size: 20px; margin: 0 0 10px 0; font-weight: 600; letter-spacing: 1px;">{title}</h1>
    <p style="color: rgba(255,255,255,0.6); font-size: 12px; margin: 0;">{date} · {author}</p>
</div>

<!-- 正文 -->
{body}

<!-- 尾部 -->
<div style="margin-top: 36px; padding: 20px 0 0 0; border-top: 1px solid #eee; text-align: center;">
    <p style="font-size: 12px; color: #bbb; margin: 0 0 4px 0;">— END —</p>
    <p style="font-size: 11px; color: #ccc; margin: 0;">由 AI Trending Bot 自动生成 · {date}</p>
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
            title = f"AI 日报 | {today}"

        body_html = self._markdown_to_wechat_html(content)

        article_html = WECHAT_HTML_TEMPLATE.format(
            title=title,
            date=today,
            author=author,
            body=body_html,
        )

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

    # ── Markdown → HTML 转换 ─────────────────────────────────────
    def _markdown_to_wechat_html(self, md_text: str) -> str:
        """将 Markdown 转换为带内联样式的微信公众号 HTML."""
        lines = md_text.split("\n")
        html_parts: list[str] = []
        in_list = False
        in_ul = False
        in_blockquote = False
        # 跟踪是否在 h3 (项目卡片) 区域
        in_card = False

        i = 0
        while i < len(lines):
            stripped = lines[i].strip()

            # ── 空行 ──
            if not stripped:
                if in_ul:
                    html_parts.append("</ul>")
                    in_ul = False
                if in_blockquote:
                    html_parts.append("</div>")
                    in_blockquote = False
                if in_card:
                    html_parts.append("</div>")  # 关闭卡片
                    in_card = False
                i += 1
                continue

            # ── 引用块 > ──
            if stripped.startswith("> "):
                quote_text = stripped[2:]
                if not in_blockquote:
                    # 关闭之前的卡片标题区域（如果有）
                    html_parts.append(
                        '<div style="background: #f8f9fb; border-left: 3px solid #e0a84c; '
                        'padding: 10px 14px; border-radius: 0 6px 6px 0; margin: 8px 0 12px 0;">'
                    )
                    in_blockquote = True
                html_parts.append(
                    f'<p style="margin: 0; font-size: 13px; color: #666; line-height: 1.7;">'
                    f'{self._inline_format(quote_text)}</p>'
                )
                i += 1
                continue

            # 关闭引用块
            if in_blockquote:
                html_parts.append("</div>")
                in_blockquote = False

            # ── 标题 ──
            if stripped.startswith("# ") and not stripped.startswith("## "):
                # h1 — 报告主标题，在 HTML 模板头部已有，此处跳过
                i += 1
                continue

            if stripped.startswith("## "):
                if in_card:
                    html_parts.append("</div>")
                    in_card = False
                text = stripped[3:]
                html_parts.append(
                    f'<h2 style="font-size: 17px; color: #1a1a2e; margin: 32px 0 16px 0; '
                    f'padding: 8px 0 8px 14px; border-left: 4px solid #0f3460; '
                    f'font-weight: 700; letter-spacing: 0.5px;">'
                    f'{self._inline_format(text)}</h2>'
                )
                i += 1
                continue

            if stripped.startswith("### "):
                if in_card:
                    html_parts.append("</div>")
                text = stripped[4:]
                # 项目卡片样式
                html_parts.append(
                    f'<div style="background: #fafbfc; border: 1px solid #eaecef; '
                    f'border-radius: 8px; padding: 16px; margin: 12px 0 4px 0;">'
                    f'<h3 style="font-size: 15px; color: #1a1a2e; margin: 0 0 6px 0; '
                    f'font-weight: 700;">{self._inline_format(text)}</h3>'
                )
                in_card = True
                i += 1
                continue

            if stripped.startswith("#### "):
                text = stripped[5:]
                html_parts.append(
                    f'<h4 style="font-size: 14px; color: #555; margin: 16px 0 8px 0; '
                    f'font-weight: 600;">{self._inline_format(text)}</h4>'
                )
                i += 1
                continue

            # ── 分隔线 ──
            if stripped in ("---", "***", "___"):
                html_parts.append(
                    '<hr style="border: none; height: 1px; background: linear-gradient(90deg, transparent, #ddd, transparent); margin: 28px 0;">'
                )
                i += 1
                continue

            # ── 无序列表 ──
            if stripped.startswith("- ") or stripped.startswith("* "):
                if not in_ul:
                    html_parts.append(
                        '<ul style="padding-left: 18px; margin: 8px 0;">'
                    )
                    in_ul = True
                text = stripped[2:]
                html_parts.append(
                    f'<li style="font-size: 14px; color: #333; margin: 6px 0; '
                    f'line-height: 1.75;">{self._inline_format(text)}</li>'
                )
                i += 1
                continue

            if in_ul:
                html_parts.append("</ul>")
                in_ul = False

            # ── Markdown 表格 ──
            # 检测表格：当前行是表头，下一行是分隔线 |---|
            if stripped.startswith("|") and stripped.endswith("|"):
                # 判断下一行是否是分隔线
                next_line = lines[i + 1].strip() if i + 1 < len(lines) else ""
                is_separator = bool(re.match(r'^\|[-| :]+\|$', next_line))
                if is_separator:
                    # 收集整个表格
                    table_lines = [stripped]
                    i += 1  # 跳过分隔线
                    i += 1
                    while i < len(lines) and lines[i].strip().startswith("|"):
                        table_lines.append(lines[i].strip())
                        i += 1
                    # 渲染表格
                    html_parts.append(self._render_table(table_lines))
                    continue
                # 不是表格，当普通段落处理（fall through）

            # ── 有序列表 ──
            if len(stripped) > 2 and stripped[0].isdigit() and ". " in stripped[:4]:
                idx = stripped.index(". ")
                text = stripped[idx + 2:]
                num = stripped[:idx]
                html_parts.append(
                    f'<p style="font-size: 14px; color: #333; margin: 6px 0; '
                    f'padding-left: 4px; line-height: 1.75;">'
                    f'<span style="display: inline-block; width: 20px; height: 20px; '
                    f'background: #0f3460; color: #fff; border-radius: 50%; '
                    f'text-align: center; line-height: 20px; font-size: 11px; '
                    f'margin-right: 8px; font-weight: 700; vertical-align: middle;">'
                    f'{num}</span>{self._inline_format(text)}</p>'
                )
                i += 1
                continue

            # ── 普通段落 ──
            # 导读段落（紧跟 h1 后的第一段）特殊处理
            html_parts.append(
                f'<p style="font-size: 14.5px; color: #444; margin: 10px 0; '
                f'line-height: 1.8; text-align: justify;">'
                f'{self._inline_format(stripped)}</p>'
            )
            i += 1

        # 收尾：关闭未关闭的标签
        if in_ul:
            html_parts.append("</ul>")
        if in_blockquote:
            html_parts.append("</div>")
        if in_card:
            html_parts.append("</div>")

        return "\n".join(html_parts)

    # ── 表格渲染 ─────────────────────────────────────────────────
    def _render_table(self, table_lines: list[str]) -> str:
        """将 Markdown 表格行列表渲染为带内联样式的 HTML 表格."""
        if not table_lines:
            return ""

        def parse_row(line: str) -> list[str]:
            # 去掉首尾 |，按 | 分割
            cells = line.strip("|").split("|")
            return [c.strip() for c in cells]

        header_cells = parse_row(table_lines[0])
        data_rows = table_lines[1:]  # 分隔线已在调用处跳过

        th_style = (
            'style="padding: 8px 12px; text-align: left; font-size: 13px; '
            'font-weight: 700; color: #fff; background: #1a1a2e; '
            'border-bottom: 2px solid #0f3460; white-space: nowrap;"'
        )
        td_style_base = (
            'padding: 8px 12px; font-size: 13px; color: #333; '
            'border-bottom: 1px solid #eaecef; vertical-align: top; line-height: 1.6;'
        )

        # 表头
        ths = "".join(f"<th {th_style}>{self._inline_format(c)}</th>" for c in header_cells)
        thead = f"<thead><tr>{ths}</tr></thead>"

        # 数据行
        tbody_rows = []
        for idx, row_line in enumerate(data_rows):
            cells = parse_row(row_line)
            bg = "#fff" if idx % 2 == 0 else "#f8f9fb"
            tds = "".join(
                f'<td style="{td_style_base} background: {bg};">{self._inline_format(c)}</td>'
                for c in cells
            )
            tbody_rows.append(f"<tr>{tds}</tr>")
        tbody = f"<tbody>{''.join(tbody_rows)}</tbody>"

        return (
            '<div style="overflow-x: auto; margin: 16px 0;">'
            '<table style="width: 100%; border-collapse: collapse; '
            'border-radius: 8px; overflow: hidden; '
            'box-shadow: 0 1px 4px rgba(0,0,0,0.08);">'
            f"{thead}{tbody}"
            "</table></div>"
        )

    # ── 内联格式 ─────────────────────────────────────────────────
    def _inline_format(self, text: str) -> str:
        """处理内联格式: 链接、加粗、斜体、行内代码、裸 URL."""
        # Markdown 链接 [text](url)
        text = re.sub(
            r'\[([^\]]+)\]\(([^)]+)\)',
            r'<a href="\2" style="color: #0f3460; text-decoration: none; '
            r'border-bottom: 1px solid rgba(15,52,96,0.3);">\1</a>',
            text,
        )
        # 加粗 **text**
        text = re.sub(
            r'\*\*([^*]+)\*\*',
            r'<strong style="color: #1a1a2e;">\1</strong>',
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
            r'<code style="background: #f3f4f6; padding: 2px 5px; border-radius: 3px; '
            r'font-size: 12.5px; color: #c7254e; font-family: Menlo, Monaco, monospace;">\1</code>',
            text,
        )
        # 裸 URL（不在 href="" 或 >url< 中的）→ 可点击链接
        text = re.sub(
            r'(?<!href=")(?<!">)(https?://[^\s<]+)',
            r'<a href="\1" style="color: #0f3460; text-decoration: none; '
            r'border-bottom: 1px solid rgba(15,52,96,0.3); word-break: break-all; font-size: 12px;">\1</a>',
            text,
        )
        # ⭐ emoji 样式化
        text = text.replace("⭐", '<span style="color: #e0a84c;">⭐</span>')
        # 🔗 链接图标
        text = text.replace("🔗", '<span style="font-size: 13px;">🔗</span>')
        # 标题 emoji 统一用 span 包裹，确保跨平台正常渲染
        for emoji_char in ("🔬", "📰", "📊", "🗞", "🚀", "💡", "🤖", "📈", "🔥", "✅", "⚠️", "❌"):
            text = text.replace(emoji_char, f'<span style="font-style: normal;">{emoji_char}</span>')
        return text
