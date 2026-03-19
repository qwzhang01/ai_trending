#!/usr/bin/env python
"""AI Trending — 生产环境启动入口.

基于 LangGraph 状态机编排，支持在 PyCharm / 直接 python 运行。

用法:
    python run.py                   # 默认运行（LangGraph 模式）
    python run.py --dry-run         # 只校验配置，不执行
    python run.py --date 2026-03-17 # 指定日期
    python run.py --verbose         # 详细日志
"""

import argparse
import sys
import traceback
from datetime import datetime

from ai_trending.logger import setup_logging, get_logger
from ai_trending.config import load_config, print_startup_banner
from ai_trending.metrics import RunMetrics


def main():
    parser = argparse.ArgumentParser(description="AI Trending — 每日 AI 趋势报告")
    parser.add_argument("--date", default=None, help="指定报告日期 (YYYY-MM-DD)")
    parser.add_argument("--author", default=None, help="作者名称")
    parser.add_argument("--dry-run", action="store_true", help="只校验配置，不执行")
    parser.add_argument("--verbose", action="store_true", help="详细日志")
    args = parser.parse_args()

    # 初始化日志
    setup_logging(level="DEBUG" if args.verbose else "INFO")
    log = get_logger("main")

    # 加载并校验配置
    config = load_config()
    print_startup_banner(config)

    if args.dry_run:
        log.info("✅ 配置校验通过 (--dry-run 模式，不执行)")
        return 0

    # 准备输入
    current_date = args.date or datetime.now().strftime("%Y-%m-%d")
    author_name = args.author or config.author_name

    # 运行指标采集
    metrics = RunMetrics(run_date=current_date)
    metrics.start()

    try:
        # --- LangGraph 模式 ---
        metrics.stage_start("LangGraph 初始化")
        from ai_trending.graph import get_graph
        graph = get_graph()
        metrics.stage_end("LangGraph 初始化")

        # 构建初始状态
        initial_state = {
            "current_date": current_date,
            "author_name": author_name,
            "github_data": "",
            "news_data": "",
            "scoring_result": "",
            "report_content": "",
            "publish_results": [],
            "token_usage": {},
            "errors": [],
        }

        metrics.stage_start("LangGraph 执行")
        final_state = graph.invoke(initial_state)
        metrics.stage_end("LangGraph 执行")

        # 提取结果
        report_content = final_state.get("report_content", "")
        publish_results = final_state.get("publish_results", [])
        token_usage = final_state.get("token_usage", {})
        errors = final_state.get("errors", [])

        # 记录 Token 用量
        if token_usage:
            metrics.token_usage.update({
                "prompt_tokens": token_usage.get("prompt_tokens", 0),
                "completion_tokens": token_usage.get("completion_tokens", 0),
                "total_tokens": token_usage.get("total_tokens", 0),
            })
            import os
            metrics.model_name = os.getenv("MODEL", "unknown")
            from ai_trending.metrics import _estimate_cost
            metrics.estimated_cost = _estimate_cost(
                metrics.model_name,
                metrics.token_usage.get("prompt_tokens", 0),
                metrics.token_usage.get("completion_tokens", 0),
            )

        # 输出预览
        log.info("📊 最终报告预览:")
        preview = report_content[:300] if report_content else "(无报告内容)"
        log.info(preview + "\n...")

        # 输出发布结果
        log.info("📤 发布结果:")
        for r in publish_results:
            log.info(f"  {r}")

        # 输出错误（如果有）
        if errors:
            log.warning(f"⚠️  运行中发生 {len(errors)} 个错误:")
            for e in errors:
                log.warning(f"  - {e}")

        # 标记状态
        if errors and not report_content:
            metrics.finish(status="failed", error="; ".join(errors[:3]))
        else:
            metrics.finish(status="success")

    except KeyboardInterrupt:
        log.warning("⚠️  用户中断执行 (Ctrl+C)")
        metrics.stage_end("LangGraph 执行", status="cancelled", error="用户中断")
        metrics.finish(status="cancelled", error="用户中断")

    except Exception as e:
        log.error(f"❌ 运行失败: {e}")
        log.debug(traceback.format_exc())
        metrics.stage_end("LangGraph 执行", status="failed", error=str(e))
        metrics.finish(status="failed", error=str(e))

    # 无论成功失败，都输出指标汇总、持久化、发送通知
    metrics.print_summary()
    metrics.save()
    metrics.send_webhook()

    return 0 if metrics.status == "success" else (130 if metrics.status == "cancelled" else 1)


if __name__ == "__main__":
    sys.exit(main())
