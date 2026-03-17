import os

from crewai import Agent, Crew, Process, Task, LLM
from crewai.project import CrewBase, agent, crew, task, before_kickoff, after_kickoff
from crewai.agents.agent_builder.base_agent import BaseAgent

from ai_trending.logger import get_logger
from ai_trending.metrics import RunMetrics
from ai_trending.tools.github_trending_tool import GitHubTrendingTool
from ai_trending.tools.ai_news_tool import AINewsTool
from ai_trending.tools.github_publish_tool import GitHubPublishTool
from ai_trending.tools.wechat_article_tool import WeChatArticleTool
from ai_trending.tools.wechat_draft_tool import WeChatDraftTool

log = get_logger("crew")


def _build_llm(tier: str = "default") -> LLM | None:
    """根据环境变量和任务等级构建不同档次的 LLM 实例.

    tier 说明:
      - "light":     数据采集/整理类任务 — 用便宜小模型即可
      - "default":   写作/分析类任务 — 用好模型保证质量
      - "tool_only": 纯工具调用任务 — 用最便宜的模型

    环境变量:
      MODEL           — default 档模型 (如 openai/gpt-4o)
      MODEL_LIGHT     — light 档模型 (如 openai/gpt-4o-mini)，未设置则回退到 MODEL
      MODEL_TOOL      — tool_only 档模型，未设置则回退到 MODEL_LIGHT，再回退到 MODEL
      OPENAI_API_BASE — 自定义 API 基地址
      LLM_TEMPERATURE — default 档温度 (默认 0.1)
      LLM_DISABLE_THINKING — 是否关闭 thinking 模式 (true/false)

    若主 MODEL 未配置则返回 None (使用 CrewAI 默认).
    """
    # 确定主模型，未配置则跳过
    default_model = os.getenv("MODEL", "")
    if not default_model:
        return None

    # 根据 tier 选择模型和温度
    light_model = os.getenv("MODEL_LIGHT", "") or default_model
    tool_model = os.getenv("MODEL_TOOL", "") or light_model

    tier_config = {
        "light": {"model": light_model, "temperature": 0.1},
        "default": {"model": default_model, "temperature": float(os.getenv("LLM_TEMPERATURE", "0.1"))},
        "tool_only": {"model": tool_model, "temperature": 0.0},
    }

    config = tier_config.get(tier, tier_config["default"])
    kwargs: dict = {"model": config["model"], "temperature": config["temperature"]}

    api_base = os.getenv("OPENAI_API_BASE", "")
    if api_base:
        kwargs["base_url"] = api_base

    # 对于推理模型（如 Kimi-K2.5），需要关闭 thinking 模式
    # 否则 CrewAI 多轮对话中缺少 reasoning_content 字段会导致 API 报错
    thinking_disabled = os.getenv("LLM_DISABLE_THINKING", "").lower()
    if thinking_disabled == "true":
        kwargs["extra_body"] = {"thinking": {"type": "disabled"}}
        log.info("已关闭 LLM thinking 模式")

    log.info(f"LLM tier={tier} → model={config['model']}, temperature={config['temperature']}")
    return LLM(**kwargs)


@CrewBase
class AiTrending():
    """AI Trending Crew — 每日 AI 开源项目与新闻聚合报告系统."""

    agents: list[BaseAgent]
    tasks: list[Task]

    agents_config = "config/agents.yaml"
    tasks_config = "config/tasks.yaml"

    @before_kickoff
    def prepare_inputs(self, inputs):
        """在 Crew 启动前，确保所有必要的输入参数都已设置."""
        from datetime import datetime

        if not inputs.get("current_date"):
            inputs["current_date"] = datetime.now().strftime("%Y-%m-%d")
        if not inputs.get("author_name"):
            inputs["author_name"] = "AI Trending Bot"

        log.info(f"📅 日期: {inputs['current_date']} | ✍️  作者: {inputs['author_name']}")
        return inputs

    @after_kickoff
    def log_completion(self, result):
        """Crew 执行完成后，直接调用 Tool 做发布和格式转换，并记录指标.

        各发布步骤相互独立，任意一步失败不影响其他步骤继续执行。
        """
        from datetime import datetime

        report_content = result.raw
        current_date = datetime.now().strftime("%Y-%m-%d")
        author_name = os.getenv("AUTHOR_NAME", "AI Trending Bot")
        article_title = f"🔥 AI 日报 | {current_date} 最热 AI 开源项目与行业新闻"

        # 获取外部注入的 metrics（由 run.py 设置），或创建临时的
        metrics: RunMetrics = getattr(self, "_metrics", RunMetrics(run_date=current_date))

        # 用于最终汇总的发布结果
        publish_summary: list[str] = []

        # --- Step 1: GitHub 发布 ---
        rec = metrics.tool_start("GitHubPublishTool")
        try:
            publish_result = GitHubPublishTool()._run(
                content=report_content,
                filename=f"{current_date}.md",
                commit_message=f"📊 AI Trending Report - {current_date}",
            )
            rec.finish(status="success")
            first_line = publish_result.splitlines()[0] if publish_result else ""
            log.info(f"📤 GitHub 发布: {first_line}")
            publish_summary.append(f"  ✅ GitHub: {first_line}")
        except Exception as e:
            rec.finish(status="failed", error=str(e))
            log.error(f"❌ GitHub 发布失败: {e}")
            publish_summary.append(f"  ❌ GitHub: {e}")

        # --- Step 2: 微信公众号 HTML 文章生成（本地保存，不依赖微信配置）---
        rec = metrics.tool_start("WeChatArticleTool")
        wechat_html = ""
        try:
            wechat_tool = WeChatArticleTool()
            wechat_result = wechat_tool._run(
                content=report_content,
                title=article_title,
                author=author_name,
            )
            # 提取 HTML 内容供草稿箱使用（复用已渲染结果，避免重复转换）
            wechat_html = wechat_tool._markdown_to_wechat_html(report_content)
            rec.finish(status="success")
            first_line = wechat_result.splitlines()[0] if wechat_result else ""
            log.info(f"📱 微信文章生成: {first_line}")
            publish_summary.append(f"  ✅ 微信HTML: {first_line}")
        except Exception as e:
            rec.finish(status="failed", error=str(e))
            log.error(f"❌ 微信文章生成失败: {e}")
            publish_summary.append(f"  ❌ 微信HTML: {e}")

        # --- Step 3: 微信公众号草稿箱发布（需要微信配置，配置缺失时跳过）---
        app_id = os.getenv("WECHAT_APP_ID", "")
        app_secret = os.getenv("WECHAT_APP_SECRET", "")
        if not app_id or not app_secret:
            log.info("⏭️  微信草稿箱: 未配置 WECHAT_APP_ID/WECHAT_APP_SECRET，跳过")
            publish_summary.append("  ⏭️  微信草稿箱: 未配置，已跳过")
        else:
            rec = metrics.tool_start("WeChatDraftTool")
            try:
                draft_result = WeChatDraftTool()._run(
                    content=wechat_html or report_content,
                    title=article_title,
                    author=author_name,
                )
                # 根据返回内容判断实际成功/失败（Tool 内部错误以文本形式返回）
                if draft_result.startswith("❌") or draft_result.startswith("⚠️"):
                    rec.finish(status="failed", error=draft_result.splitlines()[0])
                    log.warning(f"⚠️  微信草稿箱: {draft_result.splitlines()[0]}")
                    publish_summary.append(f"  ❌ 微信草稿箱: {draft_result.splitlines()[0]}")
                else:
                    rec.finish(status="success")
                    first_line = draft_result.splitlines()[0] if draft_result else ""
                    log.info(f"📤 微信草稿箱: {first_line}")
                    publish_summary.append(f"  ✅ 微信草稿箱: {first_line}")
            except Exception as e:
                rec.finish(status="failed", error=str(e))
                log.error(f"❌ 微信草稿箱发布异常: {e}")
                publish_summary.append(f"  ❌ 微信草稿箱: {e}")

        # --- 发布结果汇总 ---
        log.info("✅ AI Trending Crew 执行完成，发布结果:")
        for line in publish_summary:
            log.info(line)
        log.info("   📄 reports/ — Markdown 报告")
        log.info("   📱 output/  — 微信公众号 HTML 文章")
        return result

    # ==================== Agents ====================

    @agent
    def github_researcher(self) -> Agent:
        """GitHub AI 开源项目趋势研究员."""
        llm = _build_llm("light")  # 数据采集类任务，用便宜模型即可
        return Agent(
            config=self.agents_config["github_researcher"],  # type: ignore[index]
            tools=[GitHubTrendingTool()],
            verbose=True,
            max_retry_limit=3,
            **({"llm": llm} if llm else {}),
        )

    @agent
    def news_analyst(self) -> Agent:
        """AI 行业新闻分析师."""
        llm = _build_llm("light")  # 数据采集类任务，用便宜模型即可
        return Agent(
            config=self.agents_config["news_analyst"],  # type: ignore[index]
            tools=[AINewsTool()],
            verbose=True,
            inject_date=True,
            max_retry_limit=3,
            **({"llm": llm} if llm else {}),
        )

    @agent
    def report_writer(self) -> Agent:
        """AI 日报撰写专家."""
        llm = _build_llm("default")  # 写作类任务，需要好模型保证质量
        return Agent(
            config=self.agents_config["report_writer"],  # type: ignore[index]
            verbose=True,
            inject_date=True,
            max_retry_limit=3,
            respect_context_window=True,
            **({"llm": llm} if llm else {}),
        )

    # ==================== Tasks ====================

    @task
    def github_trending_task(self) -> Task:
        """任务1: 抓取 GitHub 热门 AI 开源项目."""
        return Task(
            config=self.tasks_config["github_trending_task"],  # type: ignore[index]
        )

    @task
    def ai_news_task(self) -> Task:
        """任务2: 搜集 AI 行业新闻."""
        return Task(
            config=self.tasks_config["ai_news_task"],  # type: ignore[index]
        )

    @task
    def report_writing_task(self) -> Task:
        """任务3: 撰写综合报告（依赖前两个任务的输出）."""
        return Task(
            config=self.tasks_config["report_writing_task"],  # type: ignore[index]
            context=[self.github_trending_task(), self.ai_news_task()],
            output_file="reports/{current_date}.md",
        )

    # ==================== Crew ====================

    @crew
    def crew(self) -> Crew:
        """组装 AI Trending Crew — 全流水线执行."""
        return Crew(
            agents=self.agents,
            tasks=self.tasks,
            process=Process.sequential,
            verbose=True,
        )
