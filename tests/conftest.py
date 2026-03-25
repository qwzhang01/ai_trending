"""pytest 公共 fixtures — 供所有测试文件复用."""

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ── 环境变量 fixtures ────────────────────────────────────────────

@pytest.fixture
def github_env(monkeypatch):
    """注入 GitHub 相关环境变量."""
    monkeypatch.setenv("GITHUB_TRENDING_TOKEN", "fake-github-token")
    monkeypatch.setenv("GITHUB_REPORT_REPO", "test-owner/test-repo")


@pytest.fixture
def wechat_env(monkeypatch):
    """注入微信公众号相关环境变量."""
    monkeypatch.setenv("WECHAT_APP_ID", "fake_app_id")
    monkeypatch.setenv("WECHAT_APP_SECRET", "fake_app_secret")
    monkeypatch.setenv("WECHAT_THUMB_MEDIA_ID", "fake_thumb_media_id")


@pytest.fixture
def newsdata_env(monkeypatch):
    """注入 newsdata.io API Key."""
    monkeypatch.setenv("NEWSDATA_API_KEY", "fake-newsdata-key")


# ── 临时目录 fixture ─────────────────────────────────────────────

@pytest.fixture
def tmp_output_dir(tmp_path, monkeypatch):
    """将工作目录切换到临时目录，避免测试污染真实 output/."""
    monkeypatch.chdir(tmp_path)
    return tmp_path


# ── 通用 HTTP mock fixture ───────────────────────────────────────

def make_mock_response(json_data=None, text="", status_code=200):
    """构造一个模拟的 requests.Response 对象."""
    mock = MagicMock()
    mock.status_code = status_code
    mock.text = text
    mock.headers = {"X-RateLimit-Remaining": "50"}
    if json_data is not None:
        mock.json.return_value = json_data
    else:
        mock.json.side_effect = ValueError("no json")
    return mock
