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

# 日报必须包含的 Section 标题（按新结构更新）
_REQUIRED_SECTIONS = [
    "## 🎯 今日头条",
    "## 🔥 GitHub 热点项目", 
    "## 📰 AI 热点新闻",
    "## 🧭 趋势洞察",
    "## 💡 本周行动建议",
]

# 新闻可信度标签（必须使用）
_NEWS_CREDIBILITY_LABELS = [
    "🟢 一手信源",
    "🟡 社区讨论", 
    "🔴 待验证",
]

# 今日信号强度标签（必须使用）
_SIGNAL_STRENGTH_LABELS = [
    "🔴 重大变化日",
    "🟡 常规更新日",
    "🟢 平静日",
]

# 禁用词列表
_BANNED_WORDS = [
    "重磅", "震撼", "颠覆", "革命性", "划时代",
    "里程碑", "历史性", "强烈推荐", "必看", "不容错过", 
    "太强了", "绝了", "牛逼", "未来已来", "新时代",
    "！", "!",
]

# 叙事风格关键词（必须包含）
_NARRATIVE_KEYWORDS = [
    "相当于", "的", "版", "一个月前", "现在", "实测", 
    "值得关注如果你", "值得注意的是", "真正的信号在于",
    "信息差", "悬念", "技术细节", "谁应该关注",
]

# So What 分析关键词（必须包含）
_SO_WHAT_KEYWORDS = [
    "所以呢", "实质是什么", "对谁有影响", "时间窗口",
    "值得注意的是", "真正的信号在于", "这意味着",
]


def _validate_report(content: str) -> list[str]:
    """校验日报内容是否符合新规范，返回问题列表（空列表表示通过）。"""
    issues: list[str] = []

    # 1. 结构检查（新结构）
    for section in _REQUIRED_SECTIONS:
        if section not in content:
            issues.append(f"缺少必要 Section：{section}")

    # 2. 今日信号强度检查
    signal_found = False
    for signal in _SIGNAL_STRENGTH_LABELS:
        if signal in content:
            signal_found = True
            break
    if not signal_found:
        issues.append("缺少今日信号强度标签（三选一：🔴 重大变化日 / 🟡 常规更新日 / 🟢 平静日）")

    # 3. 新闻可信度标签检查
    credibility_found = False
    for label in _NEWS_CREDIBILITY_LABELS:
        if label in content:
            credibility_found = True
            break
    if not credibility_found:
        issues.append("新闻条目缺少可信度标签（必须使用：🟢 一手信源 / 🟡 社区讨论 / 🔴 待验证）")

    # 4. 今日一句话检查（必须包含「今日一句话」标记）
    if "**[今日一句话]**" not in content:
        issues.append("缺少「今日一句话」开篇钩子")

    # 5. 场景化描述检查（GitHub 项目必须包含场景化描述）
    if "相当于" not in content and "的" not in content and "版" not in content:
        issues.append("GitHub 项目缺少场景化描述（必须用「相当于……的……版」句式）")

    # 6. So What 分析检查（新闻必须包含 So What 分析）
    so_what_found = False
    for keyword in _SO_WHAT_KEYWORDS:
        if keyword in content:
            so_what_found = True
            break
    if not so_what_found:
        issues.append("新闻条目缺少 So What 分析（必须回答：实质是什么、对谁有影响、时间窗口多长）")

    # 7. 本周行动建议检查
    if "**[本周作业]**" not in content and "**[讨论问题]**" not in content:
        issues.append("缺少本周行动建议（必须包含至少一项可落地的任务或讨论问题）")

    # 8. 星数上下文检查（必须包含本周增长信息）
    if "（+" not in content and "本周增长" not in content:
        issues.append("GitHub 项目星数缺少本周增长信息（格式：⭐ [star数]（+[本周增长]））")

    # 9. 头条机制检查（必须有头条深度解读）
    if "## 今日头条" in content:
        # 检查头条是否包含深度解读的四个维度
        headline_checks = [
            ("信息差悬念", "一个月前" or "现在" or "信息差"),
            ("技术细节支撑", "实测" or "技术细节" or "内核"),
            ("谁应该关注", "值得关注如果你" or "谁应该关注"),
            ("叙事完整性", "相当于" or "故事" or "情节")
        ]
        for check_name, keyword in headline_checks:
            if keyword not in content:
                issues.append(f"头条缺少{check_name}元素")

    # 10. 趋势洞察数据支撑检查
    if "## 趋势洞察" in content:
        # 检查趋势洞察是否有数据或对比支撑
        data_indicators = ["数据", "对比", "增长", "从", "相比", "同期", "明显快于", "显著高于"]
        has_data_support = any(indicator in content for indicator in data_indicators)
        if not has_data_support:
            issues.append("趋势洞察缺少数据或对比支撑（必须包含具体数据、对比信息或增长趋势）")

    # 11. 互动引导检查
    if "**[参与方式]**" not in content and "**[反馈与互动]**" not in content:
        issues.append("缺少互动引导（必须包含参与方式或反馈渠道）")

    # 12. 上期回顾检查（可选，但如果有必须包含追踪信息）
    if "## 上期回顾" in content:
        if "星数追踪" not in content and "趋势验证" not in content:
            issues.append("上期回顾缺少追踪信息（必须包含星数追踪和趋势验证）")

    # 13. 叙事风格检查（必须包含叙事元素）
    narrative_found = False
    for keyword in _NARRATIVE_KEYWORDS:
        if keyword in content:
            narrative_found = True
            break
    if not narrative_found:
        issues.append("内容缺少叙事风格元素（必须包含场景化描述、信息差悬念、技术细节等）")

    # 14. 三轮工作流检查（信息提取→判断生成→文案润色）
    # 检查是否有明显的三段式结构：信息提取（结构化）、判断生成（分析）、文案润色（叙事）
    has_structure = (
        "相当于" in content and  # 信息提取（场景化）
        "值得注意的是" in content and  # 判断生成（分析）
        "一个月前" in content  # 文案润色（叙事）
    )
    if not has_structure:
        issues.append("内容结构不符合三轮工作流要求（信息提取→判断生成→文案润色）")

    # 15. 字数检查（新范围 800-1600 字）
    char_count = len(content.replace(" ", "").replace("\n", ""))
    if char_count < 800:
        issues.append(f"内容过短：{char_count} 字（最少 800 字）")
    if char_count > 1600:
        issues.append(f"内容过长：{char_count} 字（最多 1600 字）")

    # 16. 禁用词检查
    for word in _BANNED_WORDS:
        if word in content:
            issues.append(f"包含禁用词：「{word}」")

    # 17. emoji密度检查（每100字不超过3个emoji）
    emoji_count = sum(1 for char in content if char in ["🔴", "🟡", "🟢", "🔥", "📰", "🧭", "💡", "📊", "📋", "💬"])
    if char_count > 0:
        emoji_density = emoji_count / (char_count / 100)
        if emoji_density > 3:
            issues.append(f"emoji密度过高：{emoji_density:.1f}个/100字（建议不超过3个）")

    # 18. 行动建议时效性检查
    if "**[本周作业]**" in content or "**[讨论问题]**" in content:
        if "为什么是这周而不是下周" not in content and "时效理由" not in content:
            issues.append("行动建议缺少时效性理由（必须包含「为什么是这周而不是下周」的理由）")

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
