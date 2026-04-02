"""新闻采集 Crew — 标准 CrewAI 编排.

职责:
  1. 调用 NewsFetcher 并发抓取多源原始新闻（HN / Reddit / newsdata.io / 知乎）
  2. 由 CrewAI Agent 对原始数据做 LLM 筛选，提炼出最近几天最有价值的 AI 大模型相关新闻

使用方式::

    from ai_trending.crew.new_collect import NewsCollectCrew

    result = NewsCollectCrew(keywords=["AI", "LLM", "大模型"]).run()
    # result 是格式化好的新闻摘要字符串
"""

from __future__ import annotations

import time
from datetime import datetime

from crewai import Agent, Crew, Process, Task
from crewai.project import CrewBase, agent, crew, task

from ai_trending.crew.new_collect.fetchers import NewsFetcher
from ai_trending.llm_client import build_crewai_llm
from ai_trending.logger import get_logger

log = get_logger("news_crew")


@CrewBase
class NewsCollectCrew:
    """AI 新闻采集与筛选 Crew.

    流程:
      fetch（Python）→ filter_news_task（CrewAI Agent LLM 筛选）

    Args:
        keywords: 搜索关键词列表，默认 ["AI", "LLM", "AI Agent", "大模型"]
        top_n: 抓取阶段每源最多条数，默认 30
    """

    agents_config = "config/agents.yaml"
    tasks_config = "config/tasks.yaml"

    def __init__(
        self,
        keywords: list[str] | None = None,
        top_n: int = 30,
    ) -> None:
        # 注意：@CrewBase 装饰器在 CrewAI 1.11.0+ 中会通过元类处理初始化，
        # 不能调用 super().__init__()，否则会导致 "super(type, obj): obj must be an instance or subtype of type" 错误
        self.keywords = keywords or ["AI", "LLM", "AI Agent", "大模型"]
        self.top_n = top_n

    # ------------------------------------------------------------------
    # Agent
    # ------------------------------------------------------------------
    @agent
    def news_analyst(self) -> Agent:
        """AI 新闻分析师 Agent，负责筛选和提炼有价值的新闻."""
        return Agent(
            config=self.agents_config["news_analyst"],  # type: ignore[index]
            llm=build_crewai_llm("light"),
            verbose=False,
            allow_delegation=False,
        )

    # ------------------------------------------------------------------
    # Task
    # ------------------------------------------------------------------
    @task
    def filter_news_task(self) -> Task:
        """新闻筛选任务：对原始抓取数据做 LLM 筛选，输出格式化摘要."""
        return Task(
            config=self.tasks_config["filter_news_task"],  # type: ignore[index]
            # description / expected_output 从 YAML 读取，动态数据通过 kickoff(inputs=) 注入
        )

    # ------------------------------------------------------------------
    # Crew
    # ------------------------------------------------------------------
    @crew
    def crew(self) -> Crew:
        """组装 Crew（sequential 流程）."""
        return Crew(
            agents=self.agents,
            tasks=self.tasks,
            process=Process.sequential,
            verbose=False,
        )

    # ------------------------------------------------------------------
    # 公开入口
    # ------------------------------------------------------------------
    def run(self) -> str:
        """执行完整的新闻采集 + 筛选流程，返回格式化新闻摘要.

        Returns:
            格式化的新闻摘要字符串；若抓取失败则返回错误提示。
        """
        t0 = time.perf_counter()
        log.info(f"[NewsCollectCrew] ⏱ 开始采集，关键词: {self.keywords}")

        # Step 1: 并发抓取原始新闻
        t_fetch = time.perf_counter()
        fetcher = NewsFetcher()
        news_list, source_stats = fetcher.fetch(self.keywords, self.top_n)
        t_fetch_done = time.perf_counter()

        if not news_list:
            log.warning(
                f"[NewsCollectCrew] ⏱ 所有新闻源均未返回数据（抓取耗时 {t_fetch_done - t_fetch:.2f}s）"
            )
            return "未能获取到最新的 AI 相关新闻。请检查网络连接。"

        log.info(
            f"[NewsCollectCrew] ⏱ 抓取完成（{t_fetch_done - t_fetch:.2f}s）: "
            f"{' | '.join(source_stats)}，共 {len(news_list)} 条"
        )

        # Step 2: 将原始数据序列化为文本，供 Agent 筛选
        raw_data = self._format_raw_news(news_list)
        current_date = datetime.now().strftime("%Y-%m-%d")

        # Step 3: CrewAI Agent 筛选（通过 kickoff(inputs=) 注入动态数据）
        t_llm = time.perf_counter()
        try:
            result = self.crew().kickoff(
                inputs={
                    "raw_data": raw_data,
                    "current_date": current_date,
                }
            )
            t_llm_done = time.perf_counter()
            output = str(result).strip()
            log.info(
                f"[NewsCollectCrew] ⏱ LLM 筛选完成（{t_llm_done - t_llm:.2f}s），"
                f"输出 {len(output)} 字符，节点总耗时 {t_llm_done - t0:.2f}s"
            )
            return output
        except Exception as e:
            elapsed = time.perf_counter() - t0
            log.error(
                f"[NewsCollectCrew] ⏱ CrewAI 筛选失败（耗时 {elapsed:.2f}s），降级返回原始数据: {e}"
            )
            # 降级：直接返回格式化的原始抓取结果
            return self._format_fallback(news_list)

    # ------------------------------------------------------------------
    # 内部辅助
    # ------------------------------------------------------------------
    @staticmethod
    def _format_raw_news(news_list: list[dict]) -> str:
        """将新闻列表序列化为供 LLM 阅读的文本格式."""
        lines: list[str] = []
        for i, n in enumerate(news_list, 1):
            lines.append(
                f"{i}. [{n.get('source', '未知')}] {n['title']}\n"
                f"   链接: {n.get('url', '无')}\n"
                f"   热度: {n.get('score', 0)} | 时间: {n.get('time', '未知')}\n"
                f"   摘要: {n.get('summary', '')}"
            )
        return "\n\n".join(lines)

    @staticmethod
    def _format_fallback(news_list: list[dict], top_n: int = 10) -> str:
        """降级输出：直接格式化原始抓取结果（不经过 LLM 筛选）."""
        output = f"## 最新 AI 热门新闻 Top {min(len(news_list), top_n)}\n"
        output += f"数据时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n"
        for i, news in enumerate(news_list[:top_n], 1):
            output += f"### {i}. {news['title']}\n"
            output += f"- **来源**: {news.get('source', '未知')}\n"
            output += f"- **链接**: {news.get('url', '无')}\n"
            output += f"- **热度**: {news.get('score', 0)} 分\n"
            if news.get("summary"):
                output += f"- **摘要**: {news['summary']}\n"
            output += f"- **时间**: {news.get('time', '未知')}\n\n"
        return output
