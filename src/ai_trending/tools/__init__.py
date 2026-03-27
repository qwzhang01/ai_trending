"""AI Trending 工具包 — 懒加载，避免导入时触发重量级依赖."""

from __future__ import annotations

import importlib
import types

__all__ = [
    "GitHubTrendingTool",
    "AINewsTool",
    "GitHubPublishTool",
    "WeChatPublishTool",
]

# 类名 → 子模块映射
_CLASS_MODULE_MAP: dict[str, str] = {
    "GitHubTrendingTool": "ai_trending.tools.github_trending_tool",
    "AINewsTool": "ai_trending.tools.ai_news_tool",
    "GitHubPublishTool": "ai_trending.tools.github_publish_tool",
    "WeChatPublishTool": "ai_trending.tools.wechat_publish_tool",
}

# 子模块名 → 完整模块路径映射（供 unittest.mock.patch 解析路径使用）
_SUBMODULE_MAP: dict[str, str] = {
    "github_trending_tool": "ai_trending.tools.github_trending_tool",
    "ai_news_tool": "ai_trending.tools.ai_news_tool",
    "github_publish_tool": "ai_trending.tools.github_publish_tool",
    "wechat_publish_tool": "ai_trending.tools.wechat_publish_tool",
}


def __getattr__(name: str) -> object:
    if name in _CLASS_MODULE_MAP:
        mod = importlib.import_module(_CLASS_MODULE_MAP[name])
        return getattr(mod, name)
    if name in _SUBMODULE_MAP:
        return importlib.import_module(_SUBMODULE_MAP[name])
    raise AttributeError(f"module 'ai_trending.tools' has no attribute {name!r}")
