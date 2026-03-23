"""WeChat Publish Tool — 将 Markdown 报告转换为微信公众号 HTML 并推送到草稿箱.

职责：
  1. 将 Markdown 报告转换为带内联样式的微信公众号 HTML（格式转换，不修改内容）
  2. 保存 HTML 文件到本地 output/ 目录
  3. 若配置了微信公众号环境变量，则自动推送到草稿箱

需要设置以下环境变量（推送草稿箱时必填）:
  WECHAT_APP_ID          — 公众号 AppID
  WECHAT_APP_SECRET      — 公众号 AppSecret
  WECHAT_THUMB_MEDIA_ID  — 封面图素材 media_id（优先使用）
                           或通过 WECHAT_THUMB_IMAGE_URL 自动上传获取
"""

import io
import os
import re
from datetime import datetime
from typing import Type

import markdown
from bs4 import BeautifulSoup
from crewai.tools import BaseTool
from pydantic import BaseModel, Field

from ai_trending.config import load_config
from ai_trending.logger import get_logger
from ai_trending.retry import safe_request

log = get_logger("wechat_publish")

# 微信公众号 API 基础地址
WECHAT_API_BASE = "https://api.weixin.qq.com/cgi-bin"

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


class WeChatPublishInput(BaseModel):
    """WeChatPublishTool 的输入参数."""

    content: str = Field(
        ...,
        description="待发布的 Markdown 格式日报内容",
    )
    title: str = Field(
        default="",
        description="文章标题，留空则自动生成",
    )
    author: str = Field(
        default="AI Trending Bot",
        description="文章作者名",
    )
    digest: str = Field(
        default="",
        description="文章摘要，留空则自动截取正文前 120 字",
    )


class WeChatPublishTool(BaseTool):
    """将 Markdown 日报转换为微信公众号 HTML 并推送到草稿箱.

    流程：
      1. Markdown → 带内联样式的微信 HTML（格式转换，不修改内容）
      2. 保存 HTML 到本地 output/wechat_{date}.html
      3. 若配置了 WECHAT_APP_ID / WECHAT_APP_SECRET，则推送到草稿箱
         未配置时仅保存本地文件，返回 ⚠️ 提示

    封面图配置（推送草稿箱时必须二选一）:
      方式一（推荐）: 设置 WECHAT_THUMB_MEDIA_ID 为已上传素材的 media_id
      方式二（自动）: 设置 WECHAT_THUMB_IMAGE_URL，工具自动下载并上传到素材库
    """

    name: str = "wechat_publish_tool"
    description: str = (
        "将 AI 趋势日报（Markdown 格式）转换为微信公众号 HTML 并推送到草稿箱。"
        "需要设置 WECHAT_APP_ID、WECHAT_APP_SECRET 环境变量。"
        "封面图通过 WECHAT_THUMB_MEDIA_ID（直接指定）或 WECHAT_THUMB_IMAGE_URL（自动上传）配置。"
        "未配置微信环境变量时，仅保存本地 HTML 文件。"
    )
    args_schema: Type[BaseModel] = WeChatPublishInput

    def _run(
        self,
        content: str,
        title: str = "",
        author: str = "AI Trending Bot",
        digest: str = "",
    ) -> str:
        """执行转换 + 发布，返回结果描述字符串."""
        today = datetime.now().strftime("%Y-%m-%d")

        if not title:
            title = f"🔥 AI 日报 | {today} 最热 AI 开源项目与行业新闻"

        # Step 1: Markdown → 微信 HTML
        body_html = self._markdown_to_wechat_html(content)
        article_html = WECHAT_HTML_TEMPLATE.format(
            title=title,
            date=today,
            author=author,
            body=body_html,
        )

        # Step 2: 保存本地 HTML 文件
        html_path = self._save_locally(article_html, today)

        # Step 3: 推送到微信草稿箱（若已配置）
        cfg = load_config()
        app_id = cfg.wechat.app_id
        app_secret = cfg.wechat.app_secret

        if not app_id or not app_secret:
            return (
                f"⚠️ 未设置微信公众号环境变量，已跳过草稿箱发布。\n"
                f"- **本地文件**: {html_path}\n"
                f"- **配置方式**: 设置 WECHAT_APP_ID 和 WECHAT_APP_SECRET 后重试。"
            )

        return self._publish_to_draft(
            article_html=article_html,
            title=title,
            author=author,
            digest=digest,
            html_path=html_path,
            app_id=app_id,
            app_secret=app_secret,
        )

    # ── 本地保存 ─────────────────────────────────────────────────

    def _save_locally(self, article_html: str, today: str) -> str:
        """将 HTML 保存到本地 output/ 目录，返回文件路径."""
        output_dir = os.path.join(os.getcwd(), "output")
        os.makedirs(output_dir, exist_ok=True)
        html_path = os.path.join(output_dir, f"wechat_{today}.html")
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(article_html)
        log.info(f"[wechat_publish] HTML 已保存到本地: {html_path}")
        return html_path

    # ── 微信草稿箱发布 ───────────────────────────────────────────

    def _publish_to_draft(
        self,
        article_html: str,
        title: str,
        author: str,
        digest: str,
        html_path: str,
        app_id: str,
        app_secret: str,
    ) -> str:
        """推送 HTML 到微信草稿箱，返回结果描述字符串."""
        # 自动生成摘要
        if not digest:
            plain = re.sub(r"<[^>]+>", "", article_html)
            digest = plain.strip()[:120]

        # 获取 access_token
        access_token = self._get_access_token(app_id, app_secret)
        if not access_token:
            return (
                f"❌ 获取微信 access_token 失败，请检查 AppID 和 AppSecret 是否正确。\n"
                f"- **本地文件**: {html_path}"
            )

        # 获取封面图 media_id
        thumb_media_id = self._resolve_thumb_media_id(access_token)
        if not thumb_media_id:
            return (
                f"❌ 无法获取封面图 media_id，请通过以下任一方式配置:\n"
                f"  方式一: 设置 WECHAT_THUMB_MEDIA_ID=<已上传素材的media_id>\n"
                f"  方式二: 设置 WECHAT_THUMB_IMAGE_URL=<图片URL> (工具自动上传)\n"
                f"- **本地文件**: {html_path}"
            )

        # 添加草稿
        media_id = self._add_draft(access_token, title, author, digest, article_html, thumb_media_id)
        if not media_id:
            return (
                f"❌ 推送到微信草稿箱失败，请查看日志获取详细错误信息。\n"
                f"- **本地文件**: {html_path}"
            )

        log.info(f"[wechat_publish] 文章已推送到微信草稿箱，media_id={media_id}")
        return (
            f"✅ 文章已成功推送到微信公众号草稿箱！\n"
            f"- **标题**: {title}\n"
            f"- **作者**: {author}\n"
            f"- **media_id**: {media_id}\n"
            f"- **本地文件**: {html_path}\n"
            f"- **下一步**: 登录微信公众号后台 → 草稿箱，找到该文章后点击发布即可。"
        )

    def _get_access_token(self, app_id: str, app_secret: str) -> str:
        """获取微信公众号 access_token."""
        resp = safe_request(
            "GET",
            f"{WECHAT_API_BASE}/token",
            params={
                "grant_type": "client_credential",
                "appid": app_id,
                "secret": app_secret,
            },
            timeout=15,
            max_retries=2,
            operation_name="微信获取access_token",
        )
        if resp is None:
            return ""

        data = resp.json()
        if "errcode" in data and data["errcode"] != 0:
            log.error(f"获取 access_token 失败: errcode={data.get('errcode')}, errmsg={data.get('errmsg')}")
            return ""

        token = data.get("access_token", "")
        log.info(f"微信 access_token 获取成功，有效期 {data.get('expires_in', 7200)}s")
        return token

    def _resolve_thumb_media_id(self, access_token: str) -> str:
        """解析封面图 media_id.

        优先级:
          1. 配置 WECHAT_THUMB_MEDIA_ID（直接使用，最快）
          2. 配置 WECHAT_THUMB_IMAGE_URL（自动下载并上传到素材库）
        """
        cfg = load_config()
        media_id = cfg.wechat.thumb_media_id.strip()
        if media_id:
            log.info(f"使用已配置的封面图 media_id: {media_id[:20]}...")
            return media_id

        image_url = os.environ.get("WECHAT_THUMB_IMAGE_URL", "").strip()
        if image_url:
            log.info(f"WECHAT_THUMB_MEDIA_ID 未设置，尝试从 URL 上传封面图: {image_url[:60]}...")
            uploaded_id = self._upload_thumb_from_url(access_token, image_url)
            if uploaded_id:
                log.info(
                    f"封面图上传成功，media_id={uploaded_id}。"
                    f"建议将此 media_id 保存到环境变量 WECHAT_THUMB_MEDIA_ID 以避免重复上传。"
                )
                return uploaded_id
            log.error("从 URL 上传封面图失败")
            return ""

        log.error(
            "缺少封面图配置。请设置以下任一环境变量:\n"
            "  WECHAT_THUMB_MEDIA_ID — 已上传素材的 media_id\n"
            "  WECHAT_THUMB_IMAGE_URL — 图片 URL（工具自动上传）"
        )
        return ""

    def _upload_thumb_from_url(self, access_token: str, image_url: str) -> str:
        """从图片 URL 下载图片并上传到微信永久素材库.

        微信永久素材接口要求:
          - 图片格式: JPG / PNG（草稿封面图用 type=image，不是 type=thumb）
          - 文件大小: ≤ 10MB
          - 接口: POST /material/add_material?type=image

        注意: type=thumb 仅支持 JPG 且 ≤ 64KB，限制太严格。
        草稿接口的 thumb_media_id 实际上接受 type=image 上传的 media_id。

        Returns:
            上传成功返回 media_id，失败返回空字符串
        """
        # 下载图片（使用 safe_request，统一重试和日志）
        img_resp = safe_request(
            "GET",
            image_url,
            timeout=30,
            max_retries=2,
            operation_name="下载封面图",
        )
        if img_resp is None:
            log.error(f"下载封面图失败: {image_url}")
            return ""

        img_data = img_resp.content
        if len(img_data) > 10 * 1024 * 1024:
            log.error(f"封面图文件过大: {len(img_data) / 1024 / 1024:.1f}MB，微信限制 10MB")
            return ""

        # 根据 Content-Type 或 URL 后缀判断图片格式
        content_type = img_resp.headers.get("Content-Type", "image/jpeg")
        if "png" in content_type or image_url.lower().endswith(".png"):
            ext = "png"
            mime = "image/png"
        else:
            ext = "jpg"
            mime = "image/jpeg"

        log.info(f"封面图下载成功: {len(img_data) / 1024:.1f}KB, 格式={ext}")

        # 上传到微信永久素材库（使用 safe_request）
        upload_resp = safe_request(
            "POST",
            f"{WECHAT_API_BASE}/material/add_material",
            params={"access_token": access_token, "type": "image"},
            files={"media": (f"cover.{ext}", io.BytesIO(img_data), mime)},
            timeout=60,
            max_retries=2,
            operation_name="上传封面图到微信素材库",
        )
        if upload_resp is None:
            log.error("上传封面图到微信素材库失败")
            return ""

        data = upload_resp.json()
        if "errcode" in data and data["errcode"] != 0:
            log.error(
                f"微信素材上传失败: errcode={data.get('errcode')}, errmsg={data.get('errmsg')}\n"
                f"常见原因: 45009=超出每日上传限制, 40001=access_token无效"
            )
            return ""

        media_id = data.get("media_id", "")
        if not media_id:
            log.error(f"微信素材上传响应中无 media_id: {data}")
            return ""

        return media_id

    def _add_draft(
        self,
        access_token: str,
        title: str,
        author: str,
        digest: str,
        content: str,
        thumb_media_id: str,
    ) -> str:
        """调用草稿箱接口，返回草稿 media_id."""
        payload = {
            "articles": [
                {
                    "title": title,
                    "author": author,
                    "digest": digest,
                    "content": content,
                    "content_source_url": "",
                    "thumb_media_id": thumb_media_id,
                    "need_open_comment": 0,
                    "only_fans_can_comment": 0,
                }
            ]
        }

        resp = safe_request(
            "POST",
            f"{WECHAT_API_BASE}/draft/add",
            params={"access_token": access_token},
            json=payload,
            timeout=30,
            max_retries=3,
            operation_name="微信添加草稿",
        )
        if resp is None:
            return ""

        data = resp.json()
        if "errcode" in data and data["errcode"] != 0:
            errcode = data.get("errcode")
            errmsg = data.get("errmsg", "")
            if errcode == 40007:
                log.error(
                    f"添加草稿失败: errcode=40007 (invalid media_id) — {errmsg}\n"
                    f"原因: thumb_media_id={thumb_media_id[:20]}... 无效。\n"
                    f"解决: 通过 API 上传图片获取真实 media_id，不能直接使用图片 URL 中的 hash。\n"
                    f"命令: curl -F 'media=@cover.jpg' "
                    f"'https://api.weixin.qq.com/cgi-bin/material/add_material"
                    f"?access_token=ACCESS_TOKEN&type=image'"
                )
            else:
                log.error(f"添加草稿失败: errcode={errcode}, errmsg={errmsg}")
            return ""

        return data.get("media_id", "")

    # ── Markdown → 微信 HTML 转换 ────────────────────────────────

    # 微信公众号内联样式表（所有样式必须内联，不支持外链 CSS）
    _WECHAT_STYLES: dict[str, str] = {
        "h1": (
            "font-size: 20px; font-weight: 700; color: #1a1a2e; margin: 28px 0 14px 0; "
            "padding: 8px 0 8px 14px; border-left: 4px solid #0f3460; letter-spacing: 0.5px;"
        ),
        "h2": (
            "font-size: 17px; font-weight: 700; color: #1a1a2e; margin: 32px 0 16px 0; "
            "padding: 8px 0 8px 14px; border-left: 4px solid #0f3460; letter-spacing: 0.5px;"
        ),
        "h3": (
            "font-size: 15px; font-weight: 700; color: #1a1a2e; margin: 0 0 6px 0;"
        ),
        "h4": (
            "font-size: 14px; font-weight: 600; color: #555; margin: 16px 0 8px 0;"
        ),
        "p": (
            "font-size: 14.5px; color: #444; margin: 10px 0; line-height: 1.8; text-align: justify;"
        ),
        "ul": "padding-left: 18px; margin: 8px 0;",
        "ol": "padding-left: 18px; margin: 8px 0;",
        "li": "font-size: 14px; color: #333; margin: 6px 0; line-height: 1.75;",
        "blockquote": (
            "background: #f8f9fb; border-left: 3px solid #e0a84c; "
            "padding: 10px 14px; border-radius: 0 6px 6px 0; margin: 8px 0 12px 0;"
        ),
        "code": (
            "background: #f3f4f6; padding: 2px 5px; border-radius: 3px; "
            "font-size: 12.5px; color: #c7254e; font-family: Menlo, Monaco, monospace;"
        ),
        "pre": (
            "background: #f8f8f8; padding: 16px; border-radius: 6px; "
            "overflow-x: auto; font-size: 13px; line-height: 1.6; border: 1px solid #e8e8e8; "
            "margin: 12px 0;"
        ),
        "strong": "font-weight: 700; color: #1a1a2e;",
        "em": "font-style: italic; color: #555;",
        "hr": (
            "border: none; height: 1px; "
            "background: linear-gradient(90deg, transparent, #ddd, transparent); margin: 28px 0;"
        ),
        "table": (
            "width: 100%; border-collapse: collapse; border-radius: 8px; "
            "overflow: hidden; box-shadow: 0 1px 4px rgba(0,0,0,0.08); margin: 16px 0;"
        ),
        "th": (
            "padding: 8px 12px; text-align: left; font-size: 13px; font-weight: 700; "
            "color: #fff; background: #1a1a2e; border-bottom: 2px solid #0f3460; white-space: nowrap;"
        ),
        "td": (
            "padding: 8px 12px; font-size: 13px; color: #333; "
            "border-bottom: 1px solid #eaecef; vertical-align: top; line-height: 1.6;"
        ),
        "a": (
            "color: #0f3460; text-decoration: none; "
            "border-bottom: 1px solid rgba(15,52,96,0.3);"
        ),
    }

    def _markdown_to_wechat_html(self, md_text: str) -> str:
        """将 Markdown 转换为带内联样式的微信公众号 HTML.

        使用 markdown 库解析为标准 HTML，再用 BeautifulSoup 遍历节点注入内联样式。
        支持：标题、段落、列表、代码块、引用块、表格、分隔线、加粗/斜体/行内代码。
        """
        # Step 1: Markdown → 原始 HTML（启用 tables / fenced_code / nl2br 扩展）
        raw_html = markdown.markdown(
            md_text,
            extensions=["tables", "fenced_code", "nl2br"],
        )

        # Step 2: 用 BeautifulSoup 遍历节点，注入内联样式
        soup = BeautifulSoup(raw_html, "html.parser")

        for tag_name, style in self._WECHAT_STYLES.items():
            for tag in soup.find_all(tag_name):
                existing = tag.get("style", "")
                tag["style"] = (existing + " " + style).strip() if existing else style

        # Step 3: h3 包裹卡片容器（保持原有的卡片视觉效果）
        for h3 in soup.find_all("h3"):
            card_div = soup.new_tag(
                "div",
                style=(
                    "background: #fafbfc; border: 1px solid #eaecef; "
                    "border-radius: 8px; padding: 16px; margin: 12px 0 4px 0;"
                ),
            )
            # 将 h3 及其后续兄弟节点（直到下一个 h2/h3/hr）移入卡片
            h3.insert_before(card_div)
            card_div.append(h3.extract())

        # Step 4: 移除 h1（报告主标题已在 HTML 模板头部渲染）
        for h1 in soup.find_all("h1"):
            h1.decompose()

        # Step 5: 微信不支持外链，去掉 <a> 标签保留文字
        for a_tag in soup.find_all("a"):
            a_tag.unwrap()

        # Step 6: 表格行斑马纹（偶数行加浅灰背景）
        for table in soup.find_all("table"):
            table["style"] = self._WECHAT_STYLES["table"]
            tbody = table.find("tbody")
            if tbody:
                for idx, tr in enumerate(tbody.find_all("tr")):
                    bg = "#fff" if idx % 2 == 0 else "#f8f9fb"
                    for td in tr.find_all("td"):
                        existing = td.get("style", "")
                        td["style"] = existing + f" background: {bg};"

        return str(soup)
