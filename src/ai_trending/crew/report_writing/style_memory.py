"""写作风格记忆管理器 — 记录什么表达效果好、什么应该避免。

职责：
  - 读取/写入 output/STYLE_MEMORY.md 风格记忆文件
  - 获取风格指导文本，注入到写作 Prompt
  - 记录每次质量结果和好/坏表达模式
  - 检测近期重复使用的表达模式，自动标记为"应避免"

不负责：
  - LLM 调用（纯数据操作）
  - 内容分析（由 CrewAI Agent 完成）
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from pathlib import Path

from ai_trending.logger import get_logger

log = get_logger("style_memory")

# 默认风格记忆文件路径
_DEFAULT_MEMORY_PATH = Path("output/STYLE_MEMORY.md")

# 最大保留天数（质量记录）
MAX_QUALITY_DAYS = 14

# 重复使用阈值：同一表达出现 >= N 次就标记为"应避免"
REPEAT_THRESHOLD = 3


class QualityRecord:
    """单条质量记录。"""

    def __init__(
        self,
        date: str,
        passed_count: int,
        total_count: int,
        main_issues: list[str],
    ) -> None:
        self.date = date
        self.passed_count = passed_count
        self.total_count = total_count
        self.main_issues = main_issues

    def to_table_row(self) -> str:
        """转换为 Markdown 表格行。"""
        issues_str = "; ".join(self.main_issues) if self.main_issues else "无"
        return (
            f"| {self.date} | {self.passed_count}/{self.total_count} | {issues_str} |"
        )

    @staticmethod
    def from_table_row(row: str) -> QualityRecord | None:
        """从 Markdown 表格行解析。"""
        raw_parts = row.split("|")
        # 去掉首尾空元素
        if raw_parts and not raw_parts[0].strip():
            raw_parts = raw_parts[1:]
        if raw_parts and not raw_parts[-1].strip():
            raw_parts = raw_parts[:-1]
        parts = [p.strip() for p in raw_parts]
        if len(parts) < 3:
            return None
        # 跳过表头行
        if parts[0] == "日期" or parts[0].startswith("---"):
            return None
        # 解析通过数/总数
        score_parts = parts[1].split("/")
        try:
            passed = int(score_parts[0])
            total = int(score_parts[1]) if len(score_parts) > 1 else 18
        except (ValueError, IndexError):
            return None
        # 解析主要问题
        issues_str = parts[2] if len(parts) > 2 else ""
        issues = [
            i.strip() for i in issues_str.split(";") if i.strip() and i.strip() != "无"
        ]
        return QualityRecord(
            date=parts[0],
            passed_count=passed,
            total_count=total,
            main_issues=issues,
        )


class StyleMemory:
    """写作风格记忆管理器。

    读写 output/STYLE_MEMORY.md，维护好表达/坏表达列表和质量趋势。
    """

    def __init__(self, memory_path: Path | None = None) -> None:
        self._path = memory_path or _DEFAULT_MEMORY_PATH

    def get_style_guidance(self) -> str:
        """获取风格指导文本，用于注入到写作 Prompt。

        Returns:
            格式化的风格指导文本，包含好表达、坏表达和质量趋势。
            无记忆时返回提示文本。
        """
        good, bad, records = self._load_all()

        if not good and not bad and not records:
            return "（无风格记忆记录）"

        lines = ["## 风格记忆（请参考以优化写作质量）"]

        if good:
            lines.append("")
            lines.append("### 效果好的表达（可复用的模式）")
            for item in good[:5]:  # 最多展示 5 条
                lines.append(f"- {item}")

        if bad:
            lines.append("")
            lines.append("### 效果差的表达（应避免的模式）")
            for item in bad[:5]:  # 最多展示 5 条
                lines.append(f"- {item}")

        if records:
            lines.append("")
            lines.append("### 近期质量趋势")
            for record in records[:5]:  # 最多展示 5 条
                issues_str = (
                    "; ".join(record.main_issues[:2])
                    if record.main_issues
                    else "无主要问题"
                )
                lines.append(
                    f"- {record.date}: 通过 {record.passed_count}/{record.total_count} 项"
                    f"，主要问题：{issues_str}"
                )

        return "\n".join(lines)

    def record_quality_result(
        self,
        date: str,
        validation_issues: list[str],
        total_checks: int = 18,
        good_patterns: list[str] | None = None,
        bad_patterns: list[str] | None = None,
    ) -> None:
        """记录质量结果，更新风格记忆。

        Args:
            date:              日期字符串，格式 YYYY-MM-DD
            validation_issues: 格式校验发现的问题列表
            total_checks:      总检查项数（默认 18）
            good_patterns:     本次发现的好表达模式
            bad_patterns:      本次发现的坏表达模式
        """
        good, bad, records = self._load_all()

        # 更新好/坏表达列表
        if good_patterns:
            for p in good_patterns:
                if p and p not in good:
                    good.append(p)
        if bad_patterns:
            for p in bad_patterns:
                if p and p not in bad:
                    bad.append(p)

        # 保持列表大小合理
        good = good[:20]
        bad = bad[:20]

        # 提取主要问题（最多 3 个），去除重复类似的
        main_issues = self._extract_main_issues(validation_issues)

        # 检查是否已有同日记录，有则更新
        passed_count = total_checks - len(validation_issues)
        new_record = QualityRecord(
            date=date,
            passed_count=max(0, passed_count),
            total_count=total_checks,
            main_issues=main_issues,
        )
        updated = False
        for i, record in enumerate(records):
            if record.date == date:
                records[i] = new_record
                updated = True
                break
        if not updated:
            records.append(new_record)

        # 清理过期记录
        cutoff = self._cutoff_date(MAX_QUALITY_DAYS)
        records = [r for r in records if r.date >= cutoff]

        # 按日期倒序
        records.sort(key=lambda r: r.date, reverse=True)

        self._save_all(good, bad, records)
        log.info(
            f"[StyleMemory] 已记录质量结果: date={date}, "
            f"passed={passed_count}/{total_checks}, "
            f"good_patterns={len(good_patterns or [])}, "
            f"bad_patterns={len(bad_patterns or [])}"
        )

    def detect_repeated_patterns(self, content: str) -> list[str]:
        """检测内容中是否有近期重复使用的表达模式。

        从历史报告中提取高频句式，与当前内容对比。

        Args:
            content: 当前日报内容

        Returns:
            重复使用的表达模式列表
        """
        _, bad, _ = self._load_all()
        repeated: list[str] = []

        for pattern in bad:
            # 提取坏表达中的关键短语（引号内的部分）
            match = re.search(r'"([^"]+)"', pattern)
            if match:
                phrase = match.group(1)
                if phrase.lower() in content.lower():
                    repeated.append(pattern)

        return repeated

    def extract_patterns_from_report(self, content: str) -> tuple[list[str], list[str]]:
        """从日报内容中提取好/坏表达模式。

        好表达：使用了具体数据、时间窗口、场景锚定等高质量叙事技巧。
        坏表达：使用了模板化开头、重复句式等低质量模式。

        Args:
            content: 日报内容

        Returns:
            (good_patterns, bad_patterns)
        """
        good: list[str] = []
        bad: list[str] = []

        # 好表达检测
        good_indicators = [
            (r"发布\s*\d+\s*(小时|天|周)内", "用时间窗口制造紧迫感"),
            (r"星数(突破|增长)\s*\d+", "用星数增长数据增强说服力"),
            (r"实测.{2,30}(高出|快|低于)", "用实测数据对比增强可信度"),
            (r"如果你(日常|在做|正在)", "用场景锚定目标读者"),
            (r"与.{2,15}不同", "用对比突出差异化"),
        ]
        for pattern, description in good_indicators:
            match = re.search(pattern, content)
            if match:
                phrase = match.group(0)
                good.append(f'"{phrase}" — {description}')

        # 坏表达检测：模板化开头
        # 检查每个 section 的开头是否有重复句式
        sections = re.split(r"^##\s+", content, flags=re.MULTILINE)
        opening_phrases: list[str] = []
        for section in sections[1:]:  # 跳过标题前的内容
            lines = section.strip().splitlines()
            # 取 section 的第一段非空内容行
            for line in lines[1:]:  # 跳过 section 标题行
                line = line.strip()
                if line and not line.startswith(("#", "|", "---", ">", "*", "-")):
                    # 提取前 15 个字符作为"开头模式"
                    opening = line[:15]
                    opening_phrases.append(opening)
                    break

        # 检查是否有高度相似的开头
        for phrase in opening_phrases:
            count = sum(1 for p in opening_phrases if p[:8] == phrase[:8])
            if count >= 2:
                bad.append(f'"{phrase}…" — 多个 Section 使用类似开头，缺乏变化')
                break  # 只报告一次

        return good[:5], bad[:3]

    # ==================== 内部方法 ====================

    def _load_all(
        self,
    ) -> tuple[list[str], list[str], list[QualityRecord]]:
        """从 STYLE_MEMORY.md 加载所有数据。

        Returns:
            (good_patterns, bad_patterns, quality_records)
        """
        if not self._path.exists():
            return [], [], []

        try:
            content = self._path.read_text(encoding="utf-8")
        except Exception as e:
            log.warning(f"[StyleMemory] 读取风格记忆文件失败: {e}")
            return [], [], []

        good: list[str] = []
        bad: list[str] = []
        records: list[QualityRecord] = []

        current_section = ""
        in_quality_table = False

        for line in content.splitlines():
            stripped = line.strip()

            # 识别 section
            if "效果好的表达" in stripped:
                current_section = "good"
                continue
            elif "效果差的表达" in stripped:
                current_section = "bad"
                continue
            elif "质量趋势" in stripped:
                current_section = "quality"
                continue
            elif stripped.startswith("## ") or stripped.startswith("# "):
                current_section = ""
                in_quality_table = False
                continue

            # 解析列表项
            if current_section == "good" and stripped.startswith("- "):
                good.append(stripped[2:].strip())
            elif current_section == "bad" and stripped.startswith("- "):
                bad.append(stripped[2:].strip())
            elif current_section == "quality":
                # 质量趋势表格
                if stripped.startswith("| 日期"):
                    in_quality_table = True
                    continue
                if stripped.startswith("|---"):
                    continue
                if in_quality_table and stripped.startswith("|"):
                    record = QualityRecord.from_table_row(stripped)
                    if record:
                        records.append(record)
                elif in_quality_table and not stripped.startswith("|"):
                    in_quality_table = False

        return good, bad, records

    def _save_all(
        self,
        good: list[str],
        bad: list[str],
        records: list[QualityRecord],
    ) -> None:
        """将所有数据写入 STYLE_MEMORY.md。"""
        self._path.parent.mkdir(parents=True, exist_ok=True)

        lines = ["# 写作风格记忆", ""]

        # 好表达
        lines.append("## ✅ 效果好的表达（可复用的模式）")
        lines.append("")
        if good:
            for item in good:
                lines.append(f"- {item}")
        else:
            lines.append("- （暂无记录）")

        lines.append("")

        # 坏表达
        lines.append("## ❌ 效果差的表达（应避免的模式）")
        lines.append("")
        if bad:
            for item in bad:
                lines.append(f"- {item}")
        else:
            lines.append("- （暂无记录）")

        lines.append("")

        # 质量趋势
        lines.append("## 📊 质量趋势")
        lines.append("")
        lines.append("| 日期 | 通过项 | 主要问题 |")
        lines.append("|------|-------|---------|")
        for record in records:
            lines.append(record.to_table_row())

        lines.append("")  # 尾部空行
        self._path.write_text("\n".join(lines), encoding="utf-8")

    def _extract_main_issues(
        self, validation_issues: list[str], max_count: int = 3
    ) -> list[str]:
        """从校验问题列表中提取主要问题类别。

        将具体问题归类为简短标签，避免记录过长。
        """
        if not validation_issues:
            return []

        # 问题分类映射
        category_map = [
            ("Section", ["缺少必要 Section"]),
            ("信号强度", ["信号强度"]),
            ("可信度标签", ["可信度标签"]),
            ("今日一句话", ["今日一句话"]),
            ("So What", ["So What"]),
            ("行动建议", ["行动建议"]),
            ("星数增长", ["星数", "本周增长"]),
            ("头条叙事", ["头条缺少", "信息差", "技术细节", "谁应该"]),
            ("趋势数据", ["趋势洞察"]),
            ("互动引导", ["互动引导", "参与方式"]),
            ("叙事风格", ["叙事风格"]),
            ("字数问题", ["内容过短", "内容过长"]),
            ("禁用词", ["禁用词"]),
            ("emoji密度", ["emoji"]),
            ("时效性", ["时效性"]),
            ("禁止句式", ["禁止句式"]),
        ]

        found_categories: list[str] = []
        for issue in validation_issues:
            for category, keywords in category_map:
                if any(kw in issue for kw in keywords):
                    if category not in found_categories:
                        found_categories.append(category)
                    break
            else:
                # 未匹配到分类，直接截取前 20 字符
                short = issue[:20].rstrip("（")
                if short not in found_categories:
                    found_categories.append(short)

        return found_categories[:max_count]

    @staticmethod
    def _cutoff_date(days: int) -> str:
        """计算 N 天前的日期字符串。"""
        cutoff = datetime.now() - timedelta(days=days)
        return cutoff.strftime("%Y-%m-%d")
