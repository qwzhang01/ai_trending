"""ReportWritingCrew 数据模型 — 日报输出结构化定义。"""

from __future__ import annotations

from pydantic import BaseModel, Field


class ReportOutput(BaseModel):
    """日报撰写 Crew 的输出模型。

    content 字段存储完整的 Markdown 日报正文，
    供 write_report_node 直接写入 report_content 状态字段。
    """

    content: str = Field(
        default="",
        description=(
            "完整的 AI 日报 Markdown 文本，包含七段式结构："
            "标题（含今日信号强度 + 今日一句话）、今日头条（1条深度解读）、"
            "GitHub 热点项目（2-4个，含星数增长上下文）、"
            "AI 热点新闻（4-6条，含可信度标签 + So What 分析）、"
            "趋势洞察（3-5条，含数据支撑）、本周行动建议（1-2条可落地任务）、"
            "上期回顾（可选，有历史追踪数据时包含）。"
            "总字数 800-2000 字，无禁用词，无感叹号。"
        ),
    )
    validation_issues: list[str] = Field(
        default_factory=list,
        description="格式校验问题列表，空列表表示通过校验。",
    )
