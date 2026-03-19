#!/usr/bin/env python
import sys
import warnings
from datetime import datetime

warnings.filterwarnings("ignore", category=SyntaxWarning, module="pysbd")


def run():
    """运行 AI Trending — LangGraph 状态机模式.

    流水线（LangGraph StateGraph）:
    1. [collect_github, collect_news] — 并行数据采集
    2. score_trends — LLM 结构化评分（核心）
    3. write_report — 基于评分生成 Markdown 日报
    4. publish — 推送 GitHub + 微信公众号
    """
    from ai_trending.graph import get_graph

    current_date = datetime.now().strftime("%Y-%m-%d")
    initial_state = {
        "current_date": current_date,
        "author_name": "AI Trending Bot",
        "github_data": "",
        "news_data": "",
        "scoring_result": "",
        "report_content": "",
        "publish_results": [],
        "token_usage": {},
        "errors": [],
    }

    try:
        graph = get_graph()
        final_state = graph.invoke(initial_state)

        report = final_state.get("report_content", "")
        print("\n📊 最终报告预览:\n")
        print(report[:500] if report else "(无报告内容)")
        print("\n...")
        return final_state
    except Exception as e:
        raise Exception(f"运行 AI Trending 时出错: {e}")


def run_with_trigger():
    """通过触发器运行（用于外部调度集成）.

    用法: python -m ai_trending.main '{"key": "value"}'
    """
    import json

    if len(sys.argv) < 2:
        raise Exception("请提供 JSON payload 作为参数")

    try:
        trigger_payload = json.loads(sys.argv[1])
    except json.JSONDecodeError:
        raise Exception("无效的 JSON payload")

    from ai_trending.graph import get_graph

    initial_state = {
        "current_date": trigger_payload.get(
            "current_date", datetime.now().strftime("%Y-%m-%d")
        ),
        "author_name": trigger_payload.get("author_name", "AI Trending Bot"),
        "github_data": "",
        "news_data": "",
        "scoring_result": "",
        "report_content": "",
        "publish_results": [],
        "token_usage": {},
        "errors": [],
    }

    try:
        graph = get_graph()
        final_state = graph.invoke(initial_state)
        return final_state
    except Exception as e:
        raise Exception(f"通过触发器运行时出错: {e}")
