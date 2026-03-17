"""GitHub Publish Tool — 将生成的报告推送到 GitHub 仓库."""

import os
import base64
from datetime import datetime
from typing import Type

from crewai.tools import BaseTool
from pydantic import BaseModel, Field

from ai_trending.logger import get_logger
from ai_trending.retry import safe_request

log = get_logger("publish_tool")


class GitHubPublishInput(BaseModel):
    """Input schema for GitHubPublishTool."""

    content: str = Field(
        ...,
        description="要推送到 GitHub 的 Markdown 报告内容",
    )
    filename: str = Field(
        default="",
        description="文件名（不含路径），留空则自动使用日期命名，例如 '2026-03-16.md'",
    )
    commit_message: str = Field(
        default="",
        description="Git commit 信息，留空则自动生成",
    )


class GitHubPublishTool(BaseTool):
    """将 Markdown 报告通过 GitHub API 推送到指定仓库."""

    name: str = "github_publish_tool"
    description: str = (
        "将生成的 AI 趋势报告推送到 GitHub 仓库。"
        "需要设置 GITHUB_TOKEN 和 GITHUB_REPORT_REPO 环境变量。"
        "报告会保存到仓库的 reports/ 目录下。"
    )
    args_schema: Type[BaseModel] = GitHubPublishInput

    def _run(
        self,
        content: str,
        filename: str = "",
        commit_message: str = "",
    ) -> str:
        """推送报告到 GitHub."""
        token = os.environ.get("GITHUB_TOKEN", "")
        repo = os.environ.get("GITHUB_REPORT_REPO", "")

        if not token:
            return self._save_locally(content, filename, "未设置 GITHUB_TOKEN 环境变量，报告已保存到本地")

        if not repo:
            return self._save_locally(content, filename, "未设置 GITHUB_REPORT_REPO 环境变量，报告已保存到本地")

        today = datetime.now().strftime("%Y-%m-%d")
        if not filename:
            filename = f"{today}.md"

        file_path = f"reports/{filename}"

        if not commit_message:
            commit_message = f"📊 AI Trending Report - {today}"

        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
        }

        # 检查文件是否已存在（需要 sha 来更新）
        sha = None
        check_resp = safe_request(
            "GET",
            f"https://api.github.com/repos/{repo}/contents/{file_path}",
            headers=headers,
            timeout=15,
            max_retries=2,
            operation_name="GitHub检查文件",
        )
        if check_resp is not None and check_resp.status_code == 200:
            sha = check_resp.json().get("sha")

        # 创建或更新文件
        payload = {
            "message": commit_message,
            "content": base64.b64encode(content.encode("utf-8")).decode("utf-8"),
        }
        if sha:
            payload["sha"] = sha

        resp = safe_request(
            "PUT",
            f"https://api.github.com/repos/{repo}/contents/{file_path}",
            headers=headers,
            json=payload,
            timeout=30,
            max_retries=3,
            operation_name="GitHub推送报告",
        )

        if resp is None:
            return self._save_locally(
                content, filename, "推送到 GitHub 失败（重试耗尽），报告已保存到本地"
            )

        result = resp.json()
        html_url = result.get("content", {}).get("html_url", "")
        log.info(f"报告已推送到 GitHub: {html_url}")
        return (
            f"✅ 报告已成功推送到 GitHub！\n"
            f"- **仓库**: {repo}\n"
            f"- **文件路径**: {file_path}\n"
            f"- **链接**: {html_url}\n"
            f"- **Commit**: {commit_message}\n"
        )

    def _save_locally(self, content: str, filename: str, reason: str) -> str:
        """降级方案：保存到本地文件."""
        today = datetime.now().strftime("%Y-%m-%d")
        if not filename:
            filename = f"{today}.md"

        # 保存到项目的 reports 目录
        reports_dir = os.path.join(os.getcwd(), "reports")
        os.makedirs(reports_dir, exist_ok=True)
        local_path = os.path.join(reports_dir, filename)

        with open(local_path, "w", encoding="utf-8") as f:
            f.write(content)

        return (
            f"⚠️ {reason}\n"
            f"- **本地路径**: {local_path}\n"
            f"- **文件名**: {filename}\n"
            f"请稍后手动推送到 GitHub，或配置好环境变量后重新运行。"
        )
