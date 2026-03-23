"""统一 LLM 客户端 — 三级模型调度，供 LangGraph 节点和 CrewAI Agent 共用.

三级调度:
  - light:     数据采集/整理类任务，用便宜小模型
  - default:   分析/评分/写作类任务，用好模型
  - tool_only: 纯工具调用，用最便宜的模型

底层使用 LiteLLM 的 completion API，支持 OpenAI/Claude/Qwen 等 100+ 模型。
"""

from typing import Any

import litellm

from ai_trending.config import load_config
from ai_trending.logger import get_logger

log = get_logger("llm")

# 关闭 litellm 的冗余日志
litellm.suppress_debug_info = True


def _get_tier_config(tier: str) -> dict[str, Any]:
    """根据 tier 返回模型配置."""
    llm = load_config().llm

    configs = {
        "light": {"model": llm.model_light, "temperature": 0.1},
        "default": {"model": llm.model, "temperature": llm.temperature},
        "tool_only": {"model": llm.model_tool, "temperature": 0.0},
    }
    return configs.get(tier, configs["default"])


def call_llm_with_usage(
    prompt: str,
    tier: str = "default",
    system_prompt: str | None = None,
    max_tokens: int = 4096,
    json_mode: bool = False,
) -> tuple[str, dict[str, int]]:
    """调用 LLM 并同时返回文本结果和 Token 用量.

    Returns:
        (content, usage_dict) 其中 usage_dict 包含 prompt_tokens, completion_tokens, total_tokens
    """
    config = _get_tier_config(tier)
    model = config["model"]
    temperature = config["temperature"]

    messages: list[dict[str, str]] = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    kwargs: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }

    llm_cfg = load_config().llm
    if llm_cfg.api_base:
        kwargs["api_base"] = llm_cfg.api_base

    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}

    if llm_cfg.disable_thinking:
        kwargs["extra_body"] = {"thinking": {"type": "disabled"}}

    log.info(f"LLM 调用: tier={tier}, model={model}")

    response = litellm.completion(**kwargs)
    content = response.choices[0].message.content or ""

    usage_info = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    usage = getattr(response, "usage", None)
    if usage:
        usage_info = {
            "prompt_tokens": getattr(usage, "prompt_tokens", 0),
            "completion_tokens": getattr(usage, "completion_tokens", 0),
            "total_tokens": getattr(usage, "total_tokens", 0),
        }

    return content.strip(), usage_info


def build_crewai_llm(tier: str = "default"):
    """构建 CrewAI LLM 实例，供 CrewAI Agent 使用.

    复用 _get_tier_config 的三级调度逻辑，避免与 crew.py 中重复配置。
    若主 MODEL 未配置则返回 None（使用 CrewAI 默认）。

    Args:
        tier: 模型档位 (\"light\" / \"default\" / \"tool_only\")

    Returns:
        CrewAI LLM 实例，或 None（未配置时）
    """
    from crewai import LLM

    llm_cfg = load_config().llm
    if not llm_cfg.model:
        return None

    config = _get_tier_config(tier)
    kwargs: dict = {"model": config["model"], "temperature": config["temperature"]}

    if llm_cfg.api_base:
        kwargs["base_url"] = llm_cfg.api_base

    if llm_cfg.disable_thinking:
        kwargs["extra_body"] = {"thinking": {"type": "disabled"}}
        log.info("已关闭 LLM thinking 模式")

    log.info(f"LLM tier={tier} → model={config['model']}, temperature={config['temperature']}")
    return LLM(**kwargs)
