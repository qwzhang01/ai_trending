"""ReportWritingCrew — 负责将评分数据和新闻数据整合为规范格式的 AI 日报。

输入 inputs:
    github_data:    str  — GitHub 热点项目原始数据
    news_data:      str  — AI 新闻原始数据
    scoring_result: str  — 结构化评分 JSON 字符串
    current_date:   str  — 日期，格式 YYYY-MM-DD

输出 pydantic: ReportOutput
    content:           str       — 完整的 Markdown 日报正文
    validation_issues: list[str] — 格式校验问题列表（空列表表示通过）

日报七段式结构（与 tasks.yaml 保持一致）：
    1. 标题行（含今日信号强度 + 今日一句话）
    2. ## 今日头条（1 条深度解读，150-200 字）
    3. ## GitHub 热点项目（2-4 个，含星数增长上下文）
    4. ## AI 热点新闻（4-6 条，含可信度标签 + So What 分析，严格 3 行格式）
    5. ## 趋势洞察（3-5 条，含数据支撑和前瞻预判）
    6. ## 本周行动建议（1-2 条可落地任务，含时效性理由）
    7. ## 上期回顾（可选，追踪上周推荐项目后续发展）

注意：本模块实现的是七段式结构，与旧版四段式规范文档不同，以本文件和 tasks.yaml 为准。
"""

from __future__ import annotations

from crewai import Agent, Crew, Process, Task
from crewai.project import CrewBase, agent, crew, task

from ai_trending.llm_client import build_crewai_llm
from ai_trending.logger import get_logger

from ..trend_scoring.crew import _extract_token_usage
from .models import ReportOutput

log = get_logger("report_writing_crew")

# 日报必须包含的 Section 标题（与 tasks.yaml 输出格式保持一致）
_REQUIRED_SECTIONS = [
    "## 今日头条",
    "## GitHub 热点项目",
    "## AI 热点新闻",
    "## 趋势洞察",
    "## 本周行动建议",
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

# 禁用词列表（与 tasks.yaml 约束保持一致）
_BANNED_WORDS = [
    # 情绪化渲染词
    "重磅",
    "震撼",
    "颠覆",
    "革命性",
    "划时代",
    "里程碑",
    "历史性",
    "强烈推荐",
    "必看",
    "不容错过",
    "太强了",
    "绝了",
    "牛逼",
    "未来已来",
    "新时代",
    # 感叹号
    "！",
    "!",
    # tasks.yaml 明确禁止的套话（每期最多用1次的句式不在此列）
    "重新定义",
    "拓展新边界",
    "具有重要意义",
    # 禁止的比喻句式
    "相当于",
    # 禁止的自创评分
    "综合评分",
    "趋势代表性满分",
    # 禁止的同义反复
    "因为需求大所以增长快",
]

# 叙事风格关键词（至少包含其中一个，验证叙事性写作风格）
# 注：移除「现在」「相当于」等过宽泛或已被禁止的词
_NARRATIVE_KEYWORDS = [
    "一个月前",
    "实测",
    "值得关注如果你",
    "值得注意的是",
    "真正的信号在于",
    "信息差",
    "谁应该关注",
    "增速是",
    "发布仅",
    "星数突破",
    "如果你在做",
    "痛点",
    "对比",
]

# So What 分析关键词（必须包含）
_SO_WHAT_KEYWORDS = [
    "So What",  # 英文格式（实际输出中常用）
    "所以呢",
    "实质是什么",
    "对谁有影响",
    "时间窗口",
    "值得注意的是",
    "真正的信号在于",
    "这意味着",
]


def _validate_report(content: str) -> list[str]:
    """校验日报内容是否符合七段式规范，返回问题列表（空列表表示通过）。

    校验规则与 tasks.yaml 的输出约束保持一致。
    校验失败不阻断发布流程，问题记录到 validation_issues 字段。
    """
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
        issues.append(
            "缺少今日信号强度标签（三选一：🔴 重大变化日 / 🟡 常规更新日 / 🟢 平静日）"
        )

    # 3. 新闻可信度标签检查
    credibility_found = False
    for label in _NEWS_CREDIBILITY_LABELS:
        if label in content:
            credibility_found = True
            break
    if not credibility_found:
        issues.append(
            "新闻条目缺少可信度标签（必须使用：🟢 一手信源 / 🟡 社区讨论 / 🔴 待验证）"
        )

    # 4. 今日一句话检查（必须包含「今日一句话」标记）
    if "**[今日一句话]**" not in content:
        issues.append("缺少「今日一句话」开篇钩子")

    # 5. 新闻3行格式检查（新闻必须包含 So What 分析，且必须有换行）
    # 注：移除「相当于……的……版」句式检查，因为 tasks.yaml 已明确禁止该句式

    # 6. So What 分析检查（新闻必须包含 So What 分析）
    so_what_found = False
    for keyword in _SO_WHAT_KEYWORDS:
        if keyword in content:
            so_what_found = True
            break
    if not so_what_found:
        issues.append(
            "新闻条目缺少 So What 分析（必须回答：实质是什么、对谁有影响、时间窗口多长）"
        )

    # 7. 本周行动建议检查（兼容多种格式）
    has_action = (
        "**[本周作业]**" in content
        or "**[讨论问题]**" in content
        or "本周作业" in content
        or "讨论问题" in content
    )
    if not has_action:
        issues.append("缺少本周行动建议（必须包含至少一项可落地的任务或讨论问题）")

    # 8. 星数上下文检查（必须包含本周增长信息）
    if "（+" not in content and "本周增长" not in content:
        issues.append(
            "GitHub 项目星数缺少本周增长信息（格式：⭐ [star数]（+[本周增长]））"
        )

    # 9. 头条机制检查（必须有头条深度解读）
    if "## 今日头条" in content:
        # 检查头条是否包含叙事性内容（移除「相当于……版」检查，因为已禁止该句式）
        headline_checks = [
            ("信息差悬念", ["一个月前", "信息差", "还没人听过", "现在它是", "发布仅"]),
            ("技术细节支撑", ["实测", "技术细节", "内核", "吞吐量", "增速是", "倍"]),
            ("谁应该关注", ["值得关注如果你", "谁应该关注", "面向", "如果你在做"]),
        ]
        for check_name, keywords in headline_checks:
            if not any(kw in content for kw in keywords):
                issues.append(f"头条缺少{check_name}元素")

    # 10. 趋势洞察数据支撑检查
    if "## 趋势洞察" in content:
        # 检查趋势洞察是否有数据或对比支撑
        data_indicators = [
            "数据",
            "对比",
            "增长",
            "从",
            "相比",
            "同期",
            "明显快于",
            "显著高于",
        ]
        has_data_support = any(indicator in content for indicator in data_indicators)
        if not has_data_support:
            issues.append(
                "趋势洞察缺少数据或对比支撑（必须包含具体数据、对比信息或增长趋势）"
            )

    # 11. 互动引导检查（兼容多种格式）
    has_interaction = (
        "**[参与方式]**" in content
        or "**[反馈与互动]**" in content
        or "参与方式" in content
        or "反馈与互动" in content
        or "欢迎分享" in content
        or "评论区" in content
    )
    if not has_interaction:
        issues.append("缺少互动引导（必须包含参与方式或反馈渠道）")

    # 12. 上期回顾检查（可选，但如果有必须包含追踪信息）
    if "## 上期回顾" in content:
        if "星数追踪" not in content and "趋势验证" not in content:
            issues.append("上期回顾缺少追踪信息（必须包含星数追踪和趋势验证）")

    # 13. 叙事风格检查（必须包含叙事元素，验证非模板化写作）
    narrative_found = any(kw in content for kw in _NARRATIVE_KEYWORDS)
    if not narrative_found:
        issues.append(
            "内容缺少叙事风格元素（应包含信息差悬念、技术细节、对比锐点等，如：实测/增速是/发布仅/如果你在做）"
        )

    # 14. 字数检查（与 tasks.yaml 约束一致：800-2000 字）
    char_count = len(content.replace(" ", "").replace("\n", ""))
    if char_count < 800:
        issues.append(f"内容过短：{char_count} 字（最少 800 字）")
    if char_count > 2000:
        issues.append(f"内容过长：{char_count} 字（建议不超过 2000 字）")

    # 15. 禁用词检查（覆盖 tasks.yaml 约束 3/8/17 条）
    for word in _BANNED_WORDS:
        if word in content:
            issues.append(f"包含禁用词：「{word}」")

    # 16. emoji密度检查（每100字不超过3个emoji）
    emoji_count = sum(
        1
        for char in content
        if char in ["🔴", "🟡", "🟢", "🔥", "📰", "🧭", "💡", "📊", "📋", "💬"]
    )
    if char_count > 0:
        emoji_density = emoji_count / (char_count / 100)
        if emoji_density > 3:
            issues.append(
                f"emoji密度过高：{emoji_density:.1f}个/100字（建议不超过3个）"
            )

    # 17. 行动建议时效性检查（对应 tasks.yaml 约束 13 条）
    if "本周作业" in content or "讨论问题" in content:
        if "时效理由" not in content and "为什么是这周" not in content:
            issues.append(
                "行动建议缺少时效性理由（建议包含「为什么是这周而不是下周」的理由）"
            )

    # 18. 禁止句式检查（tasks.yaml 约束 8/17 条：禁止「相当于……的……版」句式）
    import re as _re

    if _re.search(r"相当于.{1,20}的.{1,10}版", content):
        issues.append(
            "包含禁止句式：「相当于……的……版」（tasks.yaml 约束 8 条明确禁止）"
        )

    return issues


def _fix_markdown_spacing(content: str) -> str:
    """最小兜底：确保 ## 标题前有空行，避免 Markdown 渲染错乱。

    Prompt 已通过强约束要求 LLM 输出正确格式（新闻三行、字段独立行等），
    此函数只处理最基础的标题空行问题作为最后防线，不再做复杂的内容拆分。
    """
    import re

    lines = content.split("\n")
    result: list[str] = []
    for i, line in enumerate(lines):
        # ## 标题前确保有空行（兜底：LLM 偶尔漏掉空行）
        if re.match(r"^#{1,6}\s", line) and i > 0:
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
        previous_report_context: str = "",
    ) -> tuple[ReportOutput, dict[str, int]]:
        """对外公开入口：执行日报撰写，返回 (ReportOutput, token_usage)。

        Args:
            github_data:              GitHub 热点项目原始数据字符串
            news_data:                AI 新闻原始数据字符串
            scoring_result:           结构化评分 JSON 字符串
            current_date:             日期，格式 YYYY-MM-DD
            previous_report_context:  上期回顾追踪数据（由 PreviousReportTracker 生成），
                                      为空时 LLM 将省略「上期回顾」Section

        Returns:
            (ReportOutput, token_usage_dict)，其中 token_usage_dict 包含
            prompt_tokens、completion_tokens、total_tokens、successful_requests。
        """
        log.info(f"[ReportWritingCrew] 开始撰写日报 ({current_date})")
        if previous_report_context:
            log.info("[ReportWritingCrew] 已注入上期回顾追踪数据")
        else:
            log.info("[ReportWritingCrew] 无上期回顾数据，将省略上期回顾 Section")

        try:
            result = self.crew().kickoff(
                inputs={
                    "github_data": github_data or "无可用数据",
                    "news_data": news_data or "无可用数据",
                    "scoring_result": scoring_result or "{}",
                    "current_date": current_date,
                    "previous_report_context": previous_report_context
                    or "（无上期数据，请省略「上期回顾」Section）",
                }
            )

            # 提取 token 用量
            token_usage = _extract_token_usage(result)

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
                log.warning(
                    "[ReportWritingCrew] 未获取到 Pydantic 输出，使用 raw 文本兜底"
                )

            # 修正 Markdown 格式（补全标题前缺失的空行）
            fixed_content = _fix_markdown_spacing(output.content)
            if fixed_content != output.content:
                log.info("[ReportWritingCrew] 已自动修正 Markdown 空行格式")
                output = ReportOutput(
                    content=fixed_content, validation_issues=output.validation_issues
                )

            # 格式校验（不阻断，只记录问题）
            issues = _validate_report(output.content)
            if issues:
                log.warning(
                    f"[ReportWritingCrew] 格式校验发现 {len(issues)} 个问题: {issues}"
                )
                output = ReportOutput(content=output.content, validation_issues=issues)

            log.info(
                f"[ReportWritingCrew] 完成，输出 {len(output.content)} 字符，"
                f"校验问题 {len(output.validation_issues)} 个，"
                f"token 用量 {token_usage.get('total_tokens', 0)}"
            )
            return output, token_usage

        except Exception as e:
            log.error(f"[ReportWritingCrew] 撰写失败: {e}")
            raise
