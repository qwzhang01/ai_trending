"""GitHub Trending Crew — 过滤规则与工具函数。"""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel

# ── 过滤规则 ────────────────────────────────────────────────
# 仓库名/描述中包含这些关键词的，直接排除（不区分大小写）
EXCLUDE_NAME_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\bawesome[-_]", re.IGNORECASE),
    re.compile(r"[-_]awesome\b", re.IGNORECASE),
    re.compile(r"\bcurated[-_ ]list\b", re.IGNORECASE),
    re.compile(r"\bresource[s]?\b", re.IGNORECASE),
    re.compile(r"\btutorial[s]?\b", re.IGNORECASE),
    re.compile(r"\bcourse[s]?\b", re.IGNORECASE),
    re.compile(r"\bcheatsheet\b", re.IGNORECASE),
    re.compile(r"\binterview\b", re.IGNORECASE),
    re.compile(r"\blearning[-_ ]path\b", re.IGNORECASE),
    re.compile(r"\broadmap\b", re.IGNORECASE),
    re.compile(r"\b(prompts|gallery|collection)\b", re.IGNORECASE),
    re.compile(
        r"-(starter|template|boilerplate|demo|example)$",
        re.IGNORECASE,
    ),
]

EXCLUDE_DESCRIPTION_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\bcurated\b.*\blist\b", re.IGNORECASE),
    re.compile(
        r"\bcollection of\b.*\b(links|resources|tools|repos)\b",
        re.IGNORECASE,
    ),
    re.compile(r"\bawesome list\b", re.IGNORECASE),
    re.compile(r"\blearning resources\b", re.IGNORECASE),
    re.compile(r"\bstudy guide\b", re.IGNORECASE),
    re.compile(
        r"\b(list of|collection of)\b.*\b"
        r"(papers|models|tools|resources|repos|links)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(prompt[s]?|template[s]?)\b.*\b(collection|library|hub)\b",
        re.IGNORECASE,
    ),
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
    "HKUDS/LightRAG",
    "getzep/graphiti",
    "NirDiamant/RAG_Techniques",
    "NirDiamant/GenAI_Agents",
    "dair-ai/Prompt-Engineering-Guide",
    "PaddlePaddle/PaddleOCR",
}
EXCLUDE_REPOS_LOWER = {repo.lower() for repo in EXCLUDE_REPOS}

# 根据顶层主题扩展为默认技术关键词，作为 CrewAI 的兜底策略
TREND_KEYWORD_MAP: dict[str, list[str]] = {
    "ai": ["AI agent", "MCP", "multimodal", "LLM inference", "RAG"],
    "llm": ["LLM inference", "model serving", "fine-tuning", "reasoning model"],
    "agent": ["AI agent", "agentic workflow", "multi-agent", "tool calling"],
    "machine learning": ["deep learning", "diffusion model", "model serving"],
    "mcp": ["MCP", "mcp server", "model context protocol", "tool calling"],
}

TREND_TOPICS: set[str] = {
    "agentic",
    "ai-agent",
    "multi-agent",
    "autonomous-agent",
    "tool-use",
    "tool-calling",
    "mcp",
    "mcp-server",
    "model-context-protocol",
    "llm-inference",
    "llm-serving",
    "reasoning-model",
    "reasoning",
    "quantization",
    "speculative-decoding",
    "rag",
    "knowledge-graph",
    "long-term-memory",
    "memory",
    "multimodal",
    "vision-language-model",
    "vlm",
    "audio-model",
    "world-model",
}


def is_excluded(repo: dict[str, Any]) -> bool:
    """判断仓库是否应该被过滤掉。"""
    full_name = repo.get("full_name", "")
    name = repo.get("name", "")
    desc = repo.get("description", "") or ""

    if full_name.lower() in EXCLUDE_REPOS_LOWER:
        return True

    for pattern in EXCLUDE_NAME_PATTERNS:
        if pattern.search(name):
            return True

    for pattern in EXCLUDE_DESCRIPTION_PATTERNS:
        if pattern.search(desc):
            return True

    if repo.get("fork", False):
        return True

    return False


def unique_preserve_order(items: list[str]) -> list[str]:
    """按原顺序去重。"""
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        key = item.strip().lower()
        if not item.strip() or key in seen:
            continue
        seen.add(key)
        result.append(item.strip())
    return result


def model_to_dict(model: BaseModel) -> dict[str, Any]:
    """兼容 Pydantic v1/v2 的模型转 dict。"""
    if hasattr(model, "model_dump"):
        return model.model_dump()
    return model.dict()  # type: ignore[return-value]


def is_searchable_keyword(keyword: str) -> bool:
    """判断关键词是否适合直接用于 GitHub 搜索。"""
    return bool(re.search(r"[A-Za-z0-9]", keyword or ""))


# ── 关键词辅助方法 ────────────────────────────────────────────

def default_keywords_for_query(base_query: str) -> list[str]:
    """兜底关键词策略：根据主题返回预定义关键词列表。

    Args:
        base_query: 用户原始主题，例如 "AI"、"MCP"

    Returns:
        去重后的关键词列表，最多 5 个
    """
    normalized = base_query.strip().lower()
    fallback = TREND_KEYWORD_MAP.get(
        normalized,
        [base_query, "AI agent", "MCP", "LLM inference"],
    )
    merged: list[str] = []
    if is_searchable_keyword(base_query):
        merged.append(base_query.strip())
    merged.extend(fallback)
    return unique_preserve_order(merged)[:5]


def sanitize_keywords(keywords: list[str], base_query: str) -> list[str]:
    """清洗 CrewAI 输出的关键词，确保可用于 GitHub 检索。

    Args:
        keywords:   CrewAI 输出的原始关键词列表
        base_query: 用户原始主题（始终作为第一个关键词）

    Returns:
        清洗、去重后的关键词列表，最多 5 个
    """
    cleaned: list[str] = []
    for keyword in keywords:
        for part in re.split(r"[,/\n]", keyword):
            candidate = part.strip().strip('"').strip("'")
            if candidate and is_searchable_keyword(candidate):
                cleaned.append(candidate)

    merged: list[str] = []
    if is_searchable_keyword(base_query):
        merged.append(base_query.strip())
    merged.extend(cleaned)
    merged.extend(default_keywords_for_query(base_query))
    return unique_preserve_order(merged)[:5]
