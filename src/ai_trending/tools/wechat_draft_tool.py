"""WeChat Draft Tool — 将报告推送到微信公众号草稿箱."""

import io
import os
import re
from datetime import datetime
from typing import Type

from crewai.tools import BaseTool
from pydantic import BaseModel, Field

from ai_trending.logger import get_logger
from ai_trending.retry import safe_request

log = get_logger("wechat_draft_tool")

# 微信公众号 API 基础地址
WECHAT_API_BASE = "https://api.weixin.qq.com/cgi-bin"


class WeChatDraftInput(BaseModel):
    """Input schema for WeChatDraftTool."""

    content: str = Field(
        ...,
        description="要发布到微信公众号草稿箱的 HTML 文章内容",
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
        description="文章摘要，留空则自动截取前 120 字",
    )


class WeChatDraftTool(BaseTool):
    """将 HTML 文章推送到微信公众号草稿箱.

    需要设置以下环境变量:
      WECHAT_APP_ID          — 公众号 AppID
      WECHAT_APP_SECRET      — 公众号 AppSecret
      WECHAT_THUMB_MEDIA_ID  — 封面图素材 media_id（优先使用）
                               或通过 WECHAT_THUMB_IMAGE_URL 自动上传获取

    获取 media_id 的两种方式:
      方式一（推荐）: 设置 WECHAT_THUMB_MEDIA_ID 为已上传素材的 media_id
        - 登录公众号后台 → 素材管理 → 图片 → 上传图片 → 复制 media_id
        - 或通过 API 上传: POST /material/add_material?type=image
      方式二（自动）: 设置 WECHAT_THUMB_IMAGE_URL 为图片 URL
        - 工具会自动下载图片并上传到微信素材库，获取 media_id
        - 注意: 每次上传会消耗素材库配额（永久素材上限 5000 个）
    """

    name: str = "wechat_draft_tool"
    description: str = (
        "将 AI 趋势报告推送到微信公众号草稿箱。"
        "需要设置 WECHAT_APP_ID、WECHAT_APP_SECRET 环境变量。"
        "封面图通过 WECHAT_THUMB_MEDIA_ID（直接指定）或 WECHAT_THUMB_IMAGE_URL（自动上传）配置。"
        "成功后返回草稿的 media_id，可在公众号后台查看并发布。"
    )
    args_schema: Type[BaseModel] = WeChatDraftInput

    def _run(
        self,
        content: str,
        title: str = "",
        author: str = "AI Trending Bot",
        digest: str = "",
    ) -> str:
        """推送文章到微信公众号草稿箱."""
        app_id = os.environ.get("WECHAT_APP_ID", "")
        app_secret = os.environ.get("WECHAT_APP_SECRET", "")

        if not app_id or not app_secret:
            return (
                "⚠️ 未设置微信公众号环境变量，跳过草稿箱发布。\n"
                "请设置 WECHAT_APP_ID 和 WECHAT_APP_SECRET 后重试。"
            )

        today = datetime.now().strftime("%Y-%m-%d")
        if not title:
            title = f"🔥 AI 日报 | {today} 最热 AI 开源项目与行业新闻"

        if not digest:
            plain = re.sub(r"<[^>]+>", "", content)
            digest = plain.strip()[:120]

        # Step 1: 获取 access_token
        access_token = self._get_access_token(app_id, app_secret)
        if not access_token:
            return "❌ 获取微信 access_token 失败，请检查 AppID 和 AppSecret 是否正确。"

        # Step 2: 确保有有效的 thumb_media_id
        thumb_media_id = self._resolve_thumb_media_id(access_token)
        if not thumb_media_id:
            return (
                "❌ 无法获取封面图 media_id，请通过以下任一方式配置:\n"
                "  方式一: 设置 WECHAT_THUMB_MEDIA_ID=<已上传素材的media_id>\n"
                "  方式二: 设置 WECHAT_THUMB_IMAGE_URL=<图片URL> (工具自动上传)\n"
                "  获取 media_id: 登录公众号后台 → 素材管理 → 图片 → 上传后复制 media_id"
            )

        # Step 3: 添加草稿
        media_id = self._add_draft(access_token, title, author, digest, content, thumb_media_id)
        if not media_id:
            return "❌ 推送到微信草稿箱失败，请查看日志获取详细错误信息。"

        log.info(f"✅ 文章已推送到微信草稿箱，media_id={media_id}")
        return (
            f"✅ 文章已成功推送到微信公众号草稿箱！\n"
            f"- **标题**: {title}\n"
            f"- **作者**: {author}\n"
            f"- **media_id**: {media_id}\n"
            f"- **下一步**: 登录微信公众号后台 → 草稿箱，找到该文章后点击发布即可。\n"
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
          1. 环境变量 WECHAT_THUMB_MEDIA_ID（直接使用，最快）
          2. 环境变量 WECHAT_THUMB_IMAGE_URL（自动下载并上传到素材库）
        """
        # 优先使用已配置的 media_id
        media_id = os.environ.get("WECHAT_THUMB_MEDIA_ID", "").strip()
        if media_id:
            log.info(f"使用已配置的封面图 media_id: {media_id[:20]}...")
            return media_id

        # 尝试从 URL 自动上传
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
        import requests as req

        # 下载图片
        try:
            img_resp = req.get(image_url, timeout=30, stream=True)
            img_resp.raise_for_status()
            img_data = img_resp.content
        except Exception as e:
            log.error(f"下载封面图失败: {e}")
            return ""

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

        # 上传到微信永久素材库
        try:
            upload_resp = req.post(
                f"{WECHAT_API_BASE}/material/add_material",
                params={"access_token": access_token, "type": "image"},
                files={"media": (f"cover.{ext}", io.BytesIO(img_data), mime)},
                timeout=60,
            )
            upload_resp.raise_for_status()
            data = upload_resp.json()
        except Exception as e:
            log.error(f"上传封面图到微信素材库失败: {e}")
            return ""

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
        """调用草稿箱接口，返回 media_id."""
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
