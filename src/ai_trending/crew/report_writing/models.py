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
            "完整的 AI 日报 Markdown 文本，必须包含四个 Section："
            "标题导语、GitHub 热点项目（3-5个）、AI 热点新闻（6-8条）、趋势洞察（3-5条）。"
            "总字数 700-1500 字，无禁用词，无感叹号。"
        ),
    )
    validation_issues: list[str] = Field(
        default_factory=list,
        description="格式校验问题列表，空列表表示通过校验。",
    )
