"""GitHub Trending Crew — 对外入口。

使用方式：
  1. 独立 Agent 运行（命令行 / 脚本）：
       from ai_trending.crew.github_trending import GitHubTrendingOrchestrator
       text = GitHubTrendingOrchestrator().run_as_agent(query="AI", top_n=5)
       print(text)

     或直接执行模块：
       python -m ai_trending.crew.github_trending.crew

  2. 作为 LangGraph Tool 使用（推荐）：
       from ai_trending.crew.github_trending import create_langgraph_tool
       tool = create_langgraph_tool()
       result = tool.invoke({"query": "AI", "top_n": 5})

  3. 获取原始数据元组：
       from ai_trending.crew.github_trending import GitHubTrendingOrchestrator
       repos, summary, hot_signals, keywords = GitHubTrendingOrchestrator().run(query="AI")
"""

from ai_trending.crew.github_trending.crew import (
    GitHubTrendingOrchestrator,
    create_langgraph_tool,
)

__all__ = [
    "GitHubTrendingOrchestrator",
    "create_langgraph_tool",  # LangGraph 推荐入口
]
