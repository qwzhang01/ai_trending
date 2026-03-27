"""结构化日志模块 — 控制台彩色输出 + 文件日志轮转."""

import logging
import sys
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path

# 日志目录
LOG_DIR = Path.cwd() / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

# 日志格式
CONSOLE_FORMAT = "%(asctime)s │ %(levelname)-7s │ %(name)-14s │ %(message)s"
FILE_FORMAT = "%(asctime)s | %(levelname)-7s | %(name)-14s | %(funcName)s:%(lineno)d | %(message)s"
DATE_FORMAT = "%H:%M:%S"
FILE_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# 全局初始化标记
_initialized = False


def setup_logging(level: str = "INFO", log_file: str | None = None) -> None:
    """初始化日志系统（只执行一次）."""
    global _initialized
    if _initialized:
        return
    _initialized = True

    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))

    # 清除已有 handler（避免重复）
    root.handlers.clear()

    # 1. 控制台 Handler — 彩色简洁输出
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(logging.INFO)
    console.setFormatter(_ColorFormatter(CONSOLE_FORMAT, DATE_FORMAT))
    root.addHandler(console)

    # 2. 文件 Handler — 详细日志，按大小轮转
    if log_file is None:
        today = datetime.now().strftime("%Y-%m-%d")
        log_file = str(LOG_DIR / f"ai_trending_{today}.log")

    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=10 * 1024 * 1024,  # 10 MB
        backupCount=7,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter(FILE_FORMAT, FILE_DATE_FORMAT))
    root.addHandler(file_handler)

    # 降低第三方库的日志级别
    for noisy in ["httpx", "httpcore", "urllib3", "openai", "litellm", "requests"]:
        logging.getLogger(noisy).setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """获取一个命名日志器. 首次调用时自动初始化日志系统."""
    setup_logging()
    return logging.getLogger(f"ai_trend.{name}")


class _ColorFormatter(logging.Formatter):
    """控制台彩色日志格式化器."""

    COLORS = {
        logging.DEBUG: "\033[36m",  # cyan
        logging.INFO: "\033[32m",  # green
        logging.WARNING: "\033[33m",  # yellow
        logging.ERROR: "\033[31m",  # red
        logging.CRITICAL: "\033[1;31m",  # bold red
    }
    RESET = "\033[0m"

    def format(self, record: logging.LogRecord) -> str:
        color = self.COLORS.get(record.levelno, self.RESET)
        record.levelname = f"{color}{record.levelname}{self.RESET}"
        return super().format(record)
