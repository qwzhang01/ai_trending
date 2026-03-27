"""AI Trending 工具包 — 懒加载，避免导入时触发重量级依赖."""

from __future__ import annotations

__all__ = [
    "GitHubTrendingTool",
    "AINewsTool",
    "GitHubPublishTool",
    "WeChatPublishTool",
]


def __getattr__(name: str):
    if name == "GitHubTrendingTool":
        from ai_trending.tools.github_trending_tool import GitHubTrendingTool
        return GitHubTrendingTool
    if name == "AINewsTool":
        from ai_trending.tools.ai_news_tool import AINewsTool
        return AINewsTool
    if name == "GitHubPublishTool":
        from ai_trending.tools.github_publish_tool import GitHubPublishTool
        return GitHubPublishTool
    if name == "WeChatPublishTool":
        from ai_trending.tools.wechat_publish_tool import WeChatPublishTool
        return WeChatPublishTool
    raise AttributeError(f"module 'ai_trending.tools' has no attribute {name!r}")