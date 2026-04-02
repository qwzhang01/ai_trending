"""统一 LLM 客户端 — 三级模型调度，供 LangGraph 节点和 CrewAI Agent 共用.

三级调度:
  - light:     数据采集/整理类任务，用便宜小模型
  - default:   分析/评分/写作类任务，用好模型
  - tool_only: 纯工具调用，用最便宜的模型

底层使用 LiteLLM 的 completion API，支持 OpenAI/Claude/Qwen 等 100+ 模型。
"""

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from crewai import LLM

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

    try:
        response = litellm.completion(**kwargs)
    except litellm.BadRequestError as e:
        # 部分模型（如火山引擎 doubao 系列）不支持 response_format=json_object
        # 自动降级：去掉 response_format 参数重试，依赖 prompt 中的 JSON 约束
        if json_mode and "response_format" in str(e):
            log.warning(
                f"模型不支持 json_object 格式，降级重试（依赖 prompt 约束）: {e}"
            )
            kwargs.pop("response_format", None)
            response = litellm.completion(**kwargs)
        else:
            raise
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


# 不支持 tool_choice 指定具体函数名的模型关键词列表
# 这些模型在 CrewAI 使用 output_pydantic 时会报错：
# "Specifying functions for tool_choice is not yet supported"
_MODELS_WITHOUT_TOOL_CHOICE_FUNCTION = [
    "kimi",
    "moonshot",
    "moonshotai",
]


def _model_supports_tool_choice_function(model_name: str) -> bool:
    """判断模型是否支持 tool_choice 指定具体函数名.

    部分模型（如 Kimi-K2.5）不支持 tool_choice={"type": "function", "function": {...}}，
    CrewAI 在使用 output_pydantic 时会自动传递此参数，导致报错。

    Args:
        model_name: LiteLLM 格式的模型名称，如 "Pro/moonshotai/Kimi-K2.5"

    Returns:
        True 表示支持，False 表示不支持（需要兼容处理）
    """
    model_lower = model_name.lower()
    return not any(kw in model_lower for kw in _MODELS_WITHOUT_TOOL_CHOICE_FUNCTION)


def build_crewai_llm(tier: str = "default") -> "LLM | None":
    """构建 CrewAI LLM 实例，供 CrewAI Agent 使用.

    复用 _get_tier_config 的三级调度逻辑，避免与 crew.py 中重复配置。
    若主 MODEL 未配置则返回 None（使用 CrewAI 默认）。

    对不支持 tool_choice 指定函数名的模型（如 Kimi-K2.5），自动启用
    LiteLLM 的 drop_params=True，丢弃不兼容参数，避免 BadRequestError。

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
    model_name: str = config["model"]
    kwargs: dict = {"model": model_name, "temperature": config["temperature"]}

    if llm_cfg.api_base:
        kwargs["base_url"] = llm_cfg.api_base

    if llm_cfg.disable_thinking:
        kwargs["extra_body"] = {"thinking": {"type": "disabled"}}
        log.info("已关闭 LLM thinking 模式")

    # 兼容不支持 tool_choice 指定函数名的模型（如 Kimi-K2.5）
    # CrewAI 使用 output_pydantic 时会传递 tool_choice={"type":"function",...}
    # drop_params=True 让 LiteLLM 自动丢弃模型不支持的参数，避免 BadRequestError
    if not _model_supports_tool_choice_function(model_name):
        kwargs["drop_params"] = True
        log.info(
            f"模型 {model_name} 不支持 tool_choice 指定函数，已启用 drop_params 兼容模式"
        )

    log.info(
        f"LLM tier={tier} → model={model_name}, temperature={config['temperature']}"
    )
    return LLM(**kwargs)
