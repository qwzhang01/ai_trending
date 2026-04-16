"""crew/editorial_planning — Pydantic 数据模型。

编辑部选题规划的结构化输出，指导下游写作层的工作。
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class HeadlineDecision(BaseModel):
    """头条选择决策。"""

    chosen_item: str = Field(default="", description="选定的头条项目或新闻名称")
    reason: str = Field(default="", description="选择理由，不超过 50 字")
    angle: str = Field(
        default="",
        description="建议的叙事角度，如'痛点切入'、'规模切入'",
    )


class AngleAssignment(BaseModel):
    """内容角度分配。"""

    item_name: str = Field(default="", description="项目或新闻名称")
    angle: str = Field(
        default="",
        description="分配的切入角度：痛点切入/成本切入/规模切入/对比切入",
    )
    key_point: str = Field(
        default="",
        description="这条内容最值得强调的一个点，不超过 30 字",
    )


class EditorialPlan(BaseModel):
    """编辑部选题规划输出。

    由 EditorialPlanningCrew 生成，传递给 ReportWritingCrew 执行。
    """

    signal_strength: str = Field(
        default="yellow",
        description="今日信号强度：'red'（重大变化日）/ 'yellow'（常规更新日）/ 'green'（平静日）",
    )
    signal_reason: str = Field(
        default="",
        description="信号强度判断理由，不超过 30 字",
    )
    headline: HeadlineDecision = Field(
        default_factory=HeadlineDecision,
        description="今日头条决策",
    )
    repo_angles: list[AngleAssignment] = Field(
        default_factory=list,
        description="每个推荐项目的写作角度分配",
    )
    news_angles: list[AngleAssignment] = Field(
        default_factory=list,
        description="每条推荐新闻的写作角度分配",
    )
    kill_list: list[str] = Field(
        default_factory=list,
        description="排除的内容名称及原因，如 'xxx: 与昨日头条重复'",
    )
    today_hook: str = Field(
        default="",
        description="今日一句话建议，不超过 20 字，有判断力的句子",
    )
    kill_list_check: str = Field(
        default="",
        description="Kill List 验证结果记录，格式：'已检查 N 条：[条目] ✅ 无冲突 / ❌ 冲突（已替换为...）'",
    )

    def format_for_prompt(self) -> str:
        """将编辑决策格式化为可注入到 Prompt 中的文本。"""
        signal_emoji = {
            "red": "🔴 重大变化日",
            "yellow": "🟡 常规更新日",
            "green": "🟢 平静日",
        }
        signal_display = signal_emoji.get(self.signal_strength, "🟡 常规更新日")

        lines = [
            "## 编辑决策（由主编确定，请严格执行）",
            "",
            f"**信号强度**: {signal_display}",
        ]
        if self.signal_reason:
            lines.append(f"**判断理由**: {self.signal_reason}")
        if self.headline.chosen_item:
            lines.append(f"**今日头条**: {self.headline.chosen_item}")
            if self.headline.angle:
                lines.append(f"**头条角度**: {self.headline.angle}")
            if self.headline.reason:
                lines.append(f"**选定理由**: {self.headline.reason}")
        if self.today_hook:
            lines.append(f"**今日一句话**: {self.today_hook}")

        if self.repo_angles:
            lines.append("")
            lines.append("### 项目写作角度分配")
            for a in self.repo_angles:
                key_info = f"（重点: {a.key_point}）" if a.key_point else ""
                lines.append(f"- **{a.item_name}**: {a.angle}{key_info}")

        if self.news_angles:
            lines.append("")
            lines.append("### 新闻写作角度分配")
            for a in self.news_angles:
                key_info = f"（重点: {a.key_point}）" if a.key_point else ""
                lines.append(f"- **{a.item_name}**: {a.angle}{key_info}")

        if self.kill_list:
            lines.append("")
            lines.append("### 排除内容（不写入日报）")
            for item in self.kill_list:
                lines.append(f"- {item}")

        return "\n".join(lines)
