"""GitHub Trending Crew — 编排入口。

架构：
  两个独立的标准 @CrewBase Crew 按顺序执行：
    1. KeywordPlanningCrew  — 关键词规划（light 模型）
    2. TrendRankingCrew     — 趋势分析排名（default 模型）

  GitHub 搜索采集由 GitHubFetcher 完成（程序化，无需 LLM）。
  排名合并由 GitHubRanker 完成（程序化）。
  输出格式化由 format_text_output 完成。

  GitHubTrendingOrchestrator 负责：
    - 依次执行关键词规划 → 程序化搜索 → 趋势排名 → 排名合并
    - 传递中间结果（关键词 → 搜索 → 排名）
    - 兜底降级策略
    - 最终结果合并输出

使用方式：
  1. 独立 Agent 运行（命令行 / 脚本）：
       orchestrator = GitHubTrendingOrchestrator()
       text = orchestrator.run_as_agent(query="AI", top_n=5)
       print(text)

     或直接执行本文件：
       python -m ai_trending.crew.github_trending.crew

  2. 作为 LangGraph Tool 使用：
       from ai_trending.crew.github_trending import create_langgraph_tool
       tool = create_langgraph_tool()
       # 在 LangGraph 节点中调用
       result = tool.invoke({"query": "AI", "top_n": 5})

对外暴露：
  - GitHubTrendingOrchestrator.run(query, top_n)          → 原始数据元组
  - GitHubTrendingOrchestrator.run_as_agent(query, top_n) → 格式化文本（独立运行）
  - GitHubTrendingOrchestrator.as_langgraph_tool()        → LangGraph StructuredTool
  - create_langgraph_tool()                               → 模块级工厂函数（推荐）
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any

from ai_trending.crew.github_trending.fetchers import GitHubFetcher
from ai_trending.crew.github_trending.formatter import format_text_output
from ai_trending.crew.github_trending.keyword_planning.crew import KeywordPlanningCrew
from ai_trending.crew.github_trending.models import (
    GitHubSearchPlan,
    GitHubTrendRanking,
)
from ai_trending.crew.github_trending.ranker import GitHubRanker
from ai_trending.crew.github_trending.trend_ranking.crew import TrendRankingCrew
from ai_trending.crew.github_trending.utils import (
    default_keywords_for_query,
    model_to_dict,
    sanitize_keywords,
)
from ai_trending.logger import get_logger

log = get_logger("github_crew")


class GitHubTrendingOrchestrator:
    """GitHub 趋势发现编排器。

    流程：关键词规划（CrewAI）→ GitHub 搜索采集（程序化）→ 趋势排名（CrewAI）→ 排名合并。
    对外只暴露 run(query, top_n) 一个方法。
    """

    def __init__(self) -> None:
        self._fetcher = GitHubFetcher()
        self._ranker = GitHubRanker()

    # ── 唯一对外入口 ─────────────────────────────────────────

    def run(
        self,
        query: str = "AI",
        top_n: int = 5,
    ) -> tuple[list[dict[str, Any]], str, list[str], list[str]]:
        """执行完整的 GitHub 趋势发现流程。

        Args:
            query: 用户主题，例如 "AI"、"MCP"、"AI Agent"
            top_n: 期望输出数量（3-5）

        Returns:
            (final_repos, summary, hot_signals, keywords_used)
        """
        requested_count = max(3, min(top_n, 5))
        current_date = datetime.now().strftime("%Y-%m-%d")

        # Step 1: 关键词规划 Crew
        keywords = self._run_keyword_planning(query, current_date)

        # Step 2: 程序化 GitHub 搜索采集
        search_result = self._fetcher.fetch(keywords, query)

        if not search_result.candidates:
            log.warning(f"未搜索到与 '{query}' 相关的热门仓库")
            return [], "", [], keywords

        # Step 3: 趋势排名 Crew
        candidates_json = json.dumps(
            [model_to_dict(c) for c in search_result.candidates],
            ensure_ascii=False,
            indent=2,
        )
        ranking = self._run_trend_ranking(
            query, current_date, requested_count, candidates_json
        )

        # Step 4: 合并排名，选出最终结果
        final_repos, summary, hot_signals = self._ranker.merge(
            search_result, ranking, requested_count, query
        )

        return final_repos, summary, hot_signals, keywords

    # ── Step 实现 ────────────────────────────────────────────

    def _run_keyword_planning(self, query: str, current_date: str) -> list[str]:
        """Step 1：KeywordPlanningCrew 规划关键词，失败时使用兜底策略。"""
        try:
            result = KeywordPlanningCrew().crew().kickoff(
                inputs={"query": query, "current_date": current_date}
            )
            plan = self._extract_pydantic_output(result, GitHubSearchPlan)
            if plan and plan.keywords:
                keywords = sanitize_keywords(plan.keywords, query)
                log.info(f"CrewAI 关键词规划成功: {query} -> {keywords}")
                return keywords
        except Exception as e:
            log.warning(f"CrewAI 关键词规划失败: {e}")

        fallback = default_keywords_for_query(query)
        log.info(f"关键词规划使用兜底策略: {query} -> {fallback}")
        return fallback

    def _run_trend_ranking(
        self,
        query: str,
        current_date: str,
        requested_count: int,
        candidates_json: str,
    ) -> GitHubTrendRanking | None:
        """Step 3：TrendRankingCrew 趋势分析与重排行。"""
        try:
            result = TrendRankingCrew().crew().kickoff(
                inputs={
                    "query": query,
                    "current_date": current_date,
                    "requested_count": requested_count,
                    "candidates_json": candidates_json,
                }
            )
            ranking = self._extract_pydantic_output(result, GitHubTrendRanking)
            if ranking:
                log.info(f"CrewAI 趋势分析成功: 产出 {len(ranking.ranked_repos)} 个排序结果")
                return ranking
        except Exception as e:
            log.warning(f"CrewAI 趋势分析失败: {e}")
        return None

    # ── CrewOutput 解析辅助 ───────────────────────────────────

    def _extract_pydantic_output(self, output: Any, model_type: type) -> Any:
        """从 CrewOutput / TaskOutput 中提取结构化结果。

        优先级：
          1. output.pydantic（output_pydantic 直接输出，最可靠）
          2. tasks_output[-1].pydantic（Task 级别的 Pydantic 输出）
          3. raw 文本 JSON 解析（兜底，仅在前两者失败时使用）
        """
        # 1. 优先从 output.pydantic 获取（output_pydantic 已启用时最可靠）
        direct = getattr(output, "pydantic", None)
        if isinstance(direct, model_type):
            return direct

        # 2. 从 tasks_output 中获取 Task 级别的 Pydantic 输出
        tasks_output = getattr(output, "tasks_output", None) or []
        for task_output in reversed(tasks_output):
            task_model = getattr(task_output, "pydantic", None)
            if isinstance(task_model, model_type):
                return task_model

        # 3. 兜底：从 raw 文本解析 JSON（output_pydantic 失败时的降级路径）
        log.warning(
            f"[_extract_pydantic_output] output_pydantic 未返回 {model_type.__name__}，尝试 raw 文本解析"
        )
        for task_output in reversed(tasks_output):
            raw_text = getattr(task_output, "raw", None)
            parsed = self._parse_model_from_text(raw_text, model_type)
            if parsed is not None:
                return parsed

        raw_text = getattr(output, "raw", None)
        return self._parse_model_from_text(raw_text, model_type)

    def _parse_model_from_text(self, text: str | None, model_type: type) -> Any:
        """从原始文本中兜底解析 Pydantic 结果（仅在 output_pydantic 失败时使用）。"""
        if not text:
            return None

        candidates = [text.strip()]
        json_block = re.search(r"(\{.*\}|\[.*\])", text.strip(), re.DOTALL)
        if json_block:
            candidates.append(json_block.group(1).strip())

        for candidate in candidates:
            normalized = re.sub(r"^```(?:json)?\s*", "", candidate)
            normalized = re.sub(r"\s*```$", "", normalized).strip()
            try:
                if hasattr(model_type, "model_validate_json"):
                    return model_type.model_validate_json(normalized)
                return model_type.parse_raw(normalized)
            except Exception:
                continue
        return None

    # ── 独立 Agent 运行入口 ───────────────────────────────────

    def run_as_agent(
        self,
        query: str = "AI",
        top_n: int = 5,
    ) -> str:
        """独立 Agent 运行入口：执行完整流程并返回格式化文本。

        适用场景：命令行调用、脚本直接运行、单元测试。

        Args:
            query: 用户主题，例如 "AI"、"MCP"、"AI Agent"
            top_n:  期望输出数量（3-5）

        Returns:
            格式化的 Markdown 文本；失败时返回错误提示字符串。

        示例::

            orchestrator = GitHubTrendingOrchestrator()
            print(orchestrator.run_as_agent(query="MCP", top_n=5))
        """
        log.info(f"[run_as_agent] 开始执行，主题='{query}', top_n={top_n}")
        try:
            final_repos, summary, hot_signals, keywords = self.run(
                query=query, top_n=top_n
            )
        except Exception as e:
            log.error(f"[run_as_agent] 执行失败: {e}")
            return f"❌ GitHub 趋势发现失败: {e}"

        if not final_repos:
            return (
                f"未能从 GitHub 搜索到与 '{query}' 相关的热门仓库。\n"
                "请检查网络连接、GITHUB_TRENDING_TOKEN 或模型配置。"
            )

        return format_text_output(final_repos, query, keywords, summary, hot_signals)

    # ── LangGraph Tool 入口 ───────────────────────────────────

    def as_langgraph_tool(self):
        """返回可直接注册到 LangGraph 的 StructuredTool。

        适用场景：在 LangGraph 节点或 ReAct Agent 中将本 Crew 作为工具调用。

        Returns:
            langchain_core.tools.StructuredTool 实例。

        示例::

            tool = GitHubTrendingOrchestrator().as_langgraph_tool()
            # 在 LangGraph 节点中
            result = tool.invoke({"query": "AI", "top_n": 5})
        """
        try:
            from langchain_core.tools import StructuredTool
            from pydantic import BaseModel, Field as PydanticField
        except ImportError as e:
            raise ImportError(
                "as_langgraph_tool() 需要 langchain-core，请执行: pip install langchain-core"
            ) from e

        orchestrator = self  # 捕获当前实例，供闭包使用

        class _GitHubTrendingInput(BaseModel):
            query: str = PydanticField(
                default="AI",
                description="搜索主题，例如 'AI'、'LLM'、'AI Agent'、'MCP'",
            )
            top_n: int = PydanticField(
                default=5,
                description="最终返回 3-5 个项目，默认 5",
            )

        def _run_tool(query: str = "AI", top_n: int = 5) -> str:
            return orchestrator.run_as_agent(query=query, top_n=top_n)

        return StructuredTool.from_function(
            func=_run_tool,
            name="github_trending_tool",
            description=(
                "通过 CrewAI 编排两个 Agent（关键词规划 → 趋势分析）+ 程序化 GitHub 搜索，"
                "发现最近最能代表 AI 发展趋势的 3-5 个 GitHub 开源项目。"
                "返回格式化的 Markdown 文本，包含项目评分、亮点和趋势判断。"
            ),
            args_schema=_GitHubTrendingInput,
        )


# ── 模块级工厂函数（推荐在 LangGraph 中使用）────────────────────

def create_langgraph_tool():
    """创建并返回 GitHub 趋势发现的 LangGraph StructuredTool。

    这是在 LangGraph 节点或 ReAct Agent 中使用本 Crew 的推荐方式。

    Returns:
        langchain_core.tools.StructuredTool 实例。

    示例::

        from ai_trending.crew.github_trending import create_langgraph_tool

        tool = create_langgraph_tool()
        result = tool.invoke({"query": "MCP", "top_n": 5})
    """
    return GitHubTrendingOrchestrator().as_langgraph_tool()


# ── 独立运行入口 ──────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    import sys

    from ai_trending.logger import setup_logging

    parser = argparse.ArgumentParser(
        description="GitHub 热门 AI 开源项目发现（独立 Agent 模式）"
    )
    parser.add_argument(
        "--query", default="AI", help="搜索主题，例如 'AI'、'MCP'、'AI Agent'（默认: AI）"
    )
    parser.add_argument(
        "--top-n", type=int, default=5, help="返回项目数量 3-5（默认: 5）"
    )
    parser.add_argument("--verbose", action="store_true", help="输出详细日志")
    args = parser.parse_args()

    setup_logging(level="DEBUG" if args.verbose else "INFO")

    result = GitHubTrendingOrchestrator().run_as_agent(
        query=args.query, top_n=args.top_n
    )
    print(result)
    sys.exit(0 if result and not result.startswith("❌") else 1)