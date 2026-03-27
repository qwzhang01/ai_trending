"""LangGraph 状态机 — AI Trending 流程编排引擎.

替代 CrewAI 的 Sequential Pipeline，使用 LangGraph StateGraph 实现:
  - 显式状态流转（可调试、可追溯）
  - 并行数据采集（GitHub + News 并发执行）
  - 条件分支（高分项目可深入分析，低分跳过）
  - 每个节点职责单一，输入输出明确

流程:
  START → [collect_github, collect_news] (并行) → score_trends → write_report → publish → END
"""

from __future__ import annotations

import operator
from typing import Annotated, TypedDict

from langgraph.graph import END, START, StateGraph

from ai_trending.logger import get_logger

log = get_logger("graph")


# ==================== 状态定义 ====================


class TrendingState(TypedDict, total=False):
    """LangGraph 全局状态 — 在节点间流转的数据.

    每个节点读取需要的字段，写入自己负责的字段。
    """

    # --- 输入参数 ---
    current_date: str  # 报告日期 (YYYY-MM-DD)
    author_name: str  # 作者名称

    # --- 数据采集层输出 ---
    github_data: str  # GitHub 热门项目文本（由 collect_github 节点写入）
    news_data: str  # 行业新闻文本（由 collect_news 节点写入）

    # --- 评分层输出 ---
    scoring_result: str  # 结构化 JSON 评分（由 score_trends 节点写入）

    # --- 报告层输出 ---
    report_content: str  # 最终 Markdown 报告（由 write_report 节点写入）

    # --- 发布层输出 ---
    publish_results: Annotated[
        list[str], operator.add
    ]  # 发布结果列表（由 publish 节点追加）

    # --- 可观测性 ---
    token_usage: dict  # 累计 Token 用量
    errors: Annotated[list[str], operator.add]  # 错误记录（追加模式）


# ==================== 构建流程图 ====================


def build_graph() -> StateGraph:
    """构建并返回 AI Trending 的 LangGraph 流程图.

    Returns:
        编译好的 StateGraph 实例，可直接 .invoke() 调用
    """
    from ai_trending.nodes import (
        collect_github_node,
        collect_news_node,
        publish_node,
        score_trends_node,
        write_report_node,
    )

    graph = StateGraph(TrendingState)

    # 注册节点
    graph.add_node("collect_github", collect_github_node)
    graph.add_node("collect_news", collect_news_node)
    graph.add_node("score_trends", score_trends_node)
    graph.add_node("write_report", write_report_node)
    graph.add_node("publish", publish_node)

    # 定义边：从 START 并行进入两个采集节点
    graph.add_edge(START, "collect_github")
    graph.add_edge(START, "collect_news")

    # 两个采集节点完成后，进入评分节点
    graph.add_edge("collect_github", "score_trends")
    graph.add_edge("collect_news", "score_trends")

    # 评分 → 写报告 → 发布 → 结束
    graph.add_edge("score_trends", "write_report")
    graph.add_edge("write_report", "publish")
    graph.add_edge("publish", END)

    log.info(
        "LangGraph 流程图构建完成: START → [collect_github, collect_news] → score_trends → write_report → publish → END"
    )

    return graph.compile()


def get_graph():
    """获取编译好的流程图（单例模式，避免重复编译）."""
    if not hasattr(get_graph, "_instance"):
        get_graph._instance = build_graph()
    return get_graph._instance
