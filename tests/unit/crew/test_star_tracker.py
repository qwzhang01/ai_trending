"""tests/unit/crew/test_star_tracker.py — StarTracker 单元测试。

覆盖 TASK-002 新增的星数增长追踪功能：
- record_snapshot: 快照文件创建和内容正确性
- get_growth: 有历史数据、无历史数据、文件损坏
- enrich_candidates: 批量填充星数增长
- cleanup_old_snapshots: 过期快照自动清理
- _track_star_growth 在 fetchers.py 中的集成
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest

from ai_trending.crew.github_trending.models import RepoCandidate
from ai_trending.crew.github_trending.star_tracker import StarTracker


# ── Fixtures ──────────────────────────────────────────────────


@pytest.fixture
def tracker(tmp_path):
    """创建使用临时目录的 StarTracker。"""
    return StarTracker(snapshot_dir=tmp_path / "snapshots")


@pytest.fixture
def tracker_with_history(tracker):
    """创建一个带有 7 天前历史快照的 StarTracker。"""
    date_7d_ago = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
    historical_data = {
        "owner/repo-a": 3000,
        "owner/repo-b": 1500,
        "owner/repo-c": 800,
    }
    tracker.snapshot_dir.mkdir(parents=True, exist_ok=True)
    snapshot_path = tracker.snapshot_dir / f"{date_7d_ago}.json"
    snapshot_path.write_text(json.dumps(historical_data))
    return tracker


@pytest.fixture
def sample_candidates():
    """构造 3 个候选仓库。"""
    return [
        RepoCandidate(full_name="owner/repo-a", stars=5000),
        RepoCandidate(full_name="owner/repo-b", stars=2000),
        RepoCandidate(full_name="owner/repo-c", stars=1000),
    ]


# ── record_snapshot 测试 ──────────────────────────────────────


class TestRecordSnapshot:
    """测试星数快照记录。"""

    def test_creates_snapshot_file(self, tracker):
        """应在指定日期创建 JSON 快照文件。"""
        repos = [
            {"full_name": "owner/repo-a", "stars": 5000},
            {"full_name": "owner/repo-b", "stars": 3000},
        ]
        path = tracker.record_snapshot(repos, date="2026-04-01")

        assert path.exists()
        assert path.name == "2026-04-01.json"

    def test_snapshot_content_correct(self, tracker):
        """快照文件内容应为 {full_name: stars} 的 JSON 映射。"""
        repos = [
            {"full_name": "owner/repo-a", "stars": 5000},
            {"full_name": "owner/repo-b", "stars": 3000},
        ]
        path = tracker.record_snapshot(repos, date="2026-04-01")

        data = json.loads(path.read_text())
        assert data["owner/repo-a"] == 5000
        assert data["owner/repo-b"] == 3000
        assert len(data) == 2

    def test_uses_today_when_no_date(self, tracker):
        """未指定日期时应使用当天日期。"""
        repos = [{"full_name": "owner/repo", "stars": 1000}]
        path = tracker.record_snapshot(repos)

        today = datetime.now().strftime("%Y-%m-%d")
        assert path.name == f"{today}.json"

    def test_creates_directory_if_not_exists(self, tmp_path):
        """快照目录不存在时应自动创建。"""
        deep_dir = tmp_path / "a" / "b" / "c"
        tracker = StarTracker(snapshot_dir=deep_dir)

        repos = [{"full_name": "owner/repo", "stars": 100}]
        path = tracker.record_snapshot(repos, date="2026-04-01")

        assert path.exists()
        assert deep_dir.exists()

    def test_overwrites_existing_snapshot(self, tracker):
        """同一天重复运行应覆盖已有快照。"""
        repos_v1 = [{"full_name": "owner/repo", "stars": 1000}]
        repos_v2 = [{"full_name": "owner/repo", "stars": 1500}]

        tracker.record_snapshot(repos_v1, date="2026-04-01")
        path = tracker.record_snapshot(repos_v2, date="2026-04-01")

        data = json.loads(path.read_text())
        assert data["owner/repo"] == 1500

    def test_skips_invalid_entries(self, tracker):
        """应跳过缺少 full_name 或 stars 不是 int 的条目。"""
        repos = [
            {"full_name": "owner/valid", "stars": 1000},
            {"full_name": "", "stars": 500},  # 空名，应跳过
            {"full_name": "owner/bad-stars", "stars": "not-a-number"},  # 非 int
        ]
        path = tracker.record_snapshot(repos, date="2026-04-01")

        data = json.loads(path.read_text())
        assert "owner/valid" in data
        assert "" not in data
        assert len(data) == 1

    def test_empty_repos_creates_empty_snapshot(self, tracker):
        """空仓库列表应创建空 JSON 对象。"""
        path = tracker.record_snapshot([], date="2026-04-01")

        data = json.loads(path.read_text())
        assert data == {}


# ── get_growth 测试 ───────────────────────────────────────────


class TestGetGrowth:
    """测试星数增长计算。"""

    def test_with_historical_data(self, tracker_with_history):
        """有历史数据时，应返回正确的增长量。"""
        stars_ago, growth = tracker_with_history.get_growth(
            "owner/repo-a", current_stars=5000
        )

        assert stars_ago == 3000
        assert growth == 2000

    def test_no_snapshot_file(self, tracker):
        """无历史快照文件时，应返回 (None, None)。"""
        stars_ago, growth = tracker.get_growth("owner/repo", current_stars=1000)

        assert stars_ago is None
        assert growth is None

    def test_repo_not_in_snapshot(self, tracker_with_history):
        """快照中不包含该仓库时，应返回 (None, None)。"""
        stars_ago, growth = tracker_with_history.get_growth(
            "owner/new-repo", current_stars=500
        )

        assert stars_ago is None
        assert growth is None

    def test_negative_growth(self, tracker_with_history):
        """星数减少时，growth 应为负数。"""
        # repo-a 7天前 3000，现在 2500
        stars_ago, growth = tracker_with_history.get_growth(
            "owner/repo-a", current_stars=2500
        )

        assert stars_ago == 3000
        assert growth == -500

    def test_zero_growth(self, tracker_with_history):
        """星数不变时，growth 应为 0。"""
        stars_ago, growth = tracker_with_history.get_growth(
            "owner/repo-b", current_stars=1500
        )

        assert stars_ago == 1500
        assert growth == 0

    def test_corrupted_snapshot_file(self, tracker):
        """快照文件内容损坏时，应返回 (None, None) 不崩溃。"""
        date_7d_ago = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
        tracker.snapshot_dir.mkdir(parents=True, exist_ok=True)
        corrupted_path = tracker.snapshot_dir / f"{date_7d_ago}.json"
        corrupted_path.write_text("not valid json {{{")

        stars_ago, growth = tracker.get_growth("owner/repo", current_stars=1000)

        assert stars_ago is None
        assert growth is None

    def test_custom_days(self, tracker):
        """支持自定义回溯天数。"""
        date_3d_ago = (datetime.now() - timedelta(days=3)).strftime("%Y-%m-%d")
        tracker.snapshot_dir.mkdir(parents=True, exist_ok=True)
        snapshot_path = tracker.snapshot_dir / f"{date_3d_ago}.json"
        snapshot_path.write_text(json.dumps({"owner/repo": 900}))

        stars_ago, growth = tracker.get_growth(
            "owner/repo", current_stars=1200, days=3
        )

        assert stars_ago == 900
        assert growth == 300


# ── enrich_candidates 测试 ────────────────────────────────────


class TestEnrichCandidates:
    """测试批量填充星数增长数据。"""

    def test_enriches_all_with_history(
        self, tracker_with_history, sample_candidates
    ):
        """有完整历史数据时，应为所有候选仓库填充增长数据。"""
        filled = tracker_with_history.enrich_candidates(sample_candidates)

        assert filled == 3
        assert sample_candidates[0].stars_7d_ago == 3000
        assert sample_candidates[0].stars_growth_7d == 2000  # 5000 - 3000
        assert sample_candidates[1].stars_7d_ago == 1500
        assert sample_candidates[1].stars_growth_7d == 500  # 2000 - 1500

    def test_no_history_leaves_none(self, tracker, sample_candidates):
        """无历史数据时，所有字段保持 None。"""
        filled = tracker.enrich_candidates(sample_candidates)

        assert filled == 0
        for c in sample_candidates:
            assert c.stars_7d_ago is None
            assert c.stars_growth_7d is None

    def test_partial_history(self, tracker):
        """部分仓库有历史数据时，仅填充有数据的仓库。"""
        date_7d_ago = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
        tracker.snapshot_dir.mkdir(parents=True, exist_ok=True)
        snapshot_path = tracker.snapshot_dir / f"{date_7d_ago}.json"
        # 只记录 repo-a 的历史
        snapshot_path.write_text(json.dumps({"owner/repo-a": 3000}))

        candidates = [
            RepoCandidate(full_name="owner/repo-a", stars=5000),
            RepoCandidate(full_name="owner/repo-new", stars=1000),
        ]
        filled = tracker.enrich_candidates(candidates)

        assert filled == 1
        assert candidates[0].stars_7d_ago == 3000
        assert candidates[0].stars_growth_7d == 2000
        assert candidates[1].stars_7d_ago is None
        assert candidates[1].stars_growth_7d is None

    def test_empty_candidates(self, tracker_with_history):
        """空候选列表应返回 0。"""
        filled = tracker_with_history.enrich_candidates([])
        assert filled == 0


# ── cleanup_old_snapshots 测试 ────────────────────────────────


class TestCleanupOldSnapshots:
    """测试过期快照清理。"""

    def test_removes_old_files(self, tracker):
        """应删除超过 keep_days 天的快照。"""
        tracker.snapshot_dir.mkdir(parents=True, exist_ok=True)

        # 创建一个 40 天前的快照
        old_date = (datetime.now() - timedelta(days=40)).strftime("%Y-%m-%d")
        old_path = tracker.snapshot_dir / f"{old_date}.json"
        old_path.write_text(json.dumps({"repo": 100}))

        # 创建一个今天的快照
        today = datetime.now().strftime("%Y-%m-%d")
        new_path = tracker.snapshot_dir / f"{today}.json"
        new_path.write_text(json.dumps({"repo": 200}))

        removed = tracker.cleanup_old_snapshots(keep_days=30)

        assert removed == 1
        assert not old_path.exists()
        assert new_path.exists()

    def test_keeps_recent_files(self, tracker):
        """应保留最近 keep_days 天内的快照。"""
        tracker.snapshot_dir.mkdir(parents=True, exist_ok=True)

        recent_date = (datetime.now() - timedelta(days=5)).strftime("%Y-%m-%d")
        recent_path = tracker.snapshot_dir / f"{recent_date}.json"
        recent_path.write_text(json.dumps({"repo": 100}))

        removed = tracker.cleanup_old_snapshots(keep_days=30)

        assert removed == 0
        assert recent_path.exists()

    def test_no_snapshots_dir(self, tmp_path):
        """快照目录不存在时应返回 0，不崩溃。"""
        tracker = StarTracker(snapshot_dir=tmp_path / "nonexistent")

        removed = tracker.cleanup_old_snapshots()

        assert removed == 0

    def test_ignores_non_json_files(self, tracker):
        """应忽略非 .json 文件。"""
        tracker.snapshot_dir.mkdir(parents=True, exist_ok=True)

        # 创建一个非 JSON 文件
        (tracker.snapshot_dir / "notes.txt").write_text("hello")

        removed = tracker.cleanup_old_snapshots()

        assert removed == 0
        assert (tracker.snapshot_dir / "notes.txt").exists()

    def test_custom_keep_days(self, tracker):
        """支持自定义保留天数。"""
        tracker.snapshot_dir.mkdir(parents=True, exist_ok=True)

        # 创建 10 天前的快照
        date_10d = (datetime.now() - timedelta(days=10)).strftime("%Y-%m-%d")
        path_10d = tracker.snapshot_dir / f"{date_10d}.json"
        path_10d.write_text(json.dumps({"repo": 100}))

        # keep_days=5 时，10 天前的应被删除
        removed = tracker.cleanup_old_snapshots(keep_days=5)
        assert removed == 1
        assert not path_10d.exists()


# ── fetchers.py 集成测试 ──────────────────────────────────────


class TestTrackStarGrowthIntegration:
    """测试 _track_star_growth 在 GitHubFetcher 中的集成。"""

    def test_track_star_growth_records_and_enriches(self, tmp_path):
        """_track_star_growth 应记录快照并填充增长数据。"""
        from ai_trending.crew.github_trending.fetchers import GitHubFetcher

        candidates = [
            RepoCandidate(full_name="owner/repo-x", stars=8000),
        ]

        # mock StarTracker 使用临时目录
        with patch(
            "ai_trending.crew.github_trending.star_tracker._DEFAULT_SNAPSHOT_DIR",
            tmp_path / "snapshots",
        ):
            GitHubFetcher._track_star_growth(candidates)

        # 快照文件应被创建
        snapshot_dir = tmp_path / "snapshots"
        today = datetime.now().strftime("%Y-%m-%d")
        assert (snapshot_dir / f"{today}.json").exists()

    def test_track_star_growth_tolerates_failure(self):
        """_track_star_growth 失败时不应影响主流程。"""
        from ai_trending.crew.github_trending.fetchers import GitHubFetcher

        candidates = [
            RepoCandidate(full_name="owner/repo-x", stars=8000),
        ]

        # mock StarTracker 抛出异常
        with patch(
            "ai_trending.crew.github_trending.star_tracker.StarTracker.record_snapshot",
            side_effect=PermissionError("no write permission"),
        ):
            # 不应抛出异常
            GitHubFetcher._track_star_growth(candidates)

        # 候选仓库保持原样
        assert candidates[0].stars_7d_ago is None


# ── RepoCandidate 模型字段测试 ────────────────────────────────


class TestRepoCandidateStarFields:
    """测试 RepoCandidate 的星数增长字段。"""

    def test_default_none(self):
        """默认 stars_7d_ago 和 stars_growth_7d 应为 None。"""
        repo = RepoCandidate(full_name="owner/repo")
        assert repo.stars_7d_ago is None
        assert repo.stars_growth_7d is None

    def test_set_values(self):
        """应能正常设置星数增长数据。"""
        repo = RepoCandidate(
            full_name="owner/repo",
            stars=5000,
            stars_7d_ago=3000,
            stars_growth_7d=2000,
        )
        assert repo.stars_7d_ago == 3000
        assert repo.stars_growth_7d == 2000

    def test_model_dump_includes_star_fields(self):
        """model_dump 应包含星数增长字段。"""
        repo = RepoCandidate(
            full_name="owner/repo",
            stars=5000,
            stars_7d_ago=3000,
            stars_growth_7d=2000,
        )
        data = repo.model_dump()
        assert "stars_7d_ago" in data
        assert "stars_growth_7d" in data
        assert data["stars_7d_ago"] == 3000
        assert data["stars_growth_7d"] == 2000

    def test_none_values_in_dump(self):
        """无历史数据时 dump 中应为 None。"""
        repo = RepoCandidate(full_name="owner/repo")
        data = repo.model_dump()
        assert data["stars_7d_ago"] is None
        assert data["stars_growth_7d"] is None
