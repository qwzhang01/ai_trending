"""crew/new_collect — AI 新闻采集与筛选 Crew 包.

对外只暴露 NewsCollectCrew，调用方无需关心内部抓取器实现。

使用示例::

    from ai_trending.crew.new_collect import NewsCollectCrew

    summary = NewsCollectCrew(keywords=["AI", "LLM", "大模型"]).run()
"""

from ai_trending.crew.new_collect.crew import NewsCollectCrew

__all__ = ["NewsCollectCrew"]
