"""趋势排名 Crew — 标准 CrewAI @CrewBase 实现。

职责：接收候选仓库 JSON，由 LLM 评分排序，输出趋势排名结果。
"""

from __future__ import annotations

from crewai import Agent, Crew, Process, Task
from crewai.project import CrewBase, agent, crew, task

from ai_trending.llm_client import build_crewai_llm


@CrewBase
class TrendRankingCrew:
    """趋势排名 Crew（单 Agent + 单 Task）。

    输入 inputs: {"query": str, "current_date": str, "requested_count": int, "candidates_json": str}
    输出 pydantic: GitHubTrendRanking
    """

    agents_config = "config/agents.yaml"
    tasks_config = "config/tasks.yaml"

    @agent
    def trend_analyst(self) -> Agent:
        """趋势分析 Agent，使用默认模型保证分析质量。"""
        return Agent(
            config=self.agents_config["trend_analyst"],  # type: ignore[index]
            llm=build_crewai_llm("default"),
            allow_delegation=False,
            verbose=False,
        )

    @task
    def rank_repos_task(self) -> Task:
        """仓库趋势排名 Task，输出 JSON 文本（由编排器解析为 GitHubTrendRanking）。"""
        return Task(
            config=self.tasks_config["rank_repos"],  # type: ignore[index]
            # 不使用 output_pydantic，避免 instructor 在 DeepSeek 等模型上触发多 tool call 报错
            # 编排器的 _parse_model_from_text 会从 raw 文本中解析 GitHubTrendRanking
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
