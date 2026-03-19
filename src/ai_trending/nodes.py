"""LangGraph 节点实现 — 每个节点是流水线中的一个独立步骤.

节点职责:
  - collect_github_node: 调用 GitHubTrendingTool 抓取热门项目 + LLM 筛选
  - collect_news_node:   调用 AINewsTool 抓取行业新闻 + LLM 筛选
  - score_trends_node:   LLM 结构化评分（核心差异点）
  - write_report_node:   LLM 撰写 Markdown 日报
  - publish_node:        调用 publish tools 推送到各渠道

设计原则:
  - 每个节点只读取需要的 state 字段，写入自己负责的字段
  - Tool 调用和 LLM 调用分离，便于独立测试
  - 采集节点内部使用 CrewAI Agent 做 LLM 驱动的工具调用（发挥 CrewAI 的 tool-use 优势）
  - 评分和写作节点直接调用 LiteLLM（更精确的 prompt 控制）
"""

from __future__ import annotations

import os
from typing import Any

from ai_trending.logger import get_logger
from ai_trending.llm_client import call_llm, call_llm_with_usage

log = get_logger("nodes")


# ==================== Prompt 模板 ====================

GITHUB_SYSTEM_PROMPT = """你是一位资深的开源社区观察者和 AI 技术专家，专注于识别具有真正技术创新价值的项目。
你的判断标准：技术新颖性 > Star 数量。你能区分「真正的技术突破」和「包装精良的工具封装」。
你的输出简洁、克制，只说关键信息，不堆砌形容词。"""

GITHUB_PROMPT_TEMPLATE = """以下是通过 GitHub API 搜索到的 AI 相关热门项目原始数据:

{raw_data}

请从中筛选出最有价值的 Top 5 项目，严格按以下格式输出每个项目:

### [项目名] | ⭐ [Star数] | [语言]
**定位**: [一句话，不超过25字，说清楚它解决什么问题]
**亮点**: [一句话，不超过40字，说明技术创新点或为什么值得关注]
🔗 [GitHub链接]

筛选标准:
- 优先选近期（30天内）有实质性更新的项目
- 优先选技术方向新颖的（新架构、新范式），而非功能堆砌
- 排除纯工具封装、UI 套壳、教程类项目
- 按综合价值（技术新颖性 × 社区热度）从高到低排列

不要输出任何解释性文字，只输出5个项目的格式化内容。

当前日期: {current_date}"""

NEWS_SYSTEM_PROMPT = """你是一位 AI 行业分析师，擅长从信息噪音中提炼真正有价值的信号。
你的原则：一条新闻如果不能回答「这对行业意味着什么」，就不值得收录。
你的文风：克制、精准、有判断力。不用感叹号，不用「重磅」「颠覆」等词，用事实说话。"""

NEWS_PROMPT_TEMPLATE = """以下是通过多个新闻源搜集到的 AI 行业新闻原始数据:

{raw_data}

请筛选出最有价值的 8 条新闻，严格按以下格式输出:

**[类别标签]** [新闻标题]
> [一句话判断：这件事的实质是什么，对行业有什么影响，不超过35字]
来源: [来源名] | [链接]

类别标签只能是以下之一: `大厂动态` `技术突破` `开源生态` `投融资` `行业观察`

筛选标准:
- 优先选有实质内容的新闻（发布了什么、做了什么），排除纯预测和观点文章
- 同一公司/事件只保留最重要的一条
- 按新闻重要性从高到低排列

不要输出任何解释性文字，只输出8条新闻的格式化内容。

当前日期: {current_date}"""

SCORING_SYSTEM_PROMPT = """你是一位数据驱动的技术分析师，专注于 AI 领域的量化评估。
你的评分标准严格、客观、一致，不受项目知名度影响。
你只输出结构化 JSON，不输出任何多余文字。"""

SCORING_PROMPT_TEMPLATE = """基于以下采集到的 GitHub 项目数据和行业新闻，对每个项目/新闻进行结构化评分。

## GitHub 项目数据
{github_data}

## 行业新闻数据
{news_data}

## 评分要求

对每个 GitHub 项目，输出 JSON:
{{
  "repo": "owner/repo_name",
  "is_ai": true/false,
  "category": "Agent / RAG / Infra / Tool / Model",
  "scores": {{
    "热度": 0-10,
    "技术前沿性": 0-10,
    "成长潜力": 0-10,
    "综合": 0-10
  }},
  "one_line_reason": "一句话说明"
}}

评分标准:
- 热度: Star 数 >50k=9-10, >20k=7-8, >10k=5-6, >5k=3-4, <5k=1-2
- 技术前沿性: 是否引入新架构/新范式。已有技术封装或教程不超过 4 分
- 成长潜力: 架构设计、社区活跃度、团队背景
- 综合: 热度 30% + 前沿性 40% + 潜力 30%

对每条行业新闻，输出 JSON:
{{
  "title": "新闻标题",
  "category": "大厂动态 / 技术突破 / 工具框架 / 投融资 / 行业趋势",
  "impact_score": 0-10,
  "impact_reason": "一句话说明行业影响"
}}

最终输出严格 JSON 格式:
{{
  "scored_repos": [ ... ],
  "scored_news": [ ... ],
  "daily_summary": {{
    "top_trend": "今天最值得关注的一个趋势",
    "hot_directions": ["方向1", "方向2", "方向3"],
    "overall_sentiment": "积极/中性/消极"
  }}
}}

不要输出任何 JSON 以外的内容。

当前日期: {current_date}"""

REPORT_SYSTEM_PROMPT = """你是一位 AI 行业技术分析师，为技术从业者撰写每日简报。

你的写作原则:
- 每句话必须有信息量：要么有数据，要么有判断，要么有对比。没有信息量的句子直接删掉。
- 不用 emoji，不用感叹号，不用「值得关注」「不容忽视」「革命性」「里程碑」等空洞词汇。
- 对普通更新一笔带过，对真正重要的事说清楚「为什么重要」。
- 只基于提供的真实数据撰写，绝不凭空捏造。
- 高分项目详写，低分项目略写或不写。
- 报告整体风格：克制、专业、有判断力，像一份给技术 leader 看的内参。"""

REPORT_PROMPT_TEMPLATE = """基于以下数据，撰写一份每日 AI 趋势简报。

## GitHub 热门项目数据
{github_data}

## 行业新闻数据
{news_data}

## 结构化评分结果
{scoring_result}

---

## 输出格式（严格遵守）

```
# AI 日报 · {current_date}

> [今日导读：1-2句话，直接说今天最值得关注的结论，有数据支撑]

---

## 🔬 GitHub 热门项目

### [项目名] · ⭐[Star数] · [语言]
**[一句话定位，不超过20字]**
[推荐理由，1-2句，说清楚技术亮点或应用价值，引用评分数据]
→ [GitHub链接]

（重复以上格式，综合评分≥7的项目详写，4-6分简写，<4分不收录）

---

## 📰 行业动态

| 类别 | 事件 | 影响 |
|------|------|------|
| [类别] | **[标题]** · [来源](链接) | [一句话影响，≤20字] |
| [类别] | **[标题]** · [来源](链接) | [一句话影响，≤20字] |

⚠️ 表格格式要求：每行之间绝对不能有空行，否则表格无法渲染。表头、分隔线、数据行必须紧密相连，中间不插入任何空行。

（按 impact_score 从高到低，最多8条）

---

## 📊 趋势观察

**[趋势1标题]**
[1-2句分析，有数据或对比]

**[趋势2标题]**
[1-2句分析]

**[趋势3标题]**
[1-2句分析]
```

## 写作约束
- 禁止编造任何数据或链接
- 禁止使用「革命性」「里程碑」「颠覆」「极具战略意义」等词
- 禁止使用感叹号
- 行业动态表格中，影响列必须是判断句，不是描述句
- 趋势观察必须基于 daily_summary 中的数据，不能凭空发挥
- 整体字数控制在 800 字以内"""


# ==================== 节点实现 ====================

def collect_github_node(state: dict[str, Any]) -> dict[str, Any]:
    """节点 1: GitHub 热门项目数据采集.

    使用 GitHubTrendingTool 抓取原始数据，再用 LLM(light) 筛选出 Top 5。
    """
    current_date = state.get("current_date", "")
    log.info(f"[collect_github] 开始采集 GitHub 热门 AI 项目 ({current_date})")

    try:
        from ai_trending.tools.github_trending_tool import GitHubTrendingTool

        tool = GitHubTrendingTool()

        # 分别搜索多个关键词，覆盖当前 AI 行业核心趋势方向
        raw_results: list[str] = []
        for keyword in ["AI Agent", "LLM inference", "MCP"]:
            try:
                result = tool._run(query=keyword)
                if result and not result.startswith("❌"):
                    raw_results.append(f"--- 关键词: {keyword} ---\n{result}")
            except Exception as e:
                log.warning(f"[collect_github] 搜索 '{keyword}' 失败: {e}")

        if not raw_results:
            log.error("[collect_github] 所有搜索均失败")
            return {
                "github_data": "GitHub 数据采集失败，无可用数据。",
                "errors": ["GitHub 数据采集: 所有搜索关键词均失败"],
            }

        raw_data = "\n\n".join(raw_results)

        # 使用 light 模型筛选
        github_summary = call_llm(
            prompt=GITHUB_PROMPT_TEMPLATE.format(raw_data=raw_data, current_date=current_date),
            system_prompt=GITHUB_SYSTEM_PROMPT,
            tier="light",
            max_tokens=2048,
        )

        log.info(f"[collect_github] 完成, 输出 {len(github_summary)} 字符")
        return {"github_data": github_summary}

    except Exception as e:
        log.error(f"[collect_github] 异常: {e}")
        return {
            "github_data": f"GitHub 数据采集异常: {e}",
            "errors": [f"collect_github: {e}"],
        }


def collect_news_node(state: dict[str, Any]) -> dict[str, Any]:
    """节点 2: AI 行业新闻数据采集.

    使用 AINewsTool 抓取原始数据，再用 LLM(light) 筛选出 8-10 条。
    """
    current_date = state.get("current_date", "")
    log.info(f"[collect_news] 开始采集 AI 行业新闻 ({current_date})")

    try:
        from ai_trending.tools.ai_news_tool import AINewsTool

        # 搜索多个关键词
        raw_results: list[str] = []
        for keyword in ["AI", "LLM", "AI Agent", "大模型"]:
            try:
                result = AINewsTool()._run(keywords=keyword)
                if result and not result.startswith("❌"):
                    raw_results.append(f"--- 关键词: {keyword} ---\n{result}")
            except Exception as e:
                log.warning(f"[collect_news] 搜索 '{keyword}' 失败: {e}")

        if not raw_results:
            log.error("[collect_news] 所有新闻源均失败")
            return {
                "news_data": "新闻数据采集失败，无可用数据。",
                "errors": ["新闻数据采集: 所有搜索关键词均失败"],
            }

        raw_data = "\n\n".join(raw_results)

        # 使用 light 模型筛选
        news_summary = call_llm(
            prompt=NEWS_PROMPT_TEMPLATE.format(raw_data=raw_data, current_date=current_date),
            system_prompt=NEWS_SYSTEM_PROMPT,
            tier="light",
            max_tokens=2048,
        )

        log.info(f"[collect_news] 完成, 输出 {len(news_summary)} 字符")
        return {"news_data": news_summary}

    except Exception as e:
        log.error(f"[collect_news] 异常: {e}")
        return {
            "news_data": f"新闻数据采集异常: {e}",
            "errors": [f"collect_news: {e}"],
        }


def score_trends_node(state: dict[str, Any]) -> dict[str, Any]:
    """节点 3: 结构化评分（核心差异点）.

    使用 LLM(default) 对采集数据进行量化评分，输出 JSON Schema。
    这是整个系统的核心——让 LLM 参与决策，而不仅仅是信息提取。
    """
    current_date = state.get("current_date", "")
    github_data = state.get("github_data", "无数据")
    news_data = state.get("news_data", "无数据")

    log.info("[score_trends] 开始结构化评分")

    try:
        scoring_result, usage = call_llm_with_usage(
            prompt=SCORING_PROMPT_TEMPLATE.format(
                github_data=github_data,
                news_data=news_data,
                current_date=current_date,
            ),
            system_prompt=SCORING_SYSTEM_PROMPT,
            tier="default",
            max_tokens=4096,
            json_mode=True,
        )

        log.info(f"[score_trends] 完成, 输出 {len(scoring_result)} 字符, tokens={usage.get('total_tokens', 0)}")
        return {
            "scoring_result": scoring_result,
            "token_usage": usage,
        }

    except Exception as e:
        log.error(f"[score_trends] 评分失败: {e}")
        # 评分失败时，使用空 JSON 确保下游节点仍可运行
        fallback = '{"scored_repos": [], "scored_news": [], "daily_summary": {"top_trend": "评分数据不可用", "hot_directions": [], "overall_sentiment": "中性"}}'
        return {
            "scoring_result": fallback,
            "errors": [f"score_trends: {e}"],
        }


def write_report_node(state: dict[str, Any]) -> dict[str, Any]:
    """节点 4: 撰写 Markdown 日报.

    使用 LLM(default) 基于原始数据 + 评分结果生成最终报告。
    评分结果决定报告中项目的排序和详略。
    """
    current_date = state.get("current_date", "")
    github_data = state.get("github_data", "无数据")
    news_data = state.get("news_data", "无数据")
    scoring_result = state.get("scoring_result", "{}")

    log.info("[write_report] 开始撰写日报")

    try:
        report, usage = call_llm_with_usage(
            prompt=REPORT_PROMPT_TEMPLATE.format(
                github_data=github_data,
                news_data=news_data,
                scoring_result=scoring_result,
                current_date=current_date,
            ),
            system_prompt=REPORT_SYSTEM_PROMPT,
            tier="default",
            max_tokens=4096,
        )

        # 保存报告到本地文件
        from pathlib import Path
        reports_dir = Path.cwd() / "reports"
        reports_dir.mkdir(parents=True, exist_ok=True)
        report_file = reports_dir / f"{current_date}.md"
        report_file.write_text(report, encoding="utf-8")

        log.info(f"[write_report] 完成, 报告已保存到 {report_file} ({len(report)} 字符)")

        # 累加 token 用量
        prev_usage = state.get("token_usage", {})
        merged_usage = {
            "prompt_tokens": prev_usage.get("prompt_tokens", 0) + usage.get("prompt_tokens", 0),
            "completion_tokens": prev_usage.get("completion_tokens", 0) + usage.get("completion_tokens", 0),
            "total_tokens": prev_usage.get("total_tokens", 0) + usage.get("total_tokens", 0),
        }

        return {
            "report_content": report,
            "token_usage": merged_usage,
        }

    except Exception as e:
        log.error(f"[write_report] 报告撰写失败: {e}")
        return {
            "report_content": f"# AI 日报 | {current_date}\n\n报告生成失败: {e}",
            "errors": [f"write_report: {e}"],
        }


def publish_node(state: dict[str, Any]) -> dict[str, Any]:
    """节点 5: 多渠道发布.

    各发布步骤相互独立，任意一步失败不影响其他步骤继续执行。
    """
    report_content = state.get("report_content", "")
    current_date = state.get("current_date", "")
    author_name = state.get("author_name", "AI Trending Bot")
    article_title = f"AI 日报 | {current_date} 最热 AI 开源项目与行业新闻"

    publish_results: list[str] = []

    if not report_content or report_content.startswith("# AI 日报") and "报告生成失败" in report_content:
        log.warning("[publish] 报告内容为空或生成失败，跳过发布")
        return {"publish_results": ["跳过发布: 报告内容无效"]}

    # --- Step 1: GitHub 发布 ---
    try:
        from ai_trending.tools.github_publish_tool import GitHubPublishTool
        result = GitHubPublishTool()._run(
            content=report_content,
            filename=f"{current_date}.md",
            commit_message=f"AI Trending Report - {current_date}",
        )
        first_line = result.splitlines()[0] if result else ""
        log.info(f"[publish] GitHub: {first_line}")
        publish_results.append(f"GitHub: {first_line}")
    except Exception as e:
        log.error(f"[publish] GitHub 发布失败: {e}")
        publish_results.append(f"GitHub: 失败 - {e}")

    # --- Step 2: 微信公众号 HTML ---
    wechat_html = ""
    try:
        from ai_trending.tools.wechat_article_tool import WeChatArticleTool
        wechat_tool = WeChatArticleTool()
        wechat_result = wechat_tool._run(
            content=report_content,
            title=article_title,
            author=author_name,
        )
        wechat_html = wechat_tool._markdown_to_wechat_html(report_content)
        first_line = wechat_result.splitlines()[0] if wechat_result else ""
        log.info(f"[publish] 微信HTML: {first_line}")
        publish_results.append(f"微信HTML: {first_line}")
    except Exception as e:
        log.error(f"[publish] 微信 HTML 生成失败: {e}")
        publish_results.append(f"微信HTML: 失败 - {e}")

    # --- Step 3: 微信草稿箱 ---
    app_id = os.getenv("WECHAT_APP_ID", "")
    app_secret = os.getenv("WECHAT_APP_SECRET", "")
    if not app_id or not app_secret:
        log.info("[publish] 微信草稿箱: 未配置，跳过")
        publish_results.append("微信草稿箱: 未配置，已跳过")
    else:
        try:
            from ai_trending.tools.wechat_draft_tool import WeChatDraftTool
            draft_result = WeChatDraftTool()._run(
                content=wechat_html or report_content,
                title=article_title,
                author=author_name,
            )
            if draft_result.startswith("❌") or draft_result.startswith("⚠️"):
                log.warning(f"[publish] 微信草稿箱: {draft_result.splitlines()[0]}")
                publish_results.append(f"微信草稿箱: {draft_result.splitlines()[0]}")
            else:
                first_line = draft_result.splitlines()[0] if draft_result else ""
                log.info(f"[publish] 微信草稿箱: {first_line}")
                publish_results.append(f"微信草稿箱: {first_line}")
        except Exception as e:
            log.error(f"[publish] 微信草稿箱异常: {e}")
            publish_results.append(f"微信草稿箱: 异常 - {e}")

    return {"publish_results": publish_results}
