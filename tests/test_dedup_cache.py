"""dedup_cache 模块测试."""

import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from ai_trending.crew.util.dedup_cache import (
    KEEP_DAYS,
    DedupCache,
    _expire,
    _url_key,
    make_news_key,
)


# ── _url_key ─────────────────────────────────────────────────────

class TestUrlKey:
    def test_same_url_same_key(self):
        assert _url_key("https://example.com/a") == _url_key("https://example.com/a")

    def test_different_url_different_key(self):
        assert _url_key("https://example.com/a") != _url_key("https://example.com/b")

    def test_case_insensitive(self):
        assert _url_key("HTTPS://EXAMPLE.COM/A") == _url_key("https://example.com/a")

    def test_strips_whitespace(self):
        assert _url_key("  https://example.com/a  ") == _url_key("https://example.com/a")

    def test_key_length_16(self):
        key = _url_key("https://example.com")
        assert len(key) == 16


# ── make_news_key ─────────────────────────────────────────────────

class TestMakeNewsKey:
    def test_url_takes_priority(self):
        key = make_news_key("https://example.com/news", "Some Title")
        assert key == _url_key("https://example.com/news")

    def test_fallback_to_title_when_url_empty(self):
        key = make_news_key("", "Some Title")
        assert key == _url_key("Some Title")

    def test_fallback_to_title_when_url_whitespace(self):
        key = make_news_key("   ", "Some Title")
        assert key == _url_key("Some Title")

    def test_empty_both_returns_empty(self):
        assert make_news_key("", "") == ""

    def test_none_url_uses_title(self):
        # url 为空字符串，title 有值
        key = make_news_key("", "AI News Today")
        assert key != ""


# ── _expire ───────────────────────────────────────────────────────

class TestExpire:
    def test_removes_old_entries(self):
        old_date = (datetime.now() - timedelta(days=KEEP_DAYS + 1)).strftime("%Y-%m-%d")
        seen = {"old_key": old_date, "new_key": datetime.now().strftime("%Y-%m-%d")}
        result = _expire(seen)
        assert "old_key" not in result
        assert "new_key" in result

    def test_keeps_entries_within_keep_days(self):
        today = datetime.now().strftime("%Y-%m-%d")
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        seen = {"k1": today, "k2": yesterday}
        result = _expire(seen, keep_days=KEEP_DAYS)
        assert "k1" in result
        assert "k2" in result

    def test_empty_seen_returns_empty(self):
        assert _expire({}) == {}

    def test_custom_keep_days(self):
        two_days_ago = (datetime.now() - timedelta(days=2)).strftime("%Y-%m-%d")
        seen = {"k": two_days_ago}
        # keep_days=1 → 2天前的应被清除
        assert _expire(seen, keep_days=1) == {}
        # keep_days=3 → 2天前的应保留
        assert _expire(seen, keep_days=3) == {"k": two_days_ago}


# ── DedupCache ────────────────────────────────────────────────────

class TestDedupCache:
    def test_is_new_returns_true_for_unseen(self, tmp_output_dir):
        cache = DedupCache("test_cache")
        assert cache.is_new("brand_new_key") is True

    def test_is_new_returns_false_after_mark_seen(self, tmp_output_dir):
        cache = DedupCache("test_cache")
        cache.mark_seen(["key1"])
        assert cache.is_new("key1") is False

    def test_filter_new_removes_seen_items(self, tmp_output_dir):
        cache = DedupCache("test_cache")
        cache.mark_seen(["key_old"])

        items = [{"id": "key_old"}, {"id": "key_new"}]
        new_items = cache.filter_new(items, key_fn=lambda x: x["id"])
        assert len(new_items) == 1
        assert new_items[0]["id"] == "key_new"

    def test_filter_new_all_new(self, tmp_output_dir):
        cache = DedupCache("test_cache")
        items = [{"id": "a"}, {"id": "b"}, {"id": "c"}]
        new_items = cache.filter_new(items, key_fn=lambda x: x["id"])
        assert len(new_items) == 3

    def test_filter_new_all_seen(self, tmp_output_dir):
        cache = DedupCache("test_cache")
        cache.mark_seen(["a", "b"])
        items = [{"id": "a"}, {"id": "b"}]
        new_items = cache.filter_new(items, key_fn=lambda x: x["id"])
        assert new_items == []

    def test_mark_seen_persists_to_file(self, tmp_output_dir):
        cache = DedupCache("persist_test")
        cache.mark_seen(["key_persist"])

        # 重新加载缓存，验证持久化
        cache2 = DedupCache("persist_test")
        assert cache2.is_new("key_persist") is False

    def test_stats_returns_correct_info(self, tmp_output_dir):
        cache = DedupCache("stats_test")
        cache.mark_seen(["k1", "k2"])
        stats = cache.stats()
        assert stats["name"] == "stats_test"
        assert stats["total_seen"] == 2
        assert stats["keep_days"] == KEEP_DAYS

    def test_expired_entries_not_loaded(self, tmp_output_dir):
        """写入过期条目到缓存文件，验证加载时自动清理."""
        cache_dir = tmp_output_dir / "output" / "dedup_cache"
        cache_dir.mkdir(parents=True, exist_ok=True)
        cache_file = cache_dir / "expire_test.json"

        old_date = (datetime.now() - timedelta(days=KEEP_DAYS + 2)).strftime("%Y-%m-%d")
        today = datetime.now().strftime("%Y-%m-%d")
        cache_file.write_text(
            json.dumps({"seen": {"old_key": old_date, "new_key": today}}),
            encoding="utf-8",
        )

        cache = DedupCache("expire_test")
        assert cache.is_new("old_key") is True   # 过期，视为新
        assert cache.is_new("new_key") is False   # 未过期，视为旧

    def test_corrupted_cache_file_resets(self, tmp_output_dir):
        """缓存文件损坏时，应优雅降级为空缓存."""
        cache_dir = tmp_output_dir / "output" / "dedup_cache"
        cache_dir.mkdir(parents=True, exist_ok=True)
        (cache_dir / "corrupt_test.json").write_text("not valid json", encoding="utf-8")

        cache = DedupCache("corrupt_test")
        assert cache.is_new("any_key") is True

    def test_custom_keep_days(self, tmp_output_dir):
        cache = DedupCache("custom_days_test", keep_days=1)
        assert cache.keep_days == 1
