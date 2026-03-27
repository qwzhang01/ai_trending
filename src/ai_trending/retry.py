"""通用重试与降级机制 — 生产环境必备的网络调用保护."""

import functools
import time
from collections.abc import Callable
from typing import Any, TypeVar

import requests  # type: ignore[import-untyped]

from ai_trending.logger import get_logger

log = get_logger("retry")

T = TypeVar("T")


def retry_on_failure(
    max_retries: int = 3,
    backoff_base: float = 2.0,
    retry_on: tuple[type[Exception], ...] = (
        requests.ConnectionError,
        requests.Timeout,
        requests.HTTPError,
    ),
    fallback: Any = None,
    operation_name: str = "",
) -> Callable:
    """带指数退避的重试装饰器.

    Args:
        max_retries: 最大重试次数
        backoff_base: 退避基数（秒），实际等待 = backoff_base ** attempt
        retry_on: 需要重试的异常类型
        fallback: 全部失败后的返回值
        operation_name: 操作名称（用于日志）
    """

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            name = operation_name or func.__name__
            last_exception = None

            for attempt in range(1, max_retries + 1):
                try:
                    result = func(*args, **kwargs)
                    if attempt > 1:
                        log.info(f"✅ {name} 第 {attempt} 次重试成功")
                    return result
                except retry_on as e:
                    last_exception = e
                    if attempt < max_retries:
                        wait = backoff_base**attempt
                        log.warning(
                            f"⚠️  {name} 第 {attempt}/{max_retries} 次失败: {e.__class__.__name__}: {e}. "
                            f"{wait:.0f}s 后重试..."
                        )
                        time.sleep(wait)
                    else:
                        log.error(f"❌ {name} 全部 {max_retries} 次重试均失败: {e}")

            if fallback is not None:
                log.warning(f"🔄 {name} 使用降级返回值")
                return fallback
            raise last_exception  # type: ignore[misc]

        return wrapper

    return decorator


def safe_request(
    method: str,
    url: str,
    timeout: int = 15,
    max_retries: int = 3,
    operation_name: str = "",
    **kwargs: Any,
) -> requests.Response | None:
    """安全的 HTTP 请求封装 — 带重试、超时、错误处理.

    Returns:
        Response 对象，或在全部失败时返回 None
    """
    name = operation_name or f"{method.upper()} {url[:60]}"

    for attempt in range(1, max_retries + 1):
        try:
            resp = requests.request(method, url, timeout=timeout, **kwargs)

            # 对于 429 (Rate Limit)，特殊处理
            if resp.status_code == 429:
                if attempt >= max_retries:
                    log.warning(
                        f"⚠️  {name} 触发速率限制，已达最大重试次数({max_retries})，跳过"
                    )
                    return None
                retry_after = int(resp.headers.get("Retry-After", 60))
                log.warning(f"⚠️  {name} 触发速率限制，等待 {retry_after}s...")
                time.sleep(retry_after)
                continue

            resp.raise_for_status()
            return resp

        except requests.Timeout:
            log.warning(f"⚠️  {name} 超时(attempt {attempt}/{max_retries})")
        except requests.ConnectionError as e:
            log.warning(f"⚠️  {name} 连接错误(attempt {attempt}/{max_retries}): {e}")
        except requests.HTTPError as e:
            status = resp.status_code  # type: ignore[possibly-undefined]
            # 4xx 客户端错误一般不需要重试（除了 429）
            if status < 500:
                if status == 422:
                    # 422 Unprocessable Entity — 请求参数有误，重试无意义
                    log.error(f"❌ {name} 参数错误(422)，不重试: {e}")
                else:
                    log.error(f"❌ {name} 客户端错误 {status}: {e}")
                return None
            log.warning(f"⚠️  {name} 服务端错误(attempt {attempt}/{max_retries}): {e}")

        if attempt < max_retries:
            wait = 2**attempt
            time.sleep(wait)

    log.error(f"❌ {name} 全部 {max_retries} 次请求均失败")
    return None
