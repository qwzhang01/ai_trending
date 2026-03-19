"""GitHub Trending Tool — 通过 GitHub API 抓取近期 AI 领域技术创新型开源项目."""

import os
import re
import time
from datetime import datetime, timedelta
from typing import Any, Type

from crewai.tools import BaseTool
from pydantic import BaseModel, Field

from ai_trending.logger import get_logger
from ai_trending.retry import safe_request
from ai_trending.tools.dedup_cache import DedupCache

log = get_logger("github_tool")

# ── 过滤规则 ────────────────────────────────────────────────
# 仓库名/描述中包含这些关键词的，直接排除（不区分大小写）
EXCLUDE_NAME_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\bawesome[-_]", re.IGNORECASE),          # awesome-xxx 清单
    re.compile(r"[-_]awesome\b", re.IGNORECASE),          # xxx-awesome 清单
    re.compile(r"\bcurated[-_ ]list\b", re.IGNORECASE),   # curated list
    re.compile(r"\bresource[s]?\b", re.IGNORECASE),       # 资源合集
    re.compile(r"\btutorial[s]?\b", re.IGNORECASE),       # 教程
    re.compile(r"\bcourse[s]?\b", re.IGNORECASE),         # 课程
    re.compile(r"\bcheatsheet\b", re.IGNORECASE),         # 速查表
    re.compile(r"\binterview\b", re.IGNORECASE),          # 面试题
    re.compile(r"\blearning[-_ ]path\b", re.IGNORECASE),  # 学习路线
    re.compile(r"\broadmap\b", re.IGNORECASE),            # 路线图
    re.compile(r"\b(prompts|gallery|collection)\b", re.IGNORECASE),  # 提示词/画廊/合集
    re.compile(r"-(starter|template|boilerplate|demo|example)$", re.IGNORECASE),  # 模板/示例
]

EXCLUDE_DESCRIPTION_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\bcurated\b.*\blist\b", re.IGNORECASE),
    re.compile(r"\bcollection of\b.*\b(links|resources|tools|repos)\b", re.IGNORECASE),
    re.compile(r"\bawesome list\b", re.IGNORECASE),
    re.compile(r"\blearning resources\b", re.IGNORECASE),
    re.compile(r"\bstudy guide\b", re.IGNORECASE),
    re.compile(r"\b(list of|collection of)\b.*\b(papers|models|tools|resources|repos|links)\b", re.IGNORECASE),
    re.compile(r"\b(prompt[s]?|template[s]?)\b.*\b(collection|library|hub)\b", re.IGNORECASE),
]

# 排除这些具体的仓库（高 Star 但无技术创新价值的知名清单）
EXCLUDE_REPOS: set[str] = {
    "vinta/awesome-python",
    "awesome-selfhosted/awesome-selfhosted",
    "sindresorhus/awesome",
    "josephmisiti/awesome-machine-learning",
    "avelino/awesome-go",
    "fffaraz/awesome-cpp",
    "enaqx/awesome-react",
    "rust-unofficial/awesome-rust",
    "ziadoz/awesome-php",
    "akullpp/awesome-java",
    "humiaozuzu/awesome-flask",
    "prakhar1989/awesome-courses",
    "donnemartin/system-design-primer",
    "public-apis/public-apis",
    "EbookFoundation/free-programming-books",
    "codecrafters-io/build-your-own-x",
    "kamranahmedse/developer-roadmap",
    "jwasham/coding-interview-university",
    "getify/You-Dont-Know-JS",
    "trimstray/the-book-of-secret-knowledge",
    "Significant-Gravitas/AutoGPT",
    "f/awesome-chatgpt-prompts",
    "DopplerHQ/awesome-interview-questions",
    "mckaywrigley/chatbot-ui",
    "lobehub/lobe-chat",
    "open-webui/open-webui",
    "mckaywrigley/takeoff-web",
    "LAION-AI/Open-Assistant",
    "PromtEngineer/localGPT",
    "microsoft/markitdown",
    "obra/superpowers",
    # ── 常年霸榜的巨型老项目，Star 极高但无新鲜感 ──
    "huggingface/transformers",
    "langchain-ai/langchain",
    "langgenius/dify",
    "ggml-org/llama.cpp",
    "infiniflow/ragflow",
    "run-llama/llama_index",
    "microsoft/autogen",
    "microsoft/graphrag",
    "langchain-ai/langgraph",
    "vllm-project/vllm",
    "sgl-project/sglang",
    "mem0ai/mem0",
    "chroma-core/chroma",
    "milvus-io/milvus",
    "langfuse/langfuse",
    "letta-ai/letta",
    "FlowiseAI/Flowise",
    "labring/FastGPT",
    "khoj-ai/khoj",
    "BerriAI/litellm",
    "deepset-ai/haystack",
    "bentoml/OpenLLM",
    "ray-project/ray",
    "openvinotoolkit/openvino",
    "mindsdb/mindsdb",
    "crewAIInc/crewAI",
    "Mintplex-Labs/anything-llm",
    "screenpipe/screenpipe",
    "open-webui/open-webui",
    "HKUDS/LightRAG",
    "getzep/graphiti",
    "NirDiamant/RAG_Techniques",
    "NirDiamant/GenAI_Agents",
    "dair-ai/Prompt-Engineering-Guide",
    "PaddlePaddle/PaddleOCR",
}


def _is_excluded(repo: dict[str, Any]) -> bool:
    """判断仓库是否应该被过滤掉."""
    full_name = repo.get("full_name", "")
    name = repo.get("name", "")
    desc = repo.get("description", "") or ""

    # 黑名单
    if full_name.lower() in {r.lower() for r in EXCLUDE_REPOS}:
        return True

    # 名称模式匹配
    for pattern in EXCLUDE_NAME_PATTERNS:
        if pattern.search(name):
            return True

    # 描述模式匹配
    for pattern in EXCLUDE_DESCRIPTION_PATTERNS:
        if pattern.search(desc):
            return True

    # fork 仓库排除
    if repo.get("fork", False):
        return True

    return False


# AI 技术趋势关键词映射表
# 根据用户输入的顶层关键词，展开为更精准的搜索词组合
_TREND_KEYWORD_MAP: dict[str, list[str]] = {
    "ai": ["LLM", "AI agent", "RAG", "MCP", "multimodal"],
    "llm": ["LLM", "large language model", "fine-tuning", "inference"],
    "agent": ["AI agent", "autonomous agent", "agentic", "multi-agent"],
    "machine learning": ["deep learning", "neural network", "diffusion model"],
}

class GitHubTrendingInput(BaseModel):
    """Input schema for GitHubTrendingTool."""

    query: str = Field(
        default="AI",
        description="搜索关键词，例如 'AI', 'LLM', 'AI Agent', 'machine learning'",
    )
    top_n: int = Field(
        default=5,
        description="返回前 N 个最热门的仓库，默认 5",
    )


class GitHubTrendingTool(BaseTool):
    """通过 GitHub REST API 搜索近期 AI 领域技术创新型开源项目.

    过滤逻辑:
      - 排除 awesome-xxx / curated list / 教程 / 面试题 / 路线图等非技术项目
      - 排除已知的高 Star 资源合集仓库（黑名单）
      - 排除 fork 仓库
      - 聚焦近 7 天内创建或活跃更新、Star 增长快的项目
    """

    name: str = "github_trending_tool"
    description: str = (
        "通过 GitHub API 搜索近期最热门的 AI 技术创新型开源项目。"
        "自动过滤 awesome 清单、教程合集、面试题等非技术项目。"
        "聚焦真正有技术创新或业务应用价值的仓库。"
    )
    args_schema: Type[BaseModel] = GitHubTrendingInput

    def _run(self, query: str = "AI", top_n: int = 5) -> str:
        """执行 GitHub 搜索，过滤后返回格式化结果."""
        token = os.environ.get("GITHUB_TOKEN", "")
        headers = {"Accept": "application/vnd.github+json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        else:
            log.warning("GITHUB_TOKEN 未设置，API 速率限制为 10 次/分钟")

        # 近 30 天作为「近期活跃」判断基准
        since_date = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
        # 2025 年以来作为「新兴项目」判断基准
        since_2025 = "2025-01-01"
        all_repos: dict[str, dict[str, Any]] = {}

        # ── 分层针对性搜索策略 ──────────────────────────────────
        # 注意：GitHub Search API 不支持括号 + 复杂 OR 组合（会返回 422）
        # 策略：① topic: 语法（最精准）② 具体项目名 OR 锁点 ③ 简单关键词
        search_queries = [
            # A. 新兴技术方向：2025年后创建的新项目，捕捉最新趋势
            f"topic:mcp-server stars:>100 created:>{since_2025}",
            f"topic:ai-agent stars:>200 created:>{since_2025}",
            f"topic:llm-inference stars:>300 created:>{since_2025}",
            f"topic:multimodal stars:>500 created:>{since_2025}",

            # B. 当前最热技术趋势：MCP、多模态、推理加速、长文本记忆
            f"mcp server in:name,description stars:>300 pushed:>{since_date}",
            f"long context memory in:name,description stars:>500 pushed:>{since_date}",
            f"llm serving inference in:name,description stars:>1000 pushed:>{since_date}",
            f"vision language model in:name,description stars:>1000 pushed:>{since_date}",

            # C. 当前最活跃的核心框架（近期有实质更新）
            f"topic:llm-agent stars:>500 pushed:>{since_date}",
            f"topic:rag stars:>2000 pushed:>{since_date}",
            f"topic:multi-agent stars:>300 pushed:>{since_date}",

            # D. 具体项目名锁点：当前行业代表性技术栈
            f"vllm OR sglang OR ollama stars:>5000 pushed:>{since_date}",
            f"smolagents OR pydantic-ai OR agno stars:>500 pushed:>{since_date}",
        ]

        t0 = time.time()
        for sq in search_queries:
            resp = safe_request(
                "GET",
                "https://api.github.com/search/repositories",
                headers=headers,
                params={
                    "q": sq,
                    "sort": "stars",
                    "order": "desc",
                    "per_page": 30,
                },
                timeout=30,
                max_retries=3,
                operation_name=f"GitHub搜索({query})",
            )
            if resp is None:
                continue
            # 422 表示查询语法不合法，跳过该条查询
            if resp.status_code == 422:
                log.warning(f"GitHub 搜索语法错误(422)，跳过查询: {sq[:80]}")
                continue

            remaining = int(resp.headers.get("X-RateLimit-Remaining", 99))
            log.debug(f"GitHub API 剩余配额: {remaining}")

            # 速率限制耗尽时 GitHub 搜索 API 会返回 total_count=0 而非 403
            # 检测到配额不足时提前终止，避免无效请求
            if remaining <= 1:
                log.warning("GitHub API 速率限制即将耗尽，建议设置 GITHUB_TOKEN")

            data = resp.json()
            for item in data.get("items", []):
                full_name = item["full_name"]
                if full_name not in all_repos and not _is_excluded(item):
                    all_repos[full_name] = item

        elapsed = time.time() - t0
        filtered_count = len(all_repos)
        log.info(f"GitHub 搜索完成: 关键词='{query}', 有效结果={filtered_count}个仓库, 耗时={elapsed:.1f}s")

        if not all_repos:
            log.warning(f"未搜索到与 '{query}' 相关的热门仓库")
            return f"未能从 GitHub 搜索到与 '{query}' 相关的热门仓库。请检查网络连接或 GitHub Token。"

        # ── 跨日去重：过滤昨天及之前已出现过的仓库 ──────────────────
        dedup = DedupCache("github_repos")
        repo_list = list(all_repos.values())
        new_repos = dedup.filter_new(repo_list, key_fn=lambda r: r["full_name"])
        # 将本次新仓库标记为已见
        dedup.mark_seen([r["full_name"] for r in new_repos])
        log.info(f"去重缓存统计: {dedup.stats()}")

        # 如果全部都是重复的，降级返回全量（避免空结果）
        if not new_repos:
            log.info("所有仓库均已在近期出现过，返回全量结果（不去重）")
            new_repos = repo_list

        # 排序：综合「近期活跃度」+「话题新鲜度」+「Star 数」，体现技术趋势感
        # 近 30 天内有更新 +2，命中趋势话题标签 +3，Star 数每千 +1
        TREND_TOPICS = {
            # Agent 方向
            "agentic", "multi-agent", "agent-framework", "autonomous-agent", "tool-use",
            # 推理与服务
            "llm-inference", "llm-serving", "quantization", "speculative-decoding",
            # 记忆与上下文
            "long-term-memory", "rag", "knowledge-graph",
            # 多模态
            "multimodal", "vision-language-model", "vlm",
            # 新兴协议与生态
            "mcp", "mcp-server", "model-context-protocol",
            # 自主改进
            "self-improving", "world-model",
        }

        def _trend_score(repo: dict[str, Any]) -> int:
            stars = repo.get("stargazers_count", 0)
            updated_at = (repo.get("updated_at", "") or "")[:10]
            topics = {t.lower() for t in repo.get("topics", [])}

            is_recent = updated_at >= since_date
            has_trend_topic = bool(topics & TREND_TOPICS)

            return (2 if is_recent else 0) + (3 if has_trend_topic else 0) + stars // 1000

        sorted_repos = sorted(
            new_repos,
            key=_trend_score,
            reverse=True,
        )[:top_n]

        # 格式化输出（精简版，配合成本优化策略）
        results = []
        for i, repo in enumerate(sorted_repos, 1):
            info = {
                "排名": i,
                "仓库": repo.get("full_name", ""),
                "链接": repo.get("html_url", ""),
                "描述": repo.get("description", "无描述") or "无描述",
                "Stars": f"⭐ {repo.get('stargazers_count', 0):,}",
                "语言": repo.get("language", "未知") or "未知",
                "创建时间": repo.get("created_at", "")[:10],
                "最近更新": repo.get("updated_at", "")[:10],
                "主题标签": ", ".join(repo.get("topics", [])[:5]) or "无",
            }
            results.append(info)

        output = f"## GitHub 热门 AI 开源项目 Top {top_n}（关键词: {query}）\n"
        output += f"数据时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n"

        for r in results:
            output += f"### {r['排名']}. {r['仓库']}\n"
            output += f"- **链接**: {r['链接']}\n"
            output += f"- **描述**: {r['描述']}\n"
            output += f"- **Stars**: {r['Stars']} | **语言**: {r['语言']}\n"
            output += f"- **创建**: {r['创建时间']} | **更新**: {r['最近更新']}\n"
            output += f"- **标签**: {r['主题标签']}\n\n"

        return output
