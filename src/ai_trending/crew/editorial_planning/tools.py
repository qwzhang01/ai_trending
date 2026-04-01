"""crew/editorial_planning/tools.py — 编辑部按需查询工具.

EditorialPlanningCrew 的 Agent 通过这些工具主动获取上下文，
而非被动接收全量推送的数据。遵循 Claude Code 的"按需 Tool 调用"设计模式。

工具说明：
  - get_topic_history: 查询近 N 天覆盖的话题（避免雷同）
  - get_style_guidance: 查询近期风格记忆（避免重复表达）
  - search_prev_reports: 搜索历史日报是否报道过某话题
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

from crewai.tools import BaseTool
from pydantic import BaseModel, Field

from ai_trending.logger import get_logger

log = get_logger("editorial_tools")


# ==================== Tool 输入模型 ====================


class _TopicHistoryInput(BaseModel):
    days: int = Field(
        default=7,
        ge=1,
        le=14,
        description="查询最近 N 天的话题记录，默认 7 天，最多 14 天",
    )


class _StyleGuidanceInput(BaseModel):
    max_items: int = Field(
        default=5,
        ge=1,
        le=10,
        description="返回的好/坏表达模式最大条数，默认 5 条",
    )


class _SearchReportsInput(BaseModel):
    keyword: str = Field(
        description="搜索关键词，如'MCP'、'Claude'、'Agent框架'，检查历史是否报道过"
    )
    days: int = Field(
        default=14,
        ge=1,
        le=30,
        description="搜索最近 N 天的历史日报，默认 14 天",
    )


# ==================== 工厂函数 ====================


def make_topic_history_tool(get_topic_context_fn: Callable[[int], str]) -> BaseTool:
    """工厂函数：创建话题历史查询工具。

    Args:
        get_topic_context_fn: 接收 days 参数，返回话题上下文文本的函数

    Returns:
        BaseTool 实例
    """

    class _TopicHistoryTool(BaseTool):
        name: str = "get_topic_history"
        description: str = (
            "查询最近 N 天覆盖的话题记录，包含头条话题、关键词和今日一句话。"
            "在选题时调用，用于避免连续多天报道相同话题。"
            "返回 JSON 格式的话题列表和 Kill List。"
        )
        args_schema: type[BaseModel] = _TopicHistoryInput

        def _run(self, days: int = 7) -> str:
            try:
                context = get_topic_context_fn(days)
                if not context or "无近期" in context:
                    return json.dumps(
                        {"topic_records": [], "kill_list": [], "message": "无近期话题记录"},
                        ensure_ascii=False,
                    )
                return json.dumps(
                    {"topic_context": context, "days": days},
                    ensure_ascii=False,
                )
            except Exception as e:
                log.warning(f"[get_topic_history] 查询失败: {e}")
                return json.dumps({"error": str(e), "topic_records": []}, ensure_ascii=False)

    return _TopicHistoryTool()


def make_style_guidance_tool(get_style_guidance_fn: Callable[[], str]) -> BaseTool:
    """工厂函数：创建风格记忆查询工具。

    Args:
        get_style_guidance_fn: 返回风格指导文本的函数（无参数）

    Returns:
        BaseTool 实例
    """

    class _StyleGuidanceTool(BaseTool):
        name: str = "get_style_guidance"
        description: str = (
            "查询近期风格记忆，包含效果好的表达模式和应避免的重复表达。"
            "在决定今日一句话和写作角度时调用，用于保持风格多样性。"
        )
        args_schema: type[BaseModel] = _StyleGuidanceInput

        def _run(self, max_items: int = 5) -> str:
            try:
                guidance = get_style_guidance_fn()
                if not guidance or "无风格记忆" in guidance:
                    return json.dumps(
                        {"guidance": "无风格记忆记录", "good_patterns": [], "bad_patterns": []},
                        ensure_ascii=False,
                    )
                return json.dumps({"guidance": guidance}, ensure_ascii=False)
            except Exception as e:
                log.warning(f"[get_style_guidance] 查询失败: {e}")
                return json.dumps({"error": str(e), "guidance": ""}, ensure_ascii=False)

    return _StyleGuidanceTool()


def make_search_prev_reports_tool(reports_dir: Path) -> BaseTool:
    """工厂函数：创建历史日报搜索工具。

    Args:
        reports_dir: 历史日报存储目录（如 reports/）

    Returns:
        BaseTool 实例
    """

    class _SearchReportsTool(BaseTool):
        name: str = "search_prev_reports"
        description: str = (
            "搜索最近 N 天的历史日报，检查某个话题/项目是否已被深度报道过。"
            "返回匹配的日期和相关段落摘要。用于决定是否将某话题纳入本期头条。"
        )
        args_schema: type[BaseModel] = _SearchReportsInput

        def _run(self, keyword: str, days: int = 14) -> str:
            try:
                from datetime import datetime, timedelta

                keyword_lower = keyword.lower()
                matches: list[dict] = []
                today = datetime.now()

                for i in range(1, days + 1):
                    date_str = (today - timedelta(days=i)).strftime("%Y-%m-%d")
                    report_file = reports_dir / f"{date_str}.md"
                    if not report_file.exists():
                        continue

                    content = report_file.read_text(encoding="utf-8")
                    if keyword_lower not in content.lower():
                        continue

                    # 提取含关键词的段落（前后 100 字）
                    idx = content.lower().find(keyword_lower)
                    start = max(0, idx - 100)
                    end = min(len(content), idx + len(keyword) + 100)
                    excerpt = content[start:end].replace("\n", " ").strip()

                    matches.append({"date": date_str, "excerpt": excerpt})

                if not matches:
                    return json.dumps(
                        {
                            "keyword": keyword,
                            "found": False,
                            "message": f"最近 {days} 天内未找到关于「{keyword}」的报道",
                        },
                        ensure_ascii=False,
                    )
                return json.dumps(
                    {
                        "keyword": keyword,
                        "found": True,
                        "match_count": len(matches),
                        "matches": matches[:3],  # 最多返回 3 条
                        "message": f"最近 {days} 天内找到 {len(matches)} 篇关于「{keyword}」的报道",
                    },
                    ensure_ascii=False,
                )
            except Exception as e:
                log.warning(f"[search_prev_reports] 搜索失败: {e}")
                return json.dumps({"error": str(e), "found": False}, ensure_ascii=False)

    return _SearchReportsTool()
