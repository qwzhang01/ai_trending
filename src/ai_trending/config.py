"""集中化配置管理 — 环境变量校验、默认值、启动前检查."""

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv


@dataclass
class LLMConfig:
    """LLM 相关配置."""

    model: str = "openai/gpt-4o"
    model_light: str = ""  # 轻量模型，留空则回退到 model
    model_tool: str = ""  # 工具调用模型，留空则回退到 model_light
    api_key: str = ""
    api_base: str = ""
    temperature: float = 0.1  # 生产环境用低温度，减少幻觉
    max_tokens: int = 4096
    disable_thinking: bool = False  # 对推理模型关闭 thinking 模式


@dataclass
class GitHubConfig:
    """GitHub 相关配置."""

    token: str = ""
    report_repo: str = ""

    @property
    def is_publish_ready(self) -> bool:
        return bool(self.token and self.report_repo)


@dataclass
class NewsConfig:
    """新闻 API 配置."""

    newsdata_api_key: str = ""

    @property
    def has_newsdata(self) -> bool:
        return bool(self.newsdata_api_key)


@dataclass
class WeChatConfig:
    """微信公众号相关配置."""

    app_id: str = ""
    app_secret: str = ""
    thumb_media_id: str = ""  # 封面图素材 media_id，可留空（运行时自动上传）

    @property
    def is_enabled(self) -> bool:
        """是否已配置微信公众号（AppID + AppSecret 均不为空）."""
        return bool(self.app_id and self.app_secret)


@dataclass
class AppConfig:
    """应用全局配置."""

    # 子配置
    llm: LLMConfig = field(default_factory=LLMConfig)
    github: GitHubConfig = field(default_factory=GitHubConfig)
    news: NewsConfig = field(default_factory=NewsConfig)
    wechat: WeChatConfig = field(default_factory=WeChatConfig)

    # 运行参数
    verbose: bool = True
    max_retries: int = 3
    request_timeout: int = 30
    author_name: str = "AI Trending Bot"

    # 路径
    project_root: Path = field(default_factory=lambda: Path.cwd())
    reports_dir: Path = field(default_factory=lambda: Path.cwd() / "reports")
    output_dir: Path = field(default_factory=lambda: Path.cwd() / "output")
    log_dir: Path = field(default_factory=lambda: Path.cwd() / "logs")


def load_config() -> AppConfig:
    """从环境变量加载配置并返回 AppConfig 实例."""
    load_dotenv()

    default_model = os.getenv("MODEL", "openai/gpt-4o")
    light_model = os.getenv("MODEL_LIGHT", "") or default_model

    config = AppConfig(
        llm=LLMConfig(
            model=os.getenv("MODEL", "openai/gpt-4o"),
            model_light=os.getenv("MODEL_LIGHT", "") or default_model,
            model_tool=os.getenv("MODEL_TOOL", "") or light_model,
            api_key=os.getenv("OPENAI_API_KEY", ""),
            api_base=os.getenv("OPENAI_API_BASE", ""),
            temperature=float(os.getenv("LLM_TEMPERATURE", "0.1")),
            max_tokens=int(os.getenv("LLM_MAX_TOKENS", "4096")),
            disable_thinking=os.getenv("LLM_DISABLE_THINKING", "").lower() == "true",
        ),
        github=GitHubConfig(
            token=os.getenv("GITHUB_TRENDING_TOKEN", ""),
            report_repo=os.getenv("GITHUB_REPORT_REPO", ""),
        ),
        news=NewsConfig(
            newsdata_api_key=os.getenv("NEWSDATA_API_KEY", ""),
        ),
        wechat=WeChatConfig(
            app_id=os.getenv("WECHAT_APP_ID", ""),
            app_secret=os.getenv("WECHAT_APP_SECRET", ""),
            thumb_media_id=os.getenv("WECHAT_THUMB_MEDIA_ID", ""),
        ),
        verbose=os.getenv("CREW_VERBOSE", "true").lower() == "true",
        max_retries=int(os.getenv("MAX_RETRIES", "3")),
        request_timeout=int(os.getenv("REQUEST_TIMEOUT", "30")),
        author_name=os.getenv("AUTHOR_NAME", "AI Trending Bot"),
    )

    # 确保输出目录存在
    config.reports_dir.mkdir(parents=True, exist_ok=True)
    config.output_dir.mkdir(parents=True, exist_ok=True)
    config.log_dir.mkdir(parents=True, exist_ok=True)

    return config


def validate_config(config: AppConfig) -> list[str]:
    """校验配置，返回警告列表. 空列表表示一切正常."""
    warnings: list[str] = []

    # 必须项
    if not config.llm.api_key:
        warnings.append("❌ [必需] OPENAI_API_KEY 未设置，LLM 将无法调用")

    # 推荐项
    if not config.github.token:
        warnings.append(
            "⚠️  [推荐] GITHUB_TRENDING_TOKEN 未设置，GitHub API 速率受限(60次/小时)，报告无法推送"
        )
    elif not config.github.report_repo:
        warnings.append("⚠️  [可选] GITHUB_REPORT_REPO 未设置，报告将只保存到本地")

    if not config.news.has_newsdata:
        warnings.append(
            "⚠️  [可选] NEWSDATA_API_KEY 未设置，新闻源将只有 Hacker News + Reddit"
        )

    # 微信公众号（可选）
    if not config.wechat.is_enabled:
        warnings.append(
            "⚠️  [可选] WECHAT_APP_ID / WECHAT_APP_SECRET 未设置，将跳过微信草稿箱发布"
        )
    elif not config.wechat.thumb_media_id:
        warnings.append(
            "ℹ️  [可选] WECHAT_THUMB_MEDIA_ID 未设置，将在运行时自动上传封面图"
        )

    return warnings


def print_startup_banner(config: AppConfig) -> None:
    """打印启动信息面板."""
    from ai_trending.logger import get_logger

    log = get_logger("config")
    log.info("=" * 60)
    log.info("🚀 AI Trending — 每日 AI 开源项目与新闻聚合报告")
    log.info("=" * 60)
    log.info(f"  LLM 模型   : {config.llm.model}")
    log.info(f"  API Base   : {config.llm.api_base or '(默认)'}")
    log.info(f"  Temperature: {config.llm.temperature}")
    log.info(
        f"  GitHub 推送 : {'✅ 已配置' if config.github.is_publish_ready else '❌ 未配置(本地保存)'}"
    )
    log.info(
        f"  Newsdata.io: {'✅ 已配置' if config.news.has_newsdata else '❌ 未配置'}"
    )
    log.info(
        f"  微信公众号 : {'✅ 已配置' if config.wechat.is_enabled else '❌ 未配置(跳过草稿箱)'}"
    )
    log.info(f"  报告目录   : {config.reports_dir}")
    log.info(f"  输出目录   : {config.output_dir}")
    log.info("=" * 60)

    # 打印警告
    warnings = validate_config(config)
    for w in warnings:
        log.warning(w)

    # 如果有致命缺失，退出
    fatal = [w for w in warnings if w.startswith("❌")]
    if fatal:
        log.error("存在致命配置缺失，请先修复后再运行")
        sys.exit(1)
