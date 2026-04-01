"""crew/new_collect — Pydantic 数据模型。

定义新闻采集层的增强数据模型，统一上游采集格式，
所有新增字段均有默认值，向后兼容现有下游消费方。
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class RichNewsData(BaseModel):
    """增强版新闻数据，包含正文摘要。

    统一 Hacker News、Reddit、newsdata.io、知乎热榜等多源新闻的数据格式，
    兼容现有 dict 格式的下游消费（所有字段名与 fetchers.py 输出的 dict key 一致）。
    """

    # --- 基础信息（与 fetchers.py 输出的 dict key 对齐）---
    title: str = Field(description="新闻标题")
    url: str = Field(default="", description="新闻链接 URL")
    score: int = Field(default=0, description="热度评分，用于排序")
    source: str = Field(
        default="",
        description="来源名称，如 'Hacker News'、'Reddit r/MachineLearning'、'知乎热榜'",
    )
    summary: str = Field(
        default="",
        description="原始摘要，来自 API 返回或 RSS 描述，不超过 300 字",
    )
    time: str = Field(
        default="",
        description="发布时间，格式 YYYY-MM-DD，无法获取时为空字符串",
    )

    # --- 增强信息（来自 TASK-003 正文提取）---
    content_excerpt: str = Field(
        default="",
        description="从原文 URL 提取的正文前 300 字符摘要，特别用于补充 HN 等无摘要来源",
    )

    @classmethod
    def from_dict(cls, data: dict) -> RichNewsData:
        """从 fetchers.py 输出的 dict 构建 RichNewsData。

        自动映射所有已知字段，忽略未知 key。
        对值为 None 的字符串字段自动回退为空字符串。
        """
        return cls(
            title=data.get("title") or "",
            url=data.get("url") or "",
            score=data.get("score") or 0,
            source=data.get("source") or "",
            summary=data.get("summary") or "",
            time=data.get("time") or "",
            content_excerpt=data.get("content_excerpt") or "",
        )
