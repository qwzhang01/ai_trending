"""运行指标采集与可观测性模块.

提供:
  - RunMetrics: 单次运行的全量指标采集（Token、耗时、费用、Tool 调用）
  - 指标 JSON 持久化（metrics/ 目录）
  - 控制台彩色汇总报告
  - Webhook 通知（可选）
"""

import json
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from ai_trending.logger import get_logger

log = get_logger("metrics")

# 指标存储目录
METRICS_DIR = Path.cwd() / "metrics"

# 常见模型的 Token 单价 (USD / 1M tokens)
# 格式: { "model_keyword": (input_price, output_price) }
MODEL_PRICING: dict[str, tuple[float, float]] = {
    # OpenAI
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4o": (2.50, 10.00),
    "gpt-4-turbo": (10.00, 30.00),
    "gpt-3.5-turbo": (0.50, 1.50),
    "o1-mini": (3.00, 12.00),
    "o1": (15.00, 60.00),
    # Anthropic
    "claude-3-5-sonnet": (3.00, 15.00),
    "claude-sonnet-4": (3.00, 15.00),
    "claude-3-5-haiku": (0.80, 4.00),
    "claude-3-haiku": (0.25, 1.25),
    # Google
    "gemini-2.0-flash": (0.10, 0.40),
    "gemini-1.5-pro": (3.50, 10.50),
    # 开源 / SiliconFlow (大多数按量计费远低于闭源)
    "qwen": (0.10, 0.30),
    "llama": (0.10, 0.30),
    "deepseek": (0.14, 0.28),
    # Moonshot / Kimi (人民币换算，按 7.2 汇率折 USD)
    "moonshot-v1-8k": (0.17, 0.17),  # ¥1.25/1M → ~$0.17
    "moonshot-v1-32k": (0.42, 0.42),  # ¥3/1M → ~$0.42
    "moonshot-v1-128k": (0.83, 0.83),  # ¥6/1M → ~$0.83
    "kimi-k2": (0.83, 2.78),  # ¥6/¥20 per 1M → ~$0.83/$2.78
    "kimi-latest": (0.83, 2.78),
    "moonshot": (0.42, 0.42),  # 通用兜底，按 32k 档估算
    # 百川 / MiniMax / 智谱
    "baichuan": (0.14, 0.14),
    "minimax": (0.14, 0.42),
    "glm": (0.14, 0.14),
    # 字节 / 豆包
    "doubao": (0.04, 0.04),  # 豆包 lite 极低价
    # 阿里 / 通义（SiliconFlow 上的 Qwen 已覆盖，这里补官方 API）
    "qwen-max": (0.56, 2.22),  # ¥4/¥16 per 1M
    "qwen-plus": (0.06, 0.28),  # ¥0.4/¥2 per 1M
    "qwen-turbo": (0.03, 0.06),  # ¥0.2/¥0.4 per 1M
}


def _estimate_cost(model_name: str, input_tokens: int, output_tokens: int) -> float:
    """根据模型名称和 Token 数估算费用 (USD)."""
    model_lower = model_name.lower()
    for keyword, (in_price, out_price) in MODEL_PRICING.items():
        if keyword in model_lower:
            return (input_tokens * in_price + output_tokens * out_price) / 1_000_000
    # 未知模型，用中等价格估算
    return (input_tokens * 1.0 + output_tokens * 3.0) / 1_000_000


class ToolCallRecord:
    """单次 Tool 调用记录."""

    def __init__(self, tool_name: str):
        self.tool_name = tool_name
        self.start_time = time.monotonic()
        self.end_time: float | None = None
        self.status: str = "running"
        self.error: str | None = None
        self.extra: dict[str, Any] = {}

    def finish(
        self, status: str = "success", error: str | None = None, **extra: Any
    ) -> None:
        self.end_time = time.monotonic()
        self.status = status
        self.error = error
        self.extra.update(extra)

    @property
    def elapsed(self) -> float:
        if self.end_time is not None:
            return self.end_time - self.start_time
        return time.monotonic() - self.start_time

    def to_dict(self) -> dict:
        return {
            "tool": self.tool_name,
            "elapsed_sec": round(self.elapsed, 2),
            "status": self.status,
            "error": self.error,
            **self.extra,
        }


class RunMetrics:
    def __init__(self, run_date: str | None = None):
        self.run_date = run_date or datetime.now().strftime("%Y-%m-%d")
        self.run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.start_time: float | None = None
        self.end_time: float | None = None
        self.stages: list[dict] = []
        self.tool_calls: list[ToolCallRecord] = []

        # Token 用量 (从 CrewOutput.token_usage 提取)
        self.token_usage: dict[str, int] = {
            "total_tokens": 0,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "successful_requests": 0,
        }
        self.model_name: str = ""
        self.estimated_cost: float = 0.0

        # 最终状态
        self.status: str = (
            "pending"  # pending -> running -> success / failed / cancelled
        )
        self.error: str | None = None

    def start(self) -> None:
        self.start_time = time.monotonic()
        self.status = "running"

    def finish(self, status: str = "success", error: str | None = None) -> None:
        self.end_time = time.monotonic()
        self.status = status
        self.error = error

    @property
    def total_elapsed(self) -> float:
        if self.start_time is None:
            return 0
        end = self.end_time or time.monotonic()
        return end - self.start_time

    # ---------- 阶段追踪 ----------

    def stage_start(self, name: str) -> None:
        self.stages.append(
            {
                "name": name,
                "start": time.monotonic(),
                "end": None,
                "status": "running",
                "error": None,
            }
        )
        log.info(f"▶️  阶段开始: {name}")

    def stage_end(
        self, name: str, status: str = "success", error: str | None = None
    ) -> None:
        for stage in reversed(self.stages):
            if stage["name"] == name and stage["status"] == "running":
                stage["end"] = time.monotonic()
                stage["status"] = status
                stage["error"] = error
                elapsed = stage["end"] - stage["start"]
                if status == "success":
                    log.info(f"✅ 阶段完成: {name} ({elapsed:.1f}s)")
                else:
                    log.error(f"❌ 阶段失败: {name} ({elapsed:.1f}s) — {error}")
                break

    # ---------- Tool 调用追踪 ----------

    def tool_start(self, tool_name: str) -> ToolCallRecord:
        rec = ToolCallRecord(tool_name)
        self.tool_calls.append(rec)
        return rec

    # ---------- 汇总报告 ----------

    def to_dict(self) -> dict:
        """生成完整指标字典（用于 JSON 持久化）."""
        return {
            "run_id": self.run_id,
            "run_date": self.run_date,
            "timestamp": datetime.now().isoformat(),
            "status": self.status,
            "error": self.error,
            "total_elapsed_sec": round(self.total_elapsed, 2),
            "model": self.model_name,
            "token_usage": self.token_usage,
            "estimated_cost_usd": round(self.estimated_cost, 6),
            "stages": [
                {
                    "name": s["name"],
                    "elapsed_sec": round(s["end"] - s["start"], 2)
                    if s["end"] and s["start"]
                    else None,
                    "status": s["status"],
                    "error": s["error"],
                }
                for s in self.stages
            ],
            "tool_calls": [tc.to_dict() for tc in self.tool_calls],
        }

    def save(self) -> Path:
        """将指标保存为 JSON 文件."""
        METRICS_DIR.mkdir(parents=True, exist_ok=True)
        filepath = METRICS_DIR / f"{self.run_id}.json"
        filepath.write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=2))
        log.info(f"📁 指标已保存: {filepath}")
        return filepath

    def print_summary(self) -> str:
        """在控制台输出彩色汇总报告."""
        d = self.to_dict()
        status_icon = {"success": "✅", "failed": "❌", "cancelled": "⚠️"}.get(
            d["status"], "❓"
        )

        lines = [
            "",
            "╔══════════════════════════════════════════════════════════════╗",
            "║                  📊 运行指标汇总报告                        ║",
            "╠══════════════════════════════════════════════════════════════╣",
            f"║  运行 ID:   {d['run_id']}",
            f"║  日期:      {d['run_date']}",
            f"║  状态:      {status_icon} {d['status'].upper()}",
            f"║  总耗时:    {d['total_elapsed_sec']:.1f}s",
        ]

        if d["error"]:
            lines.append(f"║  错误:      {d['error'][:50]}")

        # Token 用量
        tu = d["token_usage"]
        if tu.get("total_tokens", 0) > 0:
            lines.extend(
                [
                    "║",
                    "║  ── Token 用量 ──────────────────────────────────",
                    f"║  模型:          {d['model']}",
                    f"║  Prompt:        {tu.get('prompt_tokens', 0):,} tokens",
                    f"║  Completion:    {tu.get('completion_tokens', 0):,} tokens",
                    f"║  合计:          {tu.get('total_tokens', 0):,} tokens",
                    f"║  请求数:        {tu.get('successful_requests', 0)}",
                    f"║  💰 预估费用:   ${d['estimated_cost_usd']:.4f}",
                ]
            )

        # 阶段耗时
        if d["stages"]:
            lines.extend(
                [
                    "║",
                    "║  ── 阶段耗时 ──────────────────────────────────",
                ]
            )
            for s in d["stages"]:
                icon = "✅" if s["status"] == "success" else "❌"
                elapsed = (
                    f"{s['elapsed_sec']:.1f}s"
                    if s["elapsed_sec"] is not None
                    else "N/A"
                )
                lines.append(f"║  {icon} {s['name']:<20s}  {elapsed}")
                if s["error"]:
                    lines.append(f"║     └─ {s['error'][:50]}")

        # Tool 调用
        if d["tool_calls"]:
            lines.extend(
                [
                    "║",
                    "║  ── Tool 调用 ──────────────────────────────────",
                ]
            )
            for tc in d["tool_calls"]:
                icon = "✅" if tc["status"] == "success" else "❌"
                lines.append(f"║  {icon} {tc['tool']:<24s}  {tc['elapsed_sec']:.1f}s")
                if tc.get("error"):
                    lines.append(f"║     └─ {tc['error'][:50]}")

        lines.append("╚══════════════════════════════════════════════════════════════╝")

        summary_text = "\n".join(lines)
        log.info(summary_text)
        return summary_text

    # ---------- Webhook 通知 ----------

    def send_webhook(self, force: bool = False) -> None:
        """发送运行结果通知到 Webhook（仅在失败时或 force=True 时）.

        支持的环境变量:
          WEBHOOK_URL       — Webhook 地址（支持企业微信、飞书、Slack、自定义）
          WEBHOOK_ON_SUCCESS — 设为 "true" 则成功时也发通知
        """
        webhook_url = os.getenv("WEBHOOK_URL", "")
        if not webhook_url:
            return

        # 默认只在失败时发通知
        notify_on_success = os.getenv("WEBHOOK_ON_SUCCESS", "").lower() == "true"
        if self.status == "success" and not notify_on_success and not force:
            return

        try:
            import requests as req  # type: ignore[import-untyped]

            status_icon = {"success": "✅", "failed": "❌", "cancelled": "⚠️"}.get(
                self.status, "❓"
            )
            tu = self.token_usage
            total_tokens = tu.get("total_tokens", 0)

            # 构建通知文本
            text_parts = [
                f"{status_icon} **AI Trending 运行报告**",
                f"- 日期: {self.run_date}",
                f"- 状态: {self.status.upper()}",
                f"- 耗时: {self.total_elapsed:.1f}s",
            ]
            if total_tokens > 0:
                text_parts.append(
                    f"- Token: {total_tokens:,} (≈${self.estimated_cost:.4f})"
                )
            if self.error:
                text_parts.append(f"- 错误: {self.error[:200]}")

            # Tool 调用摘要
            failed_tools = [tc for tc in self.tool_calls if tc.status == "failed"]
            if failed_tools:
                text_parts.append(
                    f"- 失败 Tool: {', '.join(tc.tool_name for tc in failed_tools)}"
                )

            text = "\n".join(text_parts)

            # 自动适配不同 Webhook 格式
            payload = _build_webhook_payload(webhook_url, text)

            resp = req.post(webhook_url, json=payload, timeout=10)
            if resp.ok:
                log.info("📨 Webhook 通知已发送")
            else:
                log.warning(
                    f"⚠️  Webhook 发送失败: {resp.status_code} {resp.text[:100]}"
                )

        except Exception as e:
            log.warning(f"⚠️  Webhook 发送异常: {e}")


def _build_webhook_payload(url: str, text: str) -> dict:
    """根据 Webhook URL 自动适配不同平台的 payload 格式."""
    if "qyapi.weixin.qq.com" in url:
        # 企业微信机器人
        return {
            "msgtype": "markdown",
            "markdown": {"content": text},
        }
    elif "open.feishu.cn" in url:
        # 飞书机器人
        return {
            "msg_type": "interactive",
            "card": {
                "elements": [{"tag": "markdown", "content": text}],
                "header": {
                    "title": {"tag": "plain_text", "content": "AI Trending 运行通知"}
                },
            },
        }
    elif "hooks.slack.com" in url:
        # Slack Webhook
        return {"text": text}
    elif "oapi.dingtalk.com" in url:
        # 钉钉机器人
        return {
            "msgtype": "markdown",
            "markdown": {"title": "AI Trending 运行通知", "text": text},
        }
    else:
        # 通用 JSON
        return {"text": text, "content": text}
