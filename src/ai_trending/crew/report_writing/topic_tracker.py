"""话题连续性追踪器 — 记录最近 7 天覆盖的话题，避免连续雷同。

职责：
  - 读取/写入 output/TOPIC_TRACKER.md 追踪记录
  - 获取最近 7 天的话题记录
  - 生成 Kill List（近 3 天已深度报道的话题，建议降级或跳过）
  - 记录当日话题（写作完成后调用）
  - 自动清理超过 7 天的旧记录

不负责：
  - LLM 调用（纯数据操作）
  - 内容分析（由 CrewAI Agent 完成）
"""

from __future__ import annotations

import re
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

from ai_trending.logger import get_logger

log = get_logger("topic_tracker")

# 默认追踪文件路径
_DEFAULT_TRACKER_PATH = Path("output/TOPIC_TRACKER.md")

# 最大保留天数
MAX_DAYS = 7

# Kill List 判断窗口（近 N 天）
KILL_LIST_DAYS = 3


class TopicRecord:
    """单条话题记录。"""

    def __init__(
        self,
        date: str,
        headline: str,
        keywords: list[str],
        hook: str,
    ) -> None:
        self.date = date
        self.headline = headline
        self.keywords = keywords
        self.hook = hook

    def to_table_row(self) -> str:
        """转换为 Markdown 表格行。"""
        kw_str = ", ".join(self.keywords) if self.keywords else ""
        return f"| {self.date} | {self.headline} | {kw_str} | {self.hook} |"

    @staticmethod
    def from_table_row(row: str) -> TopicRecord | None:
        """从 Markdown 表格行解析。"""
        # split("|") 会在首尾产生空串，需要去掉首尾但保留中间空字段
        raw_parts = row.split("|")
        # 去掉首尾空元素（"| a | b |".split("|") => ["", " a ", " b ", ""]）
        if raw_parts and not raw_parts[0].strip():
            raw_parts = raw_parts[1:]
        if raw_parts and not raw_parts[-1].strip():
            raw_parts = raw_parts[:-1]
        parts = [p.strip() for p in raw_parts]
        if len(parts) < 4:
            return None
        # 跳过表头行
        if parts[0] == "日期" or parts[0].startswith("---"):
            return None
        return TopicRecord(
            date=parts[0],
            headline=parts[1],
            keywords=[kw.strip() for kw in parts[2].split(",") if kw.strip()],
            hook=parts[3],
        )


class TopicTracker:
    """话题连续性追踪器。

    读写 output/TOPIC_TRACKER.md，记录最近 7 天覆盖的话题。
    """

    def __init__(self, tracker_path: Path | None = None) -> None:
        self._path = tracker_path or _DEFAULT_TRACKER_PATH

    def get_recent_topics(self) -> list[TopicRecord]:
        """获取最近 7 天的话题记录，按日期倒序排列。"""
        records = self._load_records()
        cutoff = self._cutoff_date(MAX_DAYS)
        recent = [r for r in records if r.date >= cutoff]
        recent.sort(key=lambda r: r.date, reverse=True)
        return recent

    def get_kill_list(self, days: int = KILL_LIST_DAYS) -> list[str]:
        """获取近 N 天已深度报道的话题，建议本期降级。

        规则：
        - 近 N 天内出现 >= 2 次的关键词 → 建议降级
        - 近 2 天内作为头条的话题 → 建议跳过或降级

        Returns:
            Kill List 条目列表，如 ["MCP（已连续 2 天作为头条，建议降级）"]
        """
        records = self._load_records()
        cutoff = self._cutoff_date(days)
        recent = [r for r in records if r.date >= cutoff]

        if not recent:
            return []

        kill_items: list[str] = []

        # 统计关键词出现频次
        kw_counter: Counter[str] = Counter()
        for record in recent:
            for kw in record.keywords:
                kw_counter[kw.lower()] += 1

        # 出现 >= 2 次的关键词
        for kw, count in kw_counter.most_common():
            if count >= 2:
                kill_items.append(f"{kw}（近{days}天出现{count}次，建议降级或换角度）")

        # 近 2 天内的头条话题
        cutoff_2d = self._cutoff_date(2)
        recent_headlines = [r.headline for r in recent if r.date >= cutoff_2d]
        for headline in recent_headlines:
            # 避免与关键词重复
            if not any(headline.lower() in item.lower() for item in kill_items):
                kill_items.append(f"{headline}（近期头条，除非有重大更新否则建议跳过）")

        return kill_items

    def get_topic_context(self) -> str:
        """获取话题上下文文本，用于注入到 editorial_planning Prompt。"""
        recent = self.get_recent_topics()
        kill_list = self.get_kill_list()

        if not recent and not kill_list:
            return "（无近期话题追踪记录）"

        lines = ["## 近期话题追踪（请参考以避免连续雷同）"]

        if recent:
            lines.append("")
            lines.append("| 日期 | 头条话题 | 覆盖关键词 | 今日一句话 |")
            lines.append("|------|---------|-----------|-----------|")
            for record in recent[:MAX_DAYS]:
                lines.append(record.to_table_row())

        if kill_list:
            lines.append("")
            lines.append("### Kill List（近期已深度报道，建议降级或跳过）")
            for item in kill_list:
                lines.append(f"- {item}")

        return "\n".join(lines)

    def record_today(
        self,
        date: str,
        headline: str,
        keywords: list[str],
        hook: str,
    ) -> None:
        """记录今日话题，并自动清理超过 7 天的旧记录。

        Args:
            date:     日期字符串，格式 YYYY-MM-DD
            headline: 今日头条话题
            keywords: 覆盖关键词列表
            hook:     今日一句话
        """
        records = self._load_records()

        # 检查是否已有同日记录，有则更新
        updated = False
        for i, record in enumerate(records):
            if record.date == date:
                records[i] = TopicRecord(date, headline, keywords, hook)
                updated = True
                break
        if not updated:
            records.append(TopicRecord(date, headline, keywords, hook))

        # 清理超过 MAX_DAYS 的旧记录
        cutoff = self._cutoff_date(MAX_DAYS)
        records = [r for r in records if r.date >= cutoff]

        # 按日期倒序排列
        records.sort(key=lambda r: r.date, reverse=True)

        # 写回文件
        self._save_records(records)
        log.info(
            f"[TopicTracker] 已记录今日话题: date={date}, headline={headline}, "
            f"keywords={keywords}, 当前共 {len(records)} 条记录"
        )

    def _load_records(self) -> list[TopicRecord]:
        """从 TOPIC_TRACKER.md 加载话题记录。"""
        if not self._path.exists():
            return []

        try:
            content = self._path.read_text(encoding="utf-8")
        except Exception as e:
            log.warning(f"[TopicTracker] 读取追踪文件失败: {e}")
            return []

        records: list[TopicRecord] = []
        in_table = False

        for line in content.splitlines():
            line = line.strip()
            # 检测表格开始
            if line.startswith("| 日期"):
                in_table = True
                continue
            # 跳过分隔行
            if line.startswith("|---"):
                continue
            # 解析表格行
            if in_table and line.startswith("|"):
                record = TopicRecord.from_table_row(line)
                if record:
                    records.append(record)
            elif in_table and not line.startswith("|"):
                in_table = False

        return records

    def _save_records(self, records: list[TopicRecord]) -> None:
        """将话题记录写入 TOPIC_TRACKER.md。"""
        self._path.parent.mkdir(parents=True, exist_ok=True)

        lines = [
            "# 话题追踪记录",
            "",
            "## 最近 7 天覆盖话题",
            "",
            "| 日期 | 头条话题 | 覆盖关键词 | 今日一句话 |",
            "|------|---------|-----------|-----------|",
        ]
        for record in records:
            lines.append(record.to_table_row())

        # Kill List — 直接从传入的 records 计算，避免递归调用 _load_records
        kill_items = self._compute_kill_list(records)
        if kill_items:
            lines.append("")
            lines.append("## Kill List（近 3 天已深度报道）")
            for item in kill_items:
                lines.append(f"- {item}")

        lines.append("")  # 尾部空行
        self._path.write_text("\n".join(lines), encoding="utf-8")

    def _compute_kill_list(self, records: list[TopicRecord]) -> list[str]:
        """从给定的 records 计算 Kill List（不调用 _load_records，避免循环）。"""
        cutoff = self._cutoff_date(KILL_LIST_DAYS)
        recent = [r for r in records if r.date >= cutoff]

        if not recent:
            return []

        kill_items: list[str] = []

        # 统计关键词出现频次
        kw_counter: Counter[str] = Counter()
        for record in recent:
            for kw in record.keywords:
                kw_counter[kw.lower()] += 1

        for kw, count in kw_counter.most_common():
            if count >= 2:
                kill_items.append(
                    f"{kw}（近{KILL_LIST_DAYS}天出现{count}次，建议降级或换角度）"
                )

        # 近 2 天内的头条话题
        cutoff_2d = self._cutoff_date(2)
        recent_headlines = [r.headline for r in recent if r.date >= cutoff_2d]
        for headline in recent_headlines:
            if not any(headline.lower() in item.lower() for item in kill_items):
                kill_items.append(f"{headline}（近期头条，除非有重大更新否则建议跳过）")

        return kill_items

    @staticmethod
    def _cutoff_date(days: int) -> str:
        """计算 N 天前的日期字符串。"""
        cutoff = datetime.now() - timedelta(days=days)
        return cutoff.strftime("%Y-%m-%d")

    @staticmethod
    def extract_keywords_from_report(report_content: str) -> list[str]:
        """从日报内容中提取覆盖关键词（简单规则提取）。

        提取 ## 标题中提到的项目名和技术关键词。
        """
        keywords: list[str] = []

        # 提取 ### 标题中的项目名（如 [项目名](url)）
        link_pattern = re.compile(r"\[([^\]]+)\]\(https?://[^\)]+\)")
        for match in link_pattern.finditer(report_content):
            name = match.group(1).strip()
            if name and len(name) < 50:  # 排除过长的文本
                keywords.append(name)

        # 提取常见技术关键词
        tech_keywords = [
            "AI",
            "LLM",
            "Agent",
            "MCP",
            "RAG",
            "GPT",
            "Claude",
            "Gemini",
            "Llama",
            "Mistral",
            "OpenAI",
            "Anthropic",
            "DeepSeek",
            "transformer",
            "diffusion",
            "多模态",
            "微调",
            "推理",
            "编程助手",
            "代码生成",
        ]
        content_lower = report_content.lower()
        for kw in tech_keywords:
            if kw.lower() in content_lower:
                keywords.append(kw)

        # 去重保序
        seen: set[str] = set()
        unique: list[str] = []
        for kw in keywords:
            kw_lower = kw.lower()
            if kw_lower not in seen:
                seen.add(kw_lower)
                unique.append(kw)

        return unique[:10]  # 最多返回 10 个

    @staticmethod
    def extract_headline_from_report(report_content: str) -> str:
        """从日报内容中提取头条话题（取 ## 今日头条 下的第一个 ### 标题）。"""
        in_headline_section = False
        for line in report_content.splitlines():
            if "## 今日头条" in line:
                in_headline_section = True
                continue
            if in_headline_section and line.startswith("### "):
                # 提取标题文本，去掉 Markdown 链接格式
                title = line.lstrip("# ").strip()
                # 去掉 [xxx](url) 中的 url 部分
                title = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", title)
                # 去掉星数等后缀
                title = re.split(r"\s+⭐", title)[0].strip()
                return title
            if (
                in_headline_section
                and line.startswith("## ")
                and "今日头条" not in line
            ):
                break  # 进入下一个 Section，没找到

        return ""

    @staticmethod
    def extract_hook_from_report(report_content: str) -> str:
        """从日报内容中提取'今日一句话'。"""
        for line in report_content.splitlines():
            if "今日一句话" in line:
                # 提取 **[今日一句话]** 后面的文本
                match = re.search(r"今日一句话[】\]]\*{0,2}\s*(.+)", line)
                if match:
                    return match.group(1).strip()
                # 备选：直接取冒号/括号后的内容
                match = re.search(r"今日一句话\S*\s+(.+)", line)
                if match:
                    return match.group(1).strip()
        return ""
