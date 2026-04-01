"""crew/quality_review — 质量审核 Crew.

职责：
  - 检查日报中是否有 LLM 虚构的统计数据（无来源的百分比、金额等）
  - 检查内容是否与评分源数据一致
  - 检查叙事风格是否符合"克制、精准"要求
  - 检查结构完整性（五大必要 Section 等）
  - 生成审核结论和修改建议（不自行修改内容）

输入 inputs: {"report_content": str, "scoring_summary": str, "current_date": str}
输出 pydantic: QualityReviewResult
"""

from __future__ import annotations

import json
from typing import Any

from crewai import Agent, Crew, Process, Task
from crewai.project import CrewBase, agent, crew, task

from ai_trending.crew.quality_review.models import QualityReviewResult
from ai_trending.llm_client import build_crewai_llm
from ai_trending.logger import get_logger

log = get_logger("quality_review")


@CrewBase
class QualityReviewCrew:
    """质量审核 Crew — 在写作层和发布层之间做内容审核。

    使用 light 档 LLM，因为审核本质是分类/比对任务。

    输入 inputs: {"report_content": str, "scoring_summary": str, "current_date": str}
    输出 pydantic: QualityReviewResult
    """

    agents_config = "config/agents.yaml"
    tasks_config = "config/tasks.yaml"

    @agent
    def quality_reviewer(self) -> Agent:
        """质量审核 Agent — 检查事实准确性和风格规范。"""
        return Agent(
            config=self.agents_config["quality_reviewer"],  # type: ignore[index]
            llm=build_crewai_llm("light"),  # 审核是分类/比对任务，light 档足够
            allow_delegation=False,
            verbose=False,
        )

    @task
    def quality_review_task(self) -> Task:
        """质量审核 Task — 输出 QualityReviewResult。"""
        return Task(
            config=self.tasks_config["quality_review_task"],  # type: ignore[index]
            output_pydantic=QualityReviewResult,
        )

    @crew
    def crew(self) -> Crew:
        """组装 Crew，由 @CrewBase 自动注入 agents 和 tasks。"""
        return Crew(
            agents=self.agents,
            tasks=self.tasks,
            process=Process.sequential,
            verbose=False,
        )

    def run(
        self,
        report_content: str = "",
        scoring_result: str = "",
        current_date: str = "",
        writing_brief: str = "",
    ) -> tuple[QualityReviewResult, dict[str, int]]:
        """执行质量审核。

        Args:
            report_content: 待审核的日报 Markdown 内容
            scoring_result: TrendScoringOutput 的 JSON 字符串（用于交叉比对）
            current_date:   当前日期
            writing_brief:  WritingBrief 文本（事实核对的权威数字来源）

        Returns:
            (QualityReviewResult, token_usage) 元组
        """
        # 从评分 JSON 中提取摘要供 Agent 比对
        scoring_summary = self._build_scoring_summary(scoring_result)

        # 从 WritingBrief 提取事实核对基准（真实数字来源）
        fact_check_source = self._build_fact_check_source(
            writing_brief, scoring_summary
        )

        log.info(f"[QualityReviewCrew] 开始质量审核 ({current_date})")

        if not report_content:
            log.warning("[QualityReviewCrew] 日报内容为空，跳过审核")
            return QualityReviewResult(
                passed=False,
                overall_assessment="日报内容为空，无法审核",
            ), {}

        try:
            result = self.crew().kickoff(
                inputs={
                    "report_content": report_content,
                    "scoring_summary": scoring_summary,
                    "fact_check_source": fact_check_source,
                    "current_date": current_date,
                }
            )

            # 提取 Pydantic 输出
            review = self._extract_review(result)

            # 提取 token 用量
            token_usage = self._extract_token_usage(result)

            log.info(
                f"[QualityReviewCrew] 完成: "
                f"passed={review.passed}, "
                f"issues={len(review.issues)} "
                f"(error={review.error_count}, warning={review.warning_count})"
            )
            return review, token_usage

        except Exception as e:
            log.error(f"[QualityReviewCrew] 审核失败，使用兜底结果: {e}")
            return self._fallback_review(str(e)), {}

    def _build_scoring_summary(self, scoring_result: str) -> str:
        """从评分 JSON 中提取关键数据，供 Agent 交叉比对。"""
        try:
            data = json.loads(scoring_result) if scoring_result else {}
        except (json.JSONDecodeError, TypeError):
            return "评分源数据不可用"

        lines = []

        # 项目数据（星数、增长等关键数字）
        repos = data.get("scored_repos", [])
        if repos:
            lines.append("### 项目数据")
            for repo in repos[:8]:
                name = repo.get("name", repo.get("repo", ""))
                stars = repo.get("stars", 0)
                growth = repo.get("stars_growth_7d")
                language = repo.get("language", "")
                growth_str = f"（+{growth}）" if growth else ""
                lines.append(f"- {name}: ⭐{stars}{growth_str} 语言:{language}")

        # 新闻数据（标题、来源等关键信息）
        news = data.get("scored_news", [])
        if news:
            lines.append("\n### 新闻数据")
            for item in news[:10]:
                title = item.get("title", "")
                source = item.get("source", "")
                lines.append(f"- {title} （来源: {source}）")

        # 趋势总结
        summary = data.get("daily_summary", {})
        if summary.get("top_trend"):
            lines.append("\n### 趋势数据")
            lines.append(f"- 主趋势: {summary.get('top_trend', '')}")
            if summary.get("hot_directions"):
                lines.append(f"- 热点方向: {', '.join(summary['hot_directions'])}")

        return "\n".join(lines) if lines else "评分源数据为空"

    def _build_fact_check_source(self, writing_brief: str, scoring_summary: str) -> str:
        """构建事实核对的权威数字来源。

        WritingBrief 是已经过处理的精简版本，包含了真实的星数、增长数字等，
        是日报中数字的唯一合法来源。

        Args:
            writing_brief:   WritingBrief.format_for_prompt() 输出的文本
            scoring_summary: 评分摘要（WritingBrief 不可用时的备用）

        Returns:
            供 Agent 核对的权威数字来源文本
        """
        if writing_brief and writing_brief not in (
            "（无写作简报，请根据编辑决策自行组织内容）",
        ):
            # WritingBrief 可用时，优先使用（已经过精简，信噪比更高）
            lines = [
                "以下是本次日报的**权威数据来源**，日报中的所有数字必须与此一致：",
                "",
                writing_brief[:2000],  # 截断避免过长
            ]
            return "\n".join(lines)
        # 降级到评分摘要
        return f"以下是评分源数据（权威数字来源）：\n\n{scoring_summary}"

    @staticmethod
    def _extract_review(result: Any) -> QualityReviewResult:
        """从 CrewOutput 提取 QualityReviewResult。"""
        if hasattr(result, "pydantic") and result.pydantic:
            return result.pydantic
        if hasattr(result, "tasks_output") and result.tasks_output:
            last_task = result.tasks_output[-1]
            if hasattr(last_task, "pydantic") and last_task.pydantic:
                return last_task.pydantic
        log.warning("[QualityReviewCrew] 无法提取 Pydantic 输出，使用默认通过结果")
        return QualityReviewResult(
            passed=True,
            overall_assessment="审核结果解析失败，默认通过",
        )

    @staticmethod
    def _extract_token_usage(result: Any) -> dict[str, int]:
        """从 CrewOutput 提取 token 用量。"""
        if hasattr(result, "token_usage") and result.token_usage:
            usage = result.token_usage
            return {
                "prompt_tokens": getattr(usage, "prompt_tokens", 0) or 0,
                "completion_tokens": getattr(usage, "completion_tokens", 0) or 0,
                "total_tokens": getattr(usage, "total_tokens", 0) or 0,
                "successful_requests": getattr(usage, "successful_requests", 0) or 0,
            }
        return {}

    @staticmethod
    def _fallback_review(error_msg: str) -> QualityReviewResult:
        """兜底策略：审核失败时返回默认通过（不阻断发布）。"""
        return QualityReviewResult(
            passed=True,
            overall_assessment=f"审核 Crew 调用失败（{error_msg}），默认通过",
            suggestions=["审核模块出现异常，建议人工检查日报内容"],
        )
