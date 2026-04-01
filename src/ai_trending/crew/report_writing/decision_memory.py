"""crew/report_writing/decision_memory.py — 编辑决策记忆系统.

第三层记忆（在 StyleMemory 和 TopicTracker 之上）：
记录"什么样的编辑决策导致了好/坏的日报"，帮助 EditorialPlanningCrew 做更好的决策。

文件格式：output/DECISION_MEMORY.md

记录维度：
  - 信号强度选择（red/yellow/green）
  - 头条类型（repo/news）
  - 主要切入角度
  - 质量审核通过数
  - 好的决策模式总结

用法：
  # 在 editorial_planning_node 中注入历史决策建议
  guidance = DecisionMemory().get_decision_guidance()

  # 在 quality_review_node 完成后记录本次决策
  DecisionMemory().record_decision(plan, quality_passed=True, passed_checks=15)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from ai_trending.logger import get_logger

log = get_logger("decision_memory")

_DEFAULT_PATH = Path("output/DECISION_MEMORY.md")
_MAX_RECORDS = 14  # 保留最近 14 天记录


@dataclass
class DecisionRecord:
    """单次编辑决策记录。"""

    date: str
    signal_strength: str  # red / yellow / green
    headline_type: str  # repo / news
    angle_used: str  # 主要使用的切入角度
    kill_list_size: int
    quality_passed: bool  # 质量审核是否通过
    passed_checks: int  # 质量审核通过的检查项数（满分约 18）

    def to_table_row(self) -> str:
        status = "✅" if self.quality_passed else "❌"
        return (
            f"| {self.date} | {self.signal_strength} | {self.headline_type} "
            f"| {self.angle_used} | {self.kill_list_size} "
            f"| {status} {self.passed_checks}/18 |"
        )

    @staticmethod
    def from_table_row(row: str) -> DecisionRecord | None:
        raw_parts = row.split("|")
        # 去掉首尾空元素
        if raw_parts and not raw_parts[0].strip():
            raw_parts = raw_parts[1:]
        if raw_parts and not raw_parts[-1].strip():
            raw_parts = raw_parts[:-1]
        parts = [p.strip() for p in raw_parts]
        if len(parts) < 6:
            return None
        if parts[0] == "日期" or parts[0].startswith("---"):
            return None
        try:
            quality_str = parts[5]
            quality_passed = "✅" in quality_str
            passed_checks = 0
            if "/" in quality_str:
                num_part = quality_str.replace("✅", "").replace("❌", "").strip()
                passed_checks = int(num_part.split("/")[0].strip())
            return DecisionRecord(
                date=parts[0],
                signal_strength=parts[1],
                headline_type=parts[2],
                angle_used=parts[3],
                kill_list_size=int(parts[4]) if parts[4].isdigit() else 0,
                quality_passed=quality_passed,
                passed_checks=passed_checks,
            )
        except (ValueError, IndexError):
            return None


class DecisionMemory:
    """编辑决策记忆管理器 — 第三层记忆。

    记录什么样的编辑决策导致好/坏的日报，
    为下一次的 EditorialPlanningCrew 提供历史参考。
    """

    def __init__(self, memory_path: Path | None = None) -> None:
        self._path = memory_path or _DEFAULT_PATH
        self._path.parent.mkdir(parents=True, exist_ok=True)

    # ==================== 对外接口 ====================

    def get_decision_guidance(self) -> str:
        """获取编辑决策指导文本，注入到 editorial_planning Prompt 中。

        Returns:
            格式化的指导文本，包含历史决策规律总结
        """
        records = self._load_records()
        patterns = self._load_patterns()

        if not records and not patterns:
            return "（无历史编辑决策记录）"

        lines: list[str] = ["## 历史编辑决策参考"]

        # 好的决策模式
        if patterns:
            lines.append("\n### 效果好的决策模式")
            for p in patterns[:5]:
                lines.append(f"- {p}")

        # 近期质量趋势（最近 5 条）
        if records:
            recent = sorted(records, key=lambda r: r.date, reverse=True)[:5]
            lines.append("\n### 近期质量趋势")
            for r in recent:
                status = "通过" if r.quality_passed else "未通过"
                lines.append(
                    f"- {r.date}: {r.signal_strength} / {r.headline_type} / "
                    f"{r.angle_used} → {status}（{r.passed_checks}/18）"
                )

        # 统计规律
        stats = self._compute_stats(records)
        if stats:
            lines.append("\n### 统计规律")
            lines.extend(stats)

        return "\n".join(lines)

    def record_decision(
        self,
        date: str,
        signal_strength: str,
        headline_type: str,
        angle_used: str,
        kill_list_size: int,
        quality_passed: bool,
        passed_checks: int,
        good_patterns: list[str] | None = None,
    ) -> None:
        """记录一次编辑决策结果。

        Args:
            date:            日期 YYYY-MM-DD
            signal_strength: red/yellow/green
            headline_type:   repo/news
            angle_used:      主要使用的切入角度
            kill_list_size:  Kill List 大小
            quality_passed:  质量审核是否通过
            passed_checks:   通过的检查项数
            good_patterns:   本次发现的好决策模式
        """
        records, patterns = self._load_all()

        # 更新或插入记录
        existing = {r.date: i for i, r in enumerate(records)}
        new_record = DecisionRecord(
            date=date,
            signal_strength=signal_strength,
            headline_type=headline_type,
            angle_used=angle_used,
            kill_list_size=kill_list_size,
            quality_passed=quality_passed,
            passed_checks=passed_checks,
        )
        if date in existing:
            records[existing[date]] = new_record
        else:
            records.append(new_record)

        # 追加好的决策模式
        if good_patterns:
            for p in good_patterns:
                if p and p not in patterns:
                    patterns.append(p)

        # 自动清理过期记录（超过 14 天）
        cutoff = (datetime.now() - timedelta(days=_MAX_RECORDS)).strftime("%Y-%m-%d")
        records = [r for r in records if r.date >= cutoff]
        patterns = patterns[-20:]  # 最多保留 20 条模式

        self._save_all(records, patterns)
        log.info(
            f"[DecisionMemory] 记录编辑决策: {date} {signal_strength} passed={quality_passed}"
        )

    # ==================== 内部方法 ====================

    def _compute_stats(self, records: list[DecisionRecord]) -> list[str]:
        """从历史记录中计算统计规律。"""
        if len(records) < 3:
            return []

        stats: list[str] = []

        # 信号强度 vs 质量通过率
        signal_pass: dict[str, list[bool]] = {}
        for r in records:
            signal_pass.setdefault(r.signal_strength, []).append(r.quality_passed)

        for signal, results in signal_pass.items():
            if len(results) >= 2:
                pass_rate = sum(results) / len(results)
                stats.append(
                    f"信号强度 {signal}: 历史质量通过率 {pass_rate:.0%}（{len(results)} 次）"
                )

        # 切入角度 vs 质量
        angle_pass: dict[str, list[int]] = {}
        for r in records:
            if r.angle_used:
                angle_pass.setdefault(r.angle_used, []).append(r.passed_checks)

        for angle, checks in angle_pass.items():
            if len(checks) >= 2:
                avg = sum(checks) / len(checks)
                stats.append(f"角度 {angle}: 平均通过检查项 {avg:.1f}/18")

        return stats[:4]  # 最多返回 4 条统计

    def _load_all(self) -> tuple[list[DecisionRecord], list[str]]:
        """加载所有记录和模式。"""
        return self._load_records(), self._load_patterns()

    def _load_records(self) -> list[DecisionRecord]:
        """从文件加载决策记录。"""
        if not self._path.exists():
            return []
        try:
            content = self._path.read_text(encoding="utf-8")
        except Exception as e:
            log.warning(f"[DecisionMemory] 读取文件失败: {e}")
            return []

        records: list[DecisionRecord] = []
        in_table = False
        for line in content.splitlines():
            s = line.strip()
            if s.startswith("| 日期"):
                in_table = True
                continue
            if s.startswith("|---"):
                continue
            if in_table and s.startswith("|"):
                r = DecisionRecord.from_table_row(s)
                if r:
                    records.append(r)
            elif in_table and not s.startswith("|"):
                in_table = False
        return records

    def _load_patterns(self) -> list[str]:
        """从文件加载好的决策模式。"""
        if not self._path.exists():
            return []
        try:
            content = self._path.read_text(encoding="utf-8")
        except Exception:
            return []

        patterns: list[str] = []
        in_patterns = False
        for line in content.splitlines():
            s = line.strip()
            if "效果好的决策模式" in s:
                in_patterns = True
                continue
            if in_patterns and s.startswith("## "):
                in_patterns = False
                continue
            if in_patterns and s.startswith("- "):
                patterns.append(s[2:].strip())
        return patterns

    def _save_all(self, records: list[DecisionRecord], patterns: list[str]) -> None:
        """将所有数据写回文件。"""
        lines: list[str] = [
            "# 编辑决策记忆",
            "",
            "> 自动生成，记录编辑决策与日报质量的关联规律。",
            "",
        ]

        if patterns:
            lines += ["## ✅ 效果好的决策模式", ""]
            for p in patterns:
                lines.append(f"- {p}")
            lines.append("")

        if records:
            sorted_records = sorted(records, key=lambda r: r.date, reverse=True)
            lines += [
                "## 📊 决策质量记录",
                "",
                "| 日期 | 信号强度 | 头条类型 | 主角度 | Kill数 | 质量 |",
                "|------|---------|---------|-------|-------|------|",
            ]
            for r in sorted_records:
                lines.append(r.to_table_row())
            lines.append("")

        try:
            self._path.write_text("\n".join(lines), encoding="utf-8")
        except Exception as e:
            log.warning(f"[DecisionMemory] 写入文件失败: {e}")
