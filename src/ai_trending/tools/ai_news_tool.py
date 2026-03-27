"""AI News Tool — 触发层.

实际的抓取逻辑和 LLM 筛选已下沉到 crew/new_collect 包中，
本工具只负责作为 CrewAI BaseTool 接口，触发 NewsCollectCrew 并返回结果。

同时继承 NewsFetcher，以便测试可以直接测试抓取方法。
"""

from crewai.tools import BaseTool
from pydantic import BaseModel, Field

from ai_trending.crew.new_collect import NewsCollectCrew
from ai_trending.crew.new_collect.fetchers import NewsFetcher
from ai_trending.logger import get_logger

log = get_logger("news_tool")


class AINewsInput(BaseModel):
    """Input schema for AINewsTool."""

    keywords: str = Field(
        default="AI,LLM,AI Agent",
        description="逗号分隔的搜索关键词，例如 'AI,LLM,AI Agent,大模型'",
    )
    top_n: int = Field(
        default=10,
        description="返回前 N 条最相关的新闻，默认 10",
    )


class AINewsTool(BaseTool, NewsFetcher):
    """触发 NewsCollectCrew 抓取并筛选最新 AI 大模型相关新闻.

    继承 NewsFetcher，提供底层抓取方法（_fetch_hacker_news、_fetch_reddit_rss 等），
    同时通过 _run 方法触发 NewsCollectCrew 完成 LLM 筛选。
    """

    name: str = "ai_news_tool"
    description: str = (
        "从 Hacker News、Reddit、newsdata.io 和知乎等来源抓取最新的 AI、大模型、AI Agent 相关新闻，"
        "并由 AI 分析师 Agent 筛选出最有价值的内容。"
        "返回新闻标题、摘要、来源和链接。"
    )
    args_schema: type[BaseModel] = AINewsInput

    def _run(self, keywords: str = "AI,LLM,AI Agent", top_n: int = 10) -> str:
        """触发 NewsCollectCrew，返回格式化的新闻摘要."""
        keyword_list = [k.strip() for k in keywords.split(",") if k.strip()]
        log.info(f"[AINewsTool] 触发 NewsCollectCrew，关键词: {keyword_list}")

        try:
            result = NewsCollectCrew(keywords=keyword_list, top_n=top_n).run()
            return result
        except Exception as e:
            log.error(f"[AINewsTool] NewsCollectCrew 执行失败: {e}")
            return f"❌ 新闻采集失败: {e}"
