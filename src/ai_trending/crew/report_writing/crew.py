"""ReportWritingCrew — 负责将评分数据和新闻数据整合为规范格式的 AI 日报。

输入 inputs:
    github_data:    str  — GitHub 热点项目原始数据
    news_data:      str  — AI 新闻原始数据
    scoring_result: str  — 结构化评分 JSON 字符串
    current_date:   str  — 日期，格式 YYYY-MM-DD

输出 pydantic: ReportOutput
    content:           str       — 完整的 Markdown 日报正文
    validation_issues: list[str] — 格式校验问题列表（空列表表示通过）
"""

from __future__ import annotations

from crewai import Agent, Crew, Process, Task
from crewai.project import CrewBase, agent, crew, task

from ai_trending.llm_client import build_crewai_llm
from ai_trending.logger import get_logger

from .models import ReportOutput

log = get_logger("report_writing_crew")

# 日报必须包含的 Section 标题
_REQUIRED_SECTIONS = [
    "## 🔥 GitHub 热点项目",
    "## 📰 AI 热点新闻",
    "## 🧭 趋势洞察",
]

# 禁用词列表
_BANNED_WORDS = [
    "重磅", "震撼", "颠覆", "革命性", "划时代",
    "里程碑", "历史性", "强烈推荐", "必看", "不容错过",
    "太强了", "绝了", "牛逼", "未来已来", "新时代",
    "！", "!",
]


def _validate_report(content: str) -> list[str]:
    """校验日报内容是否符合规范，返回问题列表（空列表表示通过）。"""
    issues: list[str] = []

    # 结构检查
    for section in _REQUIRED_SECTIONS:
        if section not in content:
            issues.append(f"缺少必要 Section：{section}")

    # 字数检查（去除空格和换行后计算）
    char_count = len(content.replace(" ", "").replace("\n", ""))
    if char_count < 700:
        issues.append(f"内容过短：{char_count} 字（最少 700 字）")
    if char_count > 1500:
        issues.append(f"内容过长：{char_count} 字（最多 1500 字）")

    # 禁用词检查
    for word in _BANNED_WORDS:
        if word in content:
            issues.append(f"包含禁用词：「{word}」")

    return issues


def _fix_news_item_lines(line: str) -> list[str]:
    """将 LLM 把新闻三行内容挤在一行的情况拆分为独立三行。

    LLM 有时输出（全挤一行）：
      **[类别]** 标题 > 一句话判断 来源：xxx | [链接](url)
    需要拆分为：
      **[类别]** 标题
      > 一句话判断
      来源：xxx | [链接](url)
    """
    import re
    # 只处理以 **[类别]** 开头且包含 " > " 的行
    if not re.match(r"^\*\*\[", line):
        return [line]
    if " > " not in line:
        return [line]

    # 按 " > " 分割出标题和后半部分
    title_part, rest = line.split(" > ", 1)

    # 再从后半部分分割出判断和来源
    # 来源部分以 "来源：" 开头
    if "来源：" in rest:
        judgment_part, source_part = rest.split("来源：", 1)
        judgment_part = judgment_part.strip()
        source_part = "来源：" + source_part.strip()
    else:
        judgment_part = rest.strip()
        source_part = ""

    result = [title_part.strip()]
    if judgment_part:
        result.append(f"> {judgment_part}")
    if source_part:
        result.append(source_part)
    return result


def _fix_github_item_fields(line: str) -> list[str]:
    """将 LLM 把多个字段挤在一行的情况拆分为独立列表项。

    LLM 有时输出：
      - 🏷️ **类别**：xxx - 💻 **语言**：yyy - 📈 **趋势信号**：zzz
    需要拆分为：
      - 🏷️ **类别**：xxx
      - 💻 **语言**：yyy
      - 📈 **趋势信号**：zzz
    """
    import re
    # 只处理以 "- 🏷️" 开头且包含 " - 💻" 或 " - 📈" 的行（说明字段被挤在一行）
    if not re.match(r"^-\s+🏷", line):
        return [line]
    if " - 💻" not in line and " - 📈" not in line:
        return [line]

    # 按 " - 💻" 或 " - 📈" 分割，保留分隔符
    parts = re.split(r"\s+-\s+(?=💻|📈|🔗)", line)
    result = []
    for part in parts:
        part = part.strip()
        if part and not part.startswith("-"):
            part = "- " + part
        if part:
            result.append(part)
    return result


def _fix_markdown_spacing(content: str) -> str:
    """修正 Markdown 格式：确保标题行和链接行前有空行，修正字段挤一行问题。

    LLM 常见的格式问题：
    1. 标题（##/###）前缺少空行
    2. 🔗 链接行前缺少空行
    3. GitHub 项目的类别/语言/趋势信号字段被挤在同一行（用 ` - ` 分隔）
    4. 新闻条目（**[类别]** 开头）前缺少空行，导致被渲染成大标题
    """
    import re

    # 第一步：拆分挤在一行的情况（GitHub 字段 / 新闻三行）
    expanded_lines: list[str] = []
    for line in content.split("\n"):
        # 先尝试拆分新闻条目（**[类别]** 标题 > 判断 来源：xxx）
        news_lines = _fix_news_item_lines(line)
        if len(news_lines) > 1:
            expanded_lines.extend(news_lines)
        else:
            # 再尝试拆分 GitHub 字段（- 🏷️ ... - 💻 ... - 📈 ...）
            expanded_lines.extend(_fix_github_item_fields(line))

    # 第二步：补全缺失的空行
    result: list[str] = []
    for i, line in enumerate(expanded_lines):
        is_heading = re.match(r"^#{1,6}\s", line)
        is_link_item = re.match(r"^-\s+🔗", line)
        # 新闻条目以 **[类别]** 开头，前面必须有空行，否则会被渲染成大标题
        is_news_item = re.match(r"^\*\*\[", line)

        if (is_heading or is_link_item or is_news_item) and i > 0:
            prev = result[-1] if result else ""
            if prev.strip() != "":
                result.append("")

        result.append(line)

    return "\n".join(result)


@CrewBase
class ReportWritingCrew:
    """AI 日报撰写 Crew。

    职责：将 GitHub 热点数据、新闻数据、评分结果整合为规范格式的 Markdown 日报。
    使用 default 档 LLM，确保内容质量和格式准确性。
    """

    agents_config = "config/agents.yaml"
    tasks_config = "config/tasks.yaml"

    @agent
    def report_writer(self) -> Agent:
        """日报撰写 Agent，使用 default 档 LLM 保证内容质量。"""
        return Agent(
            config=self.agents_config["report_writer"],  # type: ignore[index]
            llm=build_crewai_llm("default"),
            allow_delegation=False,
            verbose=False,
        )

    @task
    def write_report_task(self) -> Task:
        """日报撰写 Task，输出结构化 ReportOutput。"""
        return Task(
            config=self.tasks_config["write_report_task"],  # type: ignore[index]
            output_pydantic=ReportOutput,
        )

    @crew
    def crew(self) -> Crew:
        """组装 ReportWritingCrew。"""
        return Crew(
            agents=self.agents,
            tasks=self.tasks,
            process=Process.sequential,
            verbose=False,
        )

    def run(
        self,
        github_data: str,
        news_data: str,
        scoring_result: str,
        current_date: str,
    ) -> ReportOutput:
        """对外公开入口：执行日报撰写，返回 ReportOutput。

        Args:
            github_data:    GitHub 热点项目原始数据字符串
            news_data:      AI 新闻原始数据字符串
            scoring_result: 结构化评分 JSON 字符串
            current_date:   日期，格式 YYYY-MM-DD

        Returns:
            ReportOutput，content 字段为完整 Markdown 日报，
            validation_issues 字段为格式校验问题列表。
        """
        log.info(f"[ReportWritingCrew] 开始撰写日报 ({current_date})")

        try:
            result = self.crew().kickoff(
                inputs={
                    "github_data": github_data or "无可用数据",
                    "news_data": news_data or "无可用数据",
                    "scoring_result": scoring_result or "{}",
                    "current_date": current_date,
                }
            )

            # 优先从 pydantic 输出获取
            output: ReportOutput | None = None
            if result.pydantic and isinstance(result.pydantic, ReportOutput):
                output = result.pydantic
            elif result.tasks_output:
                last = result.tasks_output[-1]
                if last.pydantic and isinstance(last.pydantic, ReportOutput):
                    output = last.pydantic

            # 兜底：从 raw 文本构造
            if output is None or not output.content:
                raw = result.raw or ""
                output = ReportOutput(content=raw)
                log.warning("[ReportWritingCrew] 未获取到 Pydantic 输出，使用 raw 文本兜底")

            # 修正 Markdown 格式（补全标题和链接前缺失的空行）
            fixed_content = _fix_markdown_spacing(output.content)
            if fixed_content != output.content:
                log.info("[ReportWritingCrew] 已自动修正 Markdown 空行格式")
                output = ReportOutput(content=fixed_content, validation_issues=output.validation_issues)

            # 格式校验（不阻断，只记录问题）
            issues = _validate_report(output.content)
            if issues:
                log.warning(f"[ReportWritingCrew] 格式校验发现 {len(issues)} 个问题: {issues}")
                output = ReportOutput(content=output.content, validation_issues=issues)

            log.info(
                f"[ReportWritingCrew] 完成，输出 {len(output.content)} 字符，"
                f"校验问题 {len(output.validation_issues)} 个"
            )
            return output

        except Exception as e:
            log.error(f"[ReportWritingCrew] 撰写失败: {e}")
            raise
