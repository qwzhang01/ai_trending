"""crew/quality_review — Pydantic 数据模型。

质量审核的结构化输出，记录审核发现的问题和修改建议。
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class QualityIssue(BaseModel):
    """单个质量问题。"""

    severity: str = Field(
        default="info",
        description="严重程度：'error'（虚构数据/事实错误）/ 'warning'（风格偏离/格式问题）/ 'info'（优化建议）",
    )
    location: str = Field(
        default="",
        description="问题位置（Section 名称，如'今日头条'、'GitHub 热点项目'、'趋势洞察'）",
    )
    description: str = Field(
        default="",
        description="问题描述，简明说明发现了什么问题",
    )
    suggestion: str = Field(
        default="",
        description="修改建议，具体说明应该如何改正",
    )


class QualityReviewResult(BaseModel):
    """质量审核结果。

    由 QualityReviewCrew 生成，记录到 TrendingState.quality_review。
    审核失败不阻断发布，只记录 warning。
    """

    passed: bool = Field(
        default=True,
        description="是否通过审核：无 error 级问题即为通过",
    )
    overall_assessment: str = Field(
        default="",
        description="整体评估，一句话概括日报质量（不超过 50 字）",
    )
    issues: list[QualityIssue] = Field(
        default_factory=list,
        description="发现的问题列表，按严重程度排序",
    )
    suggestions: list[str] = Field(
        default_factory=list,
        description="通用改进建议（不针对特定 Section）",
    )

    @property
    def error_count(self) -> int:
        """error 级问题数量。"""
        return sum(1 for issue in self.issues if issue.severity == "error")

    @property
    def warning_count(self) -> int:
        """warning 级问题数量。"""
        return sum(1 for issue in self.issues if issue.severity == "warning")

    def format_summary(self) -> str:
        """格式化审核摘要，供日志和 State 记录使用。"""
        status = "通过" if self.passed else "未通过"
        lines = [
            f"质量审核: {status}",
            f"  问题统计: {self.error_count} error, {self.warning_count} warning, "
            f"{len(self.issues) - self.error_count - self.warning_count} info",
        ]
        if self.overall_assessment:
            lines.append(f"  整体评估: {self.overall_assessment}")
        if self.issues:
            lines.append("  具体问题:")
            for issue in self.issues:
                lines.append(
                    f"    [{issue.severity}] {issue.location}: {issue.description}"
                )
        if self.suggestions:
            lines.append("  改进建议:")
            for s in self.suggestions:
                lines.append(f"    - {s}")
        return "\n".join(lines)
