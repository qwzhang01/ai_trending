"""crew/editorial_planning — 编辑部选题规划 Crew.

职责：
  - 判断今日信号强度（red/yellow/green）
  - 选定今日头条
  - 为每个项目/新闻分配写作角度
  - 生成 Kill List（排除低价值内容）
  - 拟定"今日一句话"

输入 inputs: {"scoring_summary": str, "current_date": str, "topic_context": str}
输出 pydantic: EditorialPlan
"""

from __future__ import annotations

import json
from typing import Any

from crewai import Agent, Crew, Process, Task
from crewai.project import CrewBase, agent, crew, task

from ai_trending.crew.editorial_planning.models import (
    EditorialPlan,
    HeadlineDecision,
)
from ai_trending.llm_client import build_crewai_llm
from ai_trending.logger import get_logger

log = get_logger("editorial_planning")


@CrewBase
class EditorialPlanningCrew:
    """编辑部选题规划 Crew — 在评分层和写作层之间做编辑决策。

    使用 light 档 LLM，因为编辑决策本质是分类任务。

    输入 inputs: {"scoring_summary": str, "current_date": str, "topic_context": str}
    输出 pydantic: EditorialPlan
    """

    agents_config = "config/agents.yaml"
    tasks_config = "config/tasks.yaml"

    @agent
    def editorial_planner(self) -> Agent:
        """编辑策划 Agent — 做选题和角度决策。"""
        return Agent(
            config=self.agents_config["editorial_planner"],  # type: ignore[index]
            llm=build_crewai_llm("light"),  # 编辑决策是分类任务，light 档足够
            allow_delegation=False,
            verbose=False,
        )

    @task
    def plan_editorial_task(self) -> Task:
        """选题规划 Task — 输出 EditorialPlan。"""
        return Task(
            config=self.tasks_config["plan_editorial_task"],  # type: ignore[index]
            output_pydantic=EditorialPlan,
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
        scoring_result: str = "",
        current_date: str = "",
        topic_context: str = "",
    ) -> tuple[EditorialPlan, dict[str, int]]:
        """执行编辑部选题规划。

        Args:
            scoring_result: TrendScoringOutput 的 JSON 字符串
            current_date:   当前日期
            topic_context:  近期话题追踪上下文（由 TopicTracker 提供）

        Returns:
            (EditorialPlan, token_usage) 元组
        """
        # 从评分 JSON 中提取摘要信息供 Agent 参考
        scoring_summary = self._build_scoring_summary(scoring_result)

        log.info(f"[EditorialPlanningCrew] 开始编辑选题规划 ({current_date})")

        try:
            result = self.crew().kickoff(
                inputs={
                    "scoring_summary": scoring_summary,
                    "current_date": current_date,
                    "topic_context": topic_context or "（无近期话题追踪记录）",
                }
            )

            # 提取 Pydantic 输出
            plan = self._extract_plan(result)

            # 提取 token 用量
            token_usage = self._extract_token_usage(result)

            log.info(
                f"[EditorialPlanningCrew] 完成: "
                f"signal={plan.signal_strength}, "
                f"headline={plan.headline.chosen_item}, "
                f"angles={len(plan.repo_angles)}+{len(plan.news_angles)}, "
                f"kill_list={len(plan.kill_list)}"
            )
            return plan, token_usage

        except Exception as e:
            log.error(f"[EditorialPlanningCrew] 失败，使用兜底 Plan: {e}")
            return self._fallback_plan(scoring_result), {}

    def _build_scoring_summary(self, scoring_result: str) -> str:
        """从评分 JSON 中提取关键信息，构建 Agent 可读的摘要。"""
        try:
            data = json.loads(scoring_result) if scoring_result else {}
        except (json.JSONDecodeError, TypeError):
            return "评分数据不可用"

        lines = []

        # 项目概览
        repos = data.get("scored_repos", [])
        if repos:
            lines.append(f"### 评分项目（共 {len(repos)} 个）")
            for i, repo in enumerate(repos[:8]):
                name = repo.get("name", repo.get("repo", f"项目{i+1}"))
                stars = repo.get("stars", 0)
                growth = repo.get("stars_growth_7d")
                scores = repo.get("scores", {})
                overall = scores.get("综合", scores.get("overall", "N/A"))
                hook = repo.get("story_hook", "")
                growth_str = f"（+{growth}）" if growth else ""
                lines.append(
                    f"- **{name}** ⭐{stars}{growth_str} 综合分:{overall}"
                )
                if hook:
                    lines.append(f"  故事钩子: {hook}")

        # 新闻概览
        news = data.get("scored_news", [])
        if news:
            lines.append(f"\n### 评分新闻（共 {len(news)} 条）")
            for item in news[:10]:
                title = item.get("title", "")
                impact = item.get("impact_score", 0)
                source = item.get("source", "")
                so_what = item.get("so_what_analysis", "")
                lines.append(f"- **{title}** 影响力:{impact} 来源:{source}")
                if so_what:
                    lines.append(f"  So What: {so_what}")

        # 趋势总结
        summary = data.get("daily_summary", {})
        if summary.get("top_trend"):
            lines.append(f"\n### 趋势总结")
            lines.append(f"- 主趋势: {summary.get('top_trend', '')}")
            if summary.get("hot_directions"):
                lines.append(f"- 热点方向: {', '.join(summary['hot_directions'])}")

        return "\n".join(lines) if lines else "评分数据为空"

    @staticmethod
    def _extract_plan(result: Any) -> EditorialPlan:
        """从 CrewOutput 提取 EditorialPlan。"""
        if hasattr(result, "pydantic") and result.pydantic:
            return result.pydantic
        if hasattr(result, "tasks_output") and result.tasks_output:
            last_task = result.tasks_output[-1]
            if hasattr(last_task, "pydantic") and last_task.pydantic:
                return last_task.pydantic
        # 尝试从 raw 文本解析
        log.warning("[EditorialPlanningCrew] 无法提取 Pydantic 输出，使用默认 Plan")
        return EditorialPlan()

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
    def _fallback_plan(scoring_result: str) -> EditorialPlan:
        """兜底策略：从评分数据中简单提取编辑决策。"""
        try:
            data = json.loads(scoring_result) if scoring_result else {}
        except (json.JSONDecodeError, TypeError):
            return EditorialPlan()

        repos = data.get("scored_repos", [])
        headline_name = ""
        if repos:
            headline_name = repos[0].get("name", repos[0].get("repo", ""))

        return EditorialPlan(
            signal_strength="yellow",
            signal_reason="兜底默认值",
            headline=HeadlineDecision(
                chosen_item=headline_name,
                reason="评分最高的项目（兜底选择）",
                angle="规模切入",
            ),
            today_hook="AI 技术持续演进",
        )
