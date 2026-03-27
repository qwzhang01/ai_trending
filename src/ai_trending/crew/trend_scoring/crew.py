"""TrendScoringCrew — 将 GitHub 项目和新闻数据进行结构化评分。

输入 inputs:
    github_data:  str  — GitHub 热点项目原始数据
    news_data:    str  — AI 新闻原始数据
    current_date: str  — 日期，格式 YYYY-MM-DD

输出 pydantic: TrendScoringOutput
    scored_repos:   list[ScoredRepo]  — GitHub 项目评分列表
    scored_news:    list[ScoredNews]  — 新闻评分列表
    daily_summary:  DailySummary      — 今日趋势洞察汇总
"""

from __future__ import annotations

import json
import re

from crewai import Agent, Crew, Process, Task
from crewai.project import CrewBase, agent, crew, task

from ai_trending.llm_client import build_crewai_llm
from ai_trending.logger import get_logger

from .models import DailySummary, TrendScoringOutput

log = get_logger("trend_scoring_crew")

# 兜底评分结果（LLM 失败时使用）
_FALLBACK_OUTPUT = TrendScoringOutput(
    scored_repos=[],
    scored_news=[],
    daily_summary=DailySummary(
        top_trend="评分数据不可用",
        hot_directions=[],
        overall_sentiment="中性",
    ),
)


def _extract_token_usage(crew_output) -> dict[str, int]:
    """从 CrewOutput 中提取 token 用量，返回标准化字典。

    CrewAI 的 CrewOutput.token_usage 是 UsageMetrics 对象，
    包含 total_tokens、prompt_tokens、completion_tokens、successful_requests。
    """
    empty: dict[str, int] = {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
        "successful_requests": 0,
    }
    try:
        usage = getattr(crew_output, "token_usage", None)
        if usage is None:
            return empty
        return {
            "prompt_tokens": int(getattr(usage, "prompt_tokens", 0) or 0),
            "completion_tokens": int(getattr(usage, "completion_tokens", 0) or 0),
            "total_tokens": int(getattr(usage, "total_tokens", 0) or 0),
            "successful_requests": int(getattr(usage, "successful_requests", 0) or 0),
        }
    except Exception:
        return empty


@CrewBase
class TrendScoringCrew:
    """AI 趋势评分 Crew。

    职责：对 GitHub 热点项目和 AI 新闻进行结构化量化评分，
    为日报撰写提供排序依据和叙事素材。
    使用 default 档 LLM 保证评分质量。
    """

    agents_config = "config/agents.yaml"
    tasks_config = "config/tasks.yaml"

    @agent
    def trend_scorer(self) -> Agent:
        """趋势评分 Agent，使用 default 档 LLM 保证评分质量。"""
        return Agent(
            config=self.agents_config["trend_scorer"],  # type: ignore[index]
            llm=build_crewai_llm("default"),
            allow_delegation=False,
            verbose=False,
        )

    @task
    def score_trends_task(self) -> Task:
        """趋势评分 Task，输出结构化 TrendScoringOutput。"""
        return Task(
            config=self.tasks_config["score_trends_task"],  # type: ignore[index]
            output_pydantic=TrendScoringOutput,
        )

    @crew
    def crew(self) -> Crew:
        """组装 TrendScoringCrew。"""
        return Crew(
            agents=self.agents,
            tasks=self.tasks,
            process=Process.sequential,
            verbose=False,
        )

    def _parse_from_raw(self, raw: str) -> TrendScoringOutput | None:
        """从原始文本中兜底解析 TrendScoringOutput。"""
        if not raw:
            return None
        try:
            # 尝试提取 JSON 块（支持 markdown 代码块包裹）
            json_match = re.search(r"\{.*\}", raw.strip(), re.DOTALL)
            if json_match:
                data = json.loads(json_match.group(0))
                return TrendScoringOutput.model_validate(data)
        except Exception as e:
            log.warning(f"[TrendScoringCrew] raw 文本解析失败: {e}")
        return None

    def run(
        self,
        github_data: str,
        news_data: str,
        current_date: str,
    ) -> tuple[TrendScoringOutput, dict[str, int]]:
        """对外公开入口：执行趋势评分，返回 (TrendScoringOutput, token_usage)。

        Args:
            github_data:  GitHub 热点项目原始数据字符串
            news_data:    AI 新闻原始数据字符串
            current_date: 日期，格式 YYYY-MM-DD

        Returns:
            (TrendScoringOutput, token_usage_dict)，其中 token_usage_dict 包含
            prompt_tokens、completion_tokens、total_tokens、successful_requests。
            若 LLM 调用失败，抛出异常由节点层处理兜底。
        """
        log.info(f"[TrendScoringCrew] 开始评分 ({current_date})")

        try:
            result = self.crew().kickoff(
                inputs={
                    "github_data": github_data or "无数据",
                    "news_data": news_data or "无数据",
                    "current_date": current_date,
                }
            )

            # 提取 token 用量（CrewOutput.token_usage 为 UsageMetrics 对象）
            token_usage = _extract_token_usage(result)

            # 优先从 pydantic 输出获取
            output: TrendScoringOutput | None = None
            if result.pydantic and isinstance(result.pydantic, TrendScoringOutput):
                output = result.pydantic
            elif result.tasks_output:
                last = result.tasks_output[-1]
                if last.pydantic and isinstance(last.pydantic, TrendScoringOutput):
                    output = last.pydantic

            # 兜底：从 raw 文本解析 JSON
            if output is None:
                raw = result.raw or ""
                output = self._parse_from_raw(raw)
                if output is None:
                    log.warning("[TrendScoringCrew] 未获取到 Pydantic 输出，使用兜底空结果")
                    return _FALLBACK_OUTPUT, token_usage

            log.info(
                f"[TrendScoringCrew] 完成，"
                f"项目评分 {len(output.scored_repos)} 条，"
                f"新闻评分 {len(output.scored_news)} 条，"
                f"token 用量 {token_usage.get('total_tokens', 0)}"
            )
            return output, token_usage

        except Exception as e:
            log.error(f"[TrendScoringCrew] 评分失败: {e}")
            raise