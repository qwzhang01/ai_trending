"""GitHub 星数快照追踪器 — 本地持久化星数并计算增长趋势。

职责：
  - 每次运行时记录候选仓库的星数快照到本地 JSON 文件
  - 查询历史快照，计算指定天数内的星数增长
  - 自动清理超过 30 天的过期快照文件

不负责：
  - 调用 GitHub API（由 fetchers.py 完成）
  - LLM 调用或语义判断
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

from ai_trending.logger import get_logger

log = get_logger("star_tracker")

# 默认快照存储目录
_DEFAULT_SNAPSHOT_DIR = Path("output/star_snapshots")

# 快照保留天数
_KEEP_DAYS = 30


class StarTracker:
    """本地星数快照追踪器。

    使用 JSON 文件按日期存储星数快照：
      output/star_snapshots/2026-04-01.json
      output/star_snapshots/2026-03-31.json
      ...

    对外暴露三个方法：
      - record_snapshot(): 记录当日快照
      - get_growth(): 查询 N 天增长量
      - cleanup_old_snapshots(): 清理过期快照
    """

    def __init__(self, snapshot_dir: Path | str | None = None) -> None:
        """初始化追踪器。

        Args:
            snapshot_dir: 快照存储目录路径，为 None 时使用默认路径
        """
        self._snapshot_dir = (
            Path(snapshot_dir) if snapshot_dir else _DEFAULT_SNAPSHOT_DIR
        )

    @property
    def snapshot_dir(self) -> Path:
        """快照存储目录。"""
        return self._snapshot_dir

    def record_snapshot(
        self,
        repos: list[dict[str, int | str]],
        date: str | None = None,
    ) -> Path:
        """记录当日星数快照。

        Args:
            repos: 仓库列表，每个元素需包含 full_name 和 stars 键
            date: 日期字符串，格式 YYYY-MM-DD，为 None 时使用当天

        Returns:
            写入的快照文件路径
        """
        if date is None:
            date = datetime.now().strftime("%Y-%m-%d")

        snapshot: dict[str, int] = {}
        for repo in repos:
            full_name = str(repo.get("full_name", ""))
            stars = repo.get("stars", 0)
            if full_name and isinstance(stars, int):
                snapshot[full_name] = stars

        self._snapshot_dir.mkdir(parents=True, exist_ok=True)
        path = self._snapshot_dir / f"{date}.json"
        path.write_text(json.dumps(snapshot, indent=2, ensure_ascii=False))
        log.info(f"星数快照已记录: {path} ({len(snapshot)} 个仓库)")
        return path

    def get_growth(
        self,
        full_name: str,
        current_stars: int,
        days: int = 7,
    ) -> tuple[int | None, int | None]:
        """计算指定仓库 N 天内的星数增长。

        Args:
            full_name: 仓库全名，如 "owner/repo"
            current_stars: 当前星数
            days: 回溯天数，默认 7 天

        Returns:
            (stars_n_days_ago, growth) 元组：
            - stars_n_days_ago: N 天前的星数，无数据时为 None
            - growth: 增长量（当前 - N天前），无数据时为 None
        """
        target_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        snapshot_path = self._snapshot_dir / f"{target_date}.json"

        if not snapshot_path.exists():
            return None, None

        try:
            historical = json.loads(snapshot_path.read_text())
        except (json.JSONDecodeError, OSError) as e:
            log.warning(f"读取快照文件失败({snapshot_path}): {e}")
            return None, None

        prev_stars = historical.get(full_name)
        if prev_stars is None:
            return None, None

        growth = current_stars - prev_stars
        return prev_stars, growth

    def enrich_candidates(
        self,
        candidates: list,
        days: int = 7,
    ) -> int:
        """批量为候选仓库填充星数增长数据。

        直接修改 candidate 对象的 stars_7d_ago 和 stars_growth_7d 字段。

        Args:
            candidates: RepoCandidate 列表
            days: 回溯天数，默认 7 天

        Returns:
            成功填充的仓库数量
        """
        filled = 0
        for candidate in candidates:
            stars_ago, growth = self.get_growth(
                candidate.full_name,
                candidate.stars,
                days=days,
            )
            if stars_ago is not None:
                candidate.stars_7d_ago = stars_ago
                candidate.stars_growth_7d = growth
                filled += 1

        if filled:
            log.info(
                f"星数增长数据填充完成: {filled}/{len(candidates)} 个仓库有历史数据"
            )
        else:
            log.info(f"无 {days} 天前的历史快照，stars_growth_7d 保持 None")
        return filled

    def cleanup_old_snapshots(self, keep_days: int = _KEEP_DAYS) -> int:
        """清理超过指定天数的过期快照文件。

        Args:
            keep_days: 保留最近 N 天的快照，默认 30 天

        Returns:
            删除的文件数量
        """
        if not self._snapshot_dir.exists():
            return 0

        cutoff_date = (datetime.now() - timedelta(days=keep_days)).strftime("%Y-%m-%d")
        removed = 0

        for path in sorted(self._snapshot_dir.glob("*.json")):
            # 从文件名提取日期（如 2026-03-01.json → 2026-03-01）
            date_str = path.stem
            if len(date_str) == 10 and date_str < cutoff_date:
                try:
                    path.unlink()
                    removed += 1
                except OSError as e:
                    log.warning(f"删除过期快照失败({path}): {e}")

        if removed:
            log.info(f"已清理 {removed} 个过期快照文件（保留最近 {keep_days} 天）")
        return removed
