#!/usr/bin/env python
"""AI Trending — 生产环境启动入口.

等效于 `crewai run`，同时支持在 PyCharm / 直接 python 运行。

用法:
    python run.py                   # 默认运行
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
from ai_trending.crew import AiTrending
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
    inputs = {
        "current_date": current_date,
        "author_name": author_name,
    }

    # 运行指标采集
    metrics = RunMetrics(run_date=current_date)
    metrics.start()

    try:
        metrics.stage_start("Crew 初始化")
        ai_trending = AiTrending()
        # 注入 metrics 到 Crew 实例，供 after_kickoff 使用
        ai_trending._metrics = metrics  # type: ignore[attr-defined]
        crew_instance = ai_trending.crew()
        metrics.stage_end("Crew 初始化")

        metrics.stage_start("Crew 执行")
        result = crew_instance.kickoff(inputs=inputs)
        metrics.stage_end("Crew 执行")

        # 从 CrewOutput 提取 Token 用量和费用
        metrics.collect_crew_result(result)

        log.info("📊 最终报告预览:")
        preview = result.raw[:300] if hasattr(result, "raw") else str(result)[:300]
        log.info(preview + "\n...")

        # 标记成功
        metrics.finish(status="success")

    except KeyboardInterrupt:
        log.warning("⚠️  用户中断执行 (Ctrl+C)")
        metrics.stage_end("Crew 执行", status="cancelled", error="用户中断")
        metrics.finish(status="cancelled", error="用户中断")

    except Exception as e:
        log.error(f"❌ 运行失败: {e}")
        log.debug(traceback.format_exc())
        metrics.stage_end("Crew 执行", status="failed", error=str(e))
        metrics.finish(status="failed", error=str(e))

    # 无论成功失败，都输出指标汇总、持久化、发送通知
    metrics.print_summary()
    metrics.save()
    metrics.send_webhook()

    return 0 if metrics.status == "success" else (130 if metrics.status == "cancelled" else 1)


if __name__ == "__main__":
    sys.exit(main())
