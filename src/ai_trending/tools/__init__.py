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
    # 支持子模块名访问（供 unittest.mock.patch 解析路径使用）
    if name == "github_trending_tool":
        import ai_trending.tools.github_trending_tool as m

        return m
    if name == "ai_news_tool":
        import ai_trending.tools.ai_news_tool as m

        return m
    if name == "github_publish_tool":
        import ai_trending.tools.github_publish_tool as m

        return m
    if name == "wechat_publish_tool":
        import ai_trending.tools.wechat_publish_tool as m

        return m
    raise AttributeError(f"module 'ai_trending.tools' has no attribute {name!r}")
