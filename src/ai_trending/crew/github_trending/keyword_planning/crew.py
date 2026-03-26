"""关键词规划 Crew — 标准 CrewAI @CrewBase 实现。

职责：接收用户主题，输出适合 GitHub 检索的英文技术关键词列表。
"""

from __future__ import annotations

from crewai import Agent, Crew, Process, Task
from crewai.project import CrewBase, agent, crew, task

from ai_trending.crew.github_trending.models import GitHubSearchPlan
from ai_trending.llm_client import build_crewai_llm


@CrewBase
class KeywordPlanningCrew:
    """关键词规划 Crew（单 Agent + 单 Task）。

    输入 inputs: {"query": str, "current_date": str}
    输出 pydantic: GitHubSearchPlan
    """

    agents_config = "config/agents.yaml"
    tasks_config = "config/tasks.yaml"

    @agent
    def keyword_planner(self) -> Agent:
        """关键词规划 Agent，使用轻量模型降低成本。"""
        return Agent(
            config=self.agents_config["keyword_planner"],  # type: ignore[index]
            llm=build_crewai_llm("light"),
            allow_delegation=False,
            verbose=False,
        )

    @task
    def plan_keywords_task(self) -> Task:
        """关键词规划 Task，输出 JSON 文本（由编排器解析为 GitHubSearchPlan）。"""
        return Task(
            config=self.tasks_config["plan_keywords"],  # type: ignore[index]
            # 不使用 output_pydantic，避免 instructor 在 DeepSeek 等模型上触发多 tool call 报错
            # 编排器的 _parse_model_from_text 会从 raw 文本中解析 GitHubSearchPlan
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
