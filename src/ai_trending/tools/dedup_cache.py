"""去重缓存模块 — 基于 JSON 文件持久化，避免同一条目在多次运行中重复出现.

缓存文件存放在 output/dedup_cache/ 目录下，按类型分文件：
  - github_repos.json   : GitHub 仓库去重（key = full_name）
  - news_urls.json      : 新闻去重（key = url 或 title 的 hash）

缓存结构（每个文件）：
  {
    "seen": {
      "<key>": "<first_seen_date>",   # e.g. "langchain-ai/langgraph": "2026-03-17"
      ...
    }
  }

过期策略：超过 KEEP_DAYS 天的记录自动清理，避免文件无限增长。
"""

import json
import hashlib
from datetime import datetime, timedelta
from pathlib import Path

from ai_trending.logger import get_logger

log = get_logger("dedup_cache")

# 缓存保留天数：超过此天数的记录视为"过期"，不再参与去重
KEEP_DAYS = 7

# 缓存目录（相对于运行目录）
_CACHE_DIR = Path("output") / "dedup_cache"


def _cache_file(name: str) -> Path:
    """返回指定缓存文件的路径，并确保目录存在."""
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return _CACHE_DIR / f"{name}.json"


def _load(name: str) -> dict[str, str]:
    """加载缓存文件，返回 {key: first_seen_date} 字典."""
    path = _cache_file(name)
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data.get("seen", {})
    except (json.JSONDecodeError, OSError) as e:
        log.warning(f"去重缓存读取失败 [{name}]: {e}，将重置缓存")
        return {}


def _save(name: str, seen: dict[str, str]) -> None:
    """将缓存写回文件."""
    path = _cache_file(name)
    try:
        path.write_text(
            json.dumps({"seen": seen}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except OSError as e:
        log.warning(f"去重缓存写入失败 [{name}]: {e}")


def _expire(seen: dict[str, str], keep_days: int = KEEP_DAYS) -> dict[str, str]:
    """清理超过 keep_days 天的过期记录."""
    cutoff = (datetime.now() - timedelta(days=keep_days)).strftime("%Y-%m-%d")
    return {k: v for k, v in seen.items() if v >= cutoff}


def _url_key(url: str) -> str:
    """将 URL 转为稳定的短 key（取 MD5 前 16 位）."""
    return hashlib.md5(url.strip().lower().encode()).hexdigest()[:16]


class DedupCache:
    """跨日去重缓存，支持 GitHub 仓库和新闻 URL 两种场景.

    用法示例::

        cache = DedupCache("github_repos")
        new_items = cache.filter_new(repos, key_fn=lambda r: r["full_name"])
        cache.mark_seen([r["full_name"] for r in new_items])
    """

    def __init__(self, name: str, keep_days: int = KEEP_DAYS):
        self.name = name
        self.keep_days = keep_days
        self._seen: dict[str, str] = _expire(_load(name), keep_days)

    def is_new(self, key: str) -> bool:
        """判断 key 是否是今天首次出现（即昨天及之前没见过）."""
        today = datetime.now().strftime("%Y-%m-%d")
        first_seen = self._seen.get(key)
        # 从未见过，或者今天才第一次见到（同一天内多次运行不算重复）
        return first_seen is None or first_seen == today

    def filter_new(self, items: list, key_fn) -> list:
        """从 items 中过滤出「今天首次出现」的条目.

        Args:
            items: 待过滤的列表
            key_fn: 从 item 提取去重 key 的函数，例如 lambda r: r["full_name"]

        Returns:
            只包含新条目的列表（昨天及之前已见过的被排除）
        """
        new_items = []
        dup_count = 0
        for item in items:
            key = key_fn(item)
            if self.is_new(key):
                new_items.append(item)
            else:
                dup_count += 1

        if dup_count:
            log.info(f"[{self.name}] 去重过滤: 共 {len(items)} 条，排除重复 {dup_count} 条，剩余 {len(new_items)} 条")

        return new_items

    def mark_seen(self, keys: list[str]) -> None:
        """将 keys 标记为今天已见，并持久化到文件."""
        today = datetime.now().strftime("%Y-%m-%d")
        for key in keys:
            # 只在首次见到时记录日期，后续同一天重复调用不覆盖
            if key not in self._seen:
                self._seen[key] = today
        _save(self.name, self._seen)

    def stats(self) -> dict:
        """返回缓存统计信息."""
        return {
            "name": self.name,
            "total_seen": len(self._seen),
            "keep_days": self.keep_days,
        }


def make_news_key(url: str, title: str = "") -> str:
    """为新闻条目生成去重 key.

    优先用 URL（稳定），URL 为空时退回到 title hash。
    """
    if url and url.strip():
        return _url_key(url)
    if title:
        return _url_key(title)
    return ""
