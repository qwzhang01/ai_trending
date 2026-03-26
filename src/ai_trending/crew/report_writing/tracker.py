"""PreviousReportTracker — 上期回顾自动数据追踪器。

职责：
  1. 找到最近一期已生成的日报文件（reports/{date}.md）
  2. 解析其中推荐的 GitHub 项目（提取 owner/repo 和当时的 Star 数）
  3. 通过 GitHub API 查询这些项目的当前 Star 数
  4. 计算增长量，生成结构化的「上期回顾」上下文字符串
  5. 将上下文注入到 ReportWritingCrew 的 inputs，供 LLM 撰写真实的上期回顾

设计原则：
  - 只做数据采集和格式化，不做 LLM 调用（符合 Fetcher 层规范）
  - 查询失败时返回空字符串，不阻断主流程
  - 使用 safe_request 保证网络调用的健壮性
"""

from __future__ import annotations

import os
import re
from datetime import date, timedelta
from pathlib import Path
from typing import NamedTuple

from ai_trending.logger import get_logger
from ai_trending.retry import safe_request

log = get_logger("previous_report_tracker")

# GitHub API 基础 URL
_GITHUB_API_BASE = "https://api.github.com"

# 最多追踪的项目数量（避免 API 请求过多）
_MAX_TRACK_REPOS = 4

# 向前查找历史报告的最大天数
_MAX_LOOKBACK_DAYS = 14


class TrackedRepo(NamedTuple):
    """单个被追踪项目的数据。"""
    repo: str           # owner/repo_name
    name: str           # 显示名称
    prev_stars: int     # 上期 Star 数
    curr_stars: int     # 当前 Star 数
    growth: int         # 增长量
    report_date: str    # 上期报告日期


class PreviousReportTracker:
    """上期回顾自动数据追踪器。

    使用方式：
        tracker = PreviousReportTracker(reports_dir="reports")
        context = tracker.get_previous_report_context(current_date="2026-03-26")
        # context 是一个格式化字符串，直接注入到 ReportWritingCrew 的 inputs
    """

    def __init__(self, reports_dir: str | Path | None = None) -> None:
        """初始化追踪器。

        Args:
            reports_dir: 报告文件目录，默认为项目根目录下的 reports/
        """
        if reports_dir is None:
            # 默认：从项目根目录找 reports/
            self._reports_dir = Path.cwd() / "reports"
        else:
            self._reports_dir = Path(reports_dir)

    def get_previous_report_context(self, current_date: str) -> str:
        """获取上期回顾的完整上下文字符串，供 ReportWritingCrew 使用。

        Args:
            current_date: 当前报告日期，格式 YYYY-MM-DD

        Returns:
            格式化的上期回顾上下文字符串。
            若无历史数据或查询失败，返回空字符串（LLM 将省略上期回顾 Section）。
        """
        try:
            # 1. 找到最近一期报告
            prev_report_path, prev_date = self._find_previous_report(current_date)
            if prev_report_path is None:
                log.info("[PreviousReportTracker] 未找到历史报告，跳过上期回顾")
                return ""

            log.info(f"[PreviousReportTracker] 找到上期报告: {prev_report_path.name}")

            # 2. 解析上期报告中的推荐项目
            repos = self._parse_recommended_repos(prev_report_path)
            if not repos:
                log.info("[PreviousReportTracker] 上期报告中未找到可追踪的项目")
                return ""

            log.info(f"[PreviousReportTracker] 解析到 {len(repos)} 个项目: {[r[0] for r in repos]}")

            # 3. 查询当前 Star 数
            tracked = self._fetch_current_stars(repos, prev_date)
            if not tracked:
                log.warning("[PreviousReportTracker] 所有项目 Star 数查询失败")
                return ""

            # 4. 生成上下文字符串
            context = self._format_context(tracked, prev_date)
            log.info(f"[PreviousReportTracker] 生成上期回顾上下文，追踪 {len(tracked)} 个项目")
            return context

        except Exception as e:
            log.error(f"[PreviousReportTracker] 追踪失败: {e}")
            return ""

    # ── 内部方法 ──────────────────────────────────────────────────────────────

    def _find_previous_report(
        self, current_date: str
    ) -> tuple[Path | None, str]:
        """在 reports/ 目录中找到最近一期报告（不含当天）。

        Returns:
            (报告文件路径, 报告日期字符串)，未找到时返回 (None, "")
        """
        if not self._reports_dir.exists():
            log.warning(f"[PreviousReportTracker] reports 目录不存在: {self._reports_dir}")
            return None, ""

        try:
            current = date.fromisoformat(current_date)
        except ValueError:
            log.error(f"[PreviousReportTracker] 日期格式错误: {current_date}")
            return None, ""

        # 向前查找，最多 _MAX_LOOKBACK_DAYS 天
        for delta in range(1, _MAX_LOOKBACK_DAYS + 1):
            candidate_date = current - timedelta(days=delta)
            candidate_path = self._reports_dir / f"{candidate_date.isoformat()}.md"
            if candidate_path.exists():
                return candidate_path, candidate_date.isoformat()

        return None, ""

    def _parse_recommended_repos(
        self, report_path: Path
    ) -> list[tuple[str, str, int]]:
        """从报告文件中解析推荐的 GitHub 项目。

        Returns:
            list of (repo_full_name, display_name, prev_stars)
            例如：[("owner/repo", "repo", 5000), ...]
        """
        try:
            content = report_path.read_text(encoding="utf-8")
        except Exception as e:
            log.error(f"[PreviousReportTracker] 读取报告失败: {e}")
            return []

        repos: list[tuple[str, str, int]] = []
        seen: set[str] = set()

        # 匹配格式：[项目名](https://github.com/owner/repo) ⭐ 数字
        # 支持带增长信息：⭐ 7691（+1240）或 ⭐ 7691
        pattern = re.compile(
            r"\[([^\]]+)\]\(https://github\.com/([^/\s)]+/[^/\s)]+)\)"
            r"\s*⭐\s*([\d,]+)"
        )

        for match in pattern.finditer(content):
            display_name = match.group(1).strip()
            repo_full = match.group(2).strip().rstrip("/")
            stars_str = match.group(3).replace(",", "")

            # 过滤非法 repo 名（含 # 等特殊字符）
            if not re.match(r"^[a-zA-Z0-9_.-]+/[a-zA-Z0-9_.-]+$", repo_full):
                continue

            if repo_full in seen:
                continue
            seen.add(repo_full)

            try:
                prev_stars = int(stars_str)
            except ValueError:
                prev_stars = 0

            repos.append((repo_full, display_name, prev_stars))

            if len(repos) >= _MAX_TRACK_REPOS:
                break

        return repos

    def _fetch_current_stars(
        self,
        repos: list[tuple[str, str, int]],
        prev_date: str,
    ) -> list[TrackedRepo]:
        """通过 GitHub API 查询每个项目的当前 Star 数。

        Args:
            repos: list of (repo_full_name, display_name, prev_stars)
            prev_date: 上期报告日期

        Returns:
            list[TrackedRepo]，查询失败的项目会被跳过
        """
        github_token = os.environ.get("GITHUB_TOKEN", "")
        headers: dict[str, str] = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if github_token:
            headers["Authorization"] = f"Bearer {github_token}"

        tracked: list[TrackedRepo] = []

        for repo_full, display_name, prev_stars in repos:
            url = f"{_GITHUB_API_BASE}/repos/{repo_full}"
            resp = safe_request(
                "GET",
                url,
                headers=headers,
                timeout=10,
                max_retries=2,
                operation_name=f"GitHub API({repo_full})",
            )

            if resp is None:
                log.warning(f"[PreviousReportTracker] {repo_full} 查询失败，跳过")
                continue

            try:
                data = resp.json()
                curr_stars = int(data.get("stargazers_count", 0))
                growth = curr_stars - prev_stars

                tracked.append(TrackedRepo(
                    repo=repo_full,
                    name=display_name,
                    prev_stars=prev_stars,
                    curr_stars=curr_stars,
                    growth=growth,
                    report_date=prev_date,
                ))
                log.info(
                    f"[PreviousReportTracker] {repo_full}: "
                    f"{prev_stars} → {curr_stars} (+{growth})"
                )
            except Exception as e:
                log.warning(f"[PreviousReportTracker] {repo_full} 解析响应失败: {e}")
                continue

        return tracked

    def _format_context(self, tracked: list[TrackedRepo], prev_date: str) -> str:
        """将追踪数据格式化为供 LLM 使用的上下文字符串。

        格式设计原则：
        - 提供真实数字，LLM 直接引用，不允许修改
        - 提供趋势判断依据（增长量 + 增长率），LLM 据此写趋势验证
        - 格式清晰，LLM 容易解析
        """
        lines = [
            f"## 上期回顾数据（{prev_date}，真实追踪，禁止修改数字）",
            "",
            "以下是上期推荐项目的真实星数追踪数据，请基于这些数据撰写「上期回顾」Section。",
            "**重要约束**：星数数字必须与下方数据完全一致，不允许估算或虚构。",
            "",
            "### 星数追踪",
        ]

        for repo in tracked:
            growth_sign = "+" if repo.growth >= 0 else ""
            growth_pct = (
                f"{repo.growth / repo.prev_stars * 100:.1f}%"
                if repo.prev_stars > 0
                else "N/A"
            )

            # 趋势判断依据
            if repo.growth > 500:
                trend_hint = "增长强劲，超出预期"
            elif repo.growth > 100:
                trend_hint = "稳定增长，符合预期"
            elif repo.growth >= 0:
                trend_hint = "增长放缓，低于预期"
            else:
                trend_hint = "星数下降，需重新评估"

            lines.extend([
                f"- **{repo.name}** (`{repo.repo}`)",
                f"  - 上期星数：⭐ {repo.prev_stars:,}",
                f"  - 当前星数：⭐ {repo.curr_stars:,}",
                f"  - 增长：{growth_sign}{repo.growth:,}（{growth_sign}{growth_pct}）",
                f"  - 趋势参考：{trend_hint}",
                "",
            ])

        lines.extend([
            "### 撰写指引",
            "- 「星数追踪」部分：直接使用上方数字，格式为「⭐ {上期星数} → ⭐ {当前星数}（+{增长数}）」",
            "- 「趋势验证」部分：基于增长量和趋势参考，诚实评估判断是否准确",
            "- 「下周关注点」部分：制造连续性阅读钩子，引导读者下期继续关注",
            "- 如果某个项目增长低于预期，必须如实写出，不要美化",
        ])

        return "\n".join(lines)
