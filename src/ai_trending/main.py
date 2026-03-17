#!/usr/bin/env python
"""AI Trending — 每日 AI 开源项目与新闻聚合报告系统.

使用方式:
    crewai run          — 生成今日 AI 趋势报告
    crewai train        — 训练 Crew
    crewai test         — 测试 Crew 执行效果
"""

import sys
import warnings
from datetime import datetime

from ai_trending.crew import AiTrending

warnings.filterwarnings("ignore", category=SyntaxWarning, module="pysbd")


def run():
    """
    运行 AI Trending Crew，生成今日报告.

    流水线:
    1. GitHub 趋势研究员 → 抓取热门 AI 开源项目
    2. AI 新闻分析师 → 搜集 AI 行业新闻
    3. 报告撰写专家 → 整合为完整报告
    4. 发布专员 → 推送 GitHub + 生成微信文章
    """
    inputs = {
        "current_date": datetime.now().strftime("%Y-%m-%d"),
        "author_name": "AI Trending Bot",
    }

    try:
        result = AiTrending().crew().kickoff(inputs=inputs)
        print("\n📊 最终报告预览:\n")
        print(result.raw[:500] if hasattr(result, "raw") else str(result)[:500])
        print("\n...")
        return result
    except Exception as e:
        raise Exception(f"运行 AI Trending Crew 时出错: {e}")


def train():
    """
    训练 Crew.

    用法: crewai train -n <iterations> -f <filename>
    """
    inputs = {
        "current_date": datetime.now().strftime("%Y-%m-%d"),
        "author_name": "AI Trending Bot",
    }
    try:
        AiTrending().crew().train(
            n_iterations=int(sys.argv[1]),
            filename=sys.argv[2],
            inputs=inputs,
        )
    except Exception as e:
        raise Exception(f"训练 Crew 时出错: {e}")


def replay():
    """
    从指定任务重放执行.

    用法: crewai replay -t <task_id>
    """
    try:
        AiTrending().crew().replay(task_id=sys.argv[1])
    except Exception as e:
        raise Exception(f"重放执行时出错: {e}")


def test():
    """
    测试 Crew 执行效果.

    用法: crewai test -n <iterations> -m <eval_model>
    """
    inputs = {
        "current_date": datetime.now().strftime("%Y-%m-%d"),
        "author_name": "AI Trending Bot",
    }
    try:
        AiTrending().crew().test(
            n_iterations=int(sys.argv[1]),
            eval_llm=sys.argv[2],
            inputs=inputs,
        )
    except Exception as e:
        raise Exception(f"测试 Crew 时出错: {e}")


def run_with_trigger():
    """
    通过触发器运行 Crew（用于外部调度集成）.

    用法: python -m ai_trending.main '{"key": "value"}'
    """
    import json

    if len(sys.argv) < 2:
        raise Exception("请提供 JSON payload 作为参数")

    try:
        trigger_payload = json.loads(sys.argv[1])
    except json.JSONDecodeError:
        raise Exception("无效的 JSON payload")

    inputs = {
        "crewai_trigger_payload": trigger_payload,
        "current_date": trigger_payload.get(
            "current_date", datetime.now().strftime("%Y-%m-%d")
        ),
        "author_name": trigger_payload.get("author_name", "AI Trending Bot"),
    }

    try:
        result = AiTrending().crew().kickoff(inputs=inputs)
        return result
    except Exception as e:
        raise Exception(f"通过触发器运行 Crew 时出错: {e}")
