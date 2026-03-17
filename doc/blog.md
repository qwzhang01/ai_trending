# 我用 CrewAI 做了个每日 AI 情报机器人，完全自动化

> 每天早上打开手机，一份整理好的 AI 日报已经推送到微信公众号和 GitHub——这件事我现在完全不用操心了。

---

## 起因：信息焦虑

做 AI 相关工作的人都懂那种感觉：每天 GitHub 上冒出几十个新项目，Hacker News 上几百条讨论，Reddit 上各种热帖，知乎微博上也在刷屏……

我每天花在"刷信息"上的时间超过 1 小时，但真正有价值的内容可能只有 10 分钟。

于是我想：**能不能让 AI 帮我做这件事？**

不只是简单地爬取，而是真正地"理解"这些信息，筛选出有价值的内容，写出有洞察的点评，然后自动发布出去。

这就是 [ai_trending](https://github.com/avinzhang/avin-kit) 的由来。

---

## 效果先看

先上效果图，每天自动生成的报告长这样：

![AI Trending 报告效果预览](img.png)

报告包含：
- **GitHub 热门 AI 开源项目 Top 5**，每个项目都有深度点评，不只是复制粘贴描述
- **AI 行业热点新闻**，分大厂动态、工具框架、行业趋势三个维度
- **趋势洞察**，提炼当天最值得关注的 3 个信号

同时自动生成适配微信排版的 HTML 文章，直接复制粘贴到公众号后台就能发布。

---

## 技术选型：为什么是 CrewAI？

市面上的 AI Agent 框架不少，我最终选择了 [CrewAI](https://www.crewai.com/)，原因很简单：

**它的抽象层次刚刚好。**

- LangChain 太底层，要自己拼很多东西
- AutoGen 更适合对话式多 Agent
- CrewAI 的 **角色（Agent）+ 任务（Task）+ 工具（Tool）** 三层抽象，和我的需求完美契合

我需要的就是：几个有明确分工的 Agent，按顺序完成各自的任务，最后汇总输出。

---

## 系统架构

整个系统的核心是一个 **4 Agent × 5 Task** 的流水线：

```
┌─────────────────────────────────────────────────────┐
│                   AI Trending Crew                   │
├──────────────┬──────────────┬────────────┬───────────┤
│  GitHub      │  AI 新闻     │  报告撰写   │  发布     │
│  趋势研究员   │  分析师      │  专家       │  专员     │
├──────────────┼──────────────┼────────────┼───────────┤
│ GitHub       │ Hacker News  │  (无工具)   │ GitHub    │
│ Trending     │ Reddit       │  整合上游    │ Publish   │
│ Tool         │ newsdata.io  │  输出       │ Tool +    │
│              │              │            │ WeChat    │
│              │              │            │ Tool      │
└──────┬───────┴──────┬───────┴─────┬──────┴─────┬─────┘
       │              │             │            │
       ▼              ▼             ▼            ▼
  [GitHub 项目]  [AI 新闻]  → [Markdown 报告] → [GitHub + 微信]
```

**任务流水线（顺序执行）：**

1. `github_trending_task` — GitHub 趋势研究员抓取热门 AI 项目
2. `ai_news_task` — AI 新闻分析师搜集行业动态
3. `report_writing_task` — 报告撰写专家整合两个任务的输出，生成完整报告
4. `github_publish_task` — 发布专员将报告推送到 GitHub
5. `wechat_article_task` — 发布专员生成微信公众号 HTML 文章

每个 Agent 都有自己的 `role`、`goal`、`backstory`，这些 Prompt 直接决定了输出质量。

---

## 核心实现

### 1. Agent 定义（agents.yaml）

CrewAI 支持用 YAML 定义 Agent，非常清晰：

```yaml
github_researcher:
  role: >
    GitHub AI 趋势研究员
  goal: >
    发现并分析 GitHub 上最热门的 AI 开源项目，提供深度洞察
  backstory: >
    你是一位资深的开源社区观察者，对 AI/ML 领域有深刻理解。
    你擅长从 Star 数、提交活跃度、社区讨论中判断一个项目的真实价值，
    而不只是看表面数据。你的点评总是一针见血，让读者快速抓住重点。
```

`backstory` 是关键——它决定了 Agent 的"人格"，直接影响生成内容的风格和深度。

### 2. 自定义工具（Tools）

CrewAI 的工具是标准的 Python 类，继承 `BaseTool` 即可：

```python
from crewai.tools import BaseTool
from pydantic import BaseModel, Field

class GitHubTrendingInput(BaseModel):
    query: str = Field(description="搜索关键词，如 'AI agent LLM'")
    days: int = Field(default=1, description="搜索最近几天的项目")

class GitHubTrendingTool(BaseTool):
    name: str = "GitHub Trending Tool"
    description: str = "搜索 GitHub 上最近热门的 AI 开源项目"
    args_schema: type[BaseModel] = GitHubTrendingInput

    def _run(self, query: str, days: int = 1) -> str:
        # 调用 GitHub Search API
        # 按 stars 排序，过滤最近 N 天更新的项目
        ...
```

工具的 `description` 要写清楚，Agent 会根据这个描述决定什么时候调用哪个工具。

### 3. 新闻聚合：多源去重

新闻来源有三个：Hacker News API、Reddit API、newsdata.io。

最麻烦的问题是**去重**——同一条新闻可能在三个平台都出现。我用了一个简单但有效的方案：

```python
# 基于 URL 的持久化去重缓存
# output/dedup_cache/news_urls.json

def is_duplicate(url: str) -> bool:
    cache = load_cache()
    url_hash = hashlib.md5(url.encode()).hexdigest()
    if url_hash in cache:
        return True
    cache[url_hash] = datetime.now().isoformat()
    save_cache(cache)
    return False
```

缓存持久化到本地 JSON 文件，每次运行前检查，避免重复推送同一条新闻。

### 4. 微信文章生成

微信公众号的 HTML 有一些特殊要求：
- 所有样式必须内联（不支持外部 CSS）
- 图片需要上传到微信服务器（或用外链）
- 字体、行距有特定的适配规范

我让 `WeChatArticleTool` 直接生成带内联样式的 HTML，Agent 负责填充内容，工具负责套模板：

```python
WECHAT_TEMPLATE = """
<div style="max-width: 680px; margin: 0 auto; padding: 20px; 
     font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', ...">
  <!-- 渐变头部 Banner -->
  <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); 
       border-radius: 12px; padding: 30px; ...">
    <h1 style="color: #fff; ...">{title}</h1>
  </div>
  <!-- 正文内容 -->
  {content}
</div>
"""
```

生成的 HTML 直接复制到微信公众号后台的"源代码"模式，排版效果非常好。

---

## 踩过的坑

### 坑 1：LLM 输出不稳定

有时候 Agent 会"发挥失常"，输出格式乱掉，或者内容太短。

解决方案：在 Task 的 `expected_output` 里写清楚格式要求，并加上 retry 机制：

```yaml
# tasks.yaml
report_writing_task:
  expected_output: >
    一份完整的 Markdown 格式日报，必须包含：
    1. 今日看点（100-200字总结）
    2. GitHub 热门项目 Top 5（每个项目含简介和深度点评）
    3. AI 行业新闻（按大厂动态/工具框架/行业趋势分类）
    4. 趋势洞察（3个要点）
    5. 推荐阅读（3个链接）
```

### 坑 2：GitHub API 速率限制

未认证的 GitHub API 每小时只有 60 次请求，很容易触发限制。

解决方案：配置 `GITHUB_TOKEN`，速率提升到 5000 次/小时，完全够用。

### 坑 3：CrewAI 版本迭代快

CrewAI 更新非常频繁，API 变化较大。建议锁定版本，用 `uv` 管理依赖：

```toml
# pyproject.toml
[tool.uv]
dependencies = [
    "crewai==0.x.x",
]
```

---

## 运行效果

每次执行大约需要 **3-5 分钟**（取决于 LLM 速度），输出：

- `reports/2026-03-17.md` — Markdown 格式日报，自动推送到 GitHub
- `output/wechat_2026-03-17.html` — 微信公众号文章，直接可用

以 2026-03-17 的报告为例，当天的主题是：

> **AI Agent 正在从软件概念走向软硬件全面落地**——英伟达发布专为 Agent 设计的 Vera CPU，阿里推出企业级 Agent 平台，整个行业正在为智能体的爆发构建基础设施。

这种洞察是 Agent 自己总结出来的，不是我写的。

---

## 快速上手

```bash
# 1. 克隆项目
git clone https://github.com/avinzhang/avin-kit
cd ai_trending

# 2. 安装依赖（需要 Python 3.10+ 和 uv）
uv sync

# 3. 配置环境变量
cp .env.example .env
# 编辑 .env，填入 MODEL、GITHUB_TOKEN 等

# 4. 运行
crewai run
```

支持的 LLM 后端：
- **本地免费**：Ollama + llama3.1/qwen2.5（推荐，完全免费）
- **云端**：OpenAI GPT-4o、Claude 3.5、Gemini 等

---

## 后续计划

- [ ] **Web Dashboard**：用 FastAPI 做一个历史报告浏览页面
- [ ] **Telegram Bot**：每天自动推送到 Telegram 频道
- [ ] **自定义订阅**：支持用户配置感兴趣的技术方向
- [ ] **向量搜索**：接入向量数据库，支持历史报告语义检索
- [ ] **GitHub Actions**：用 Actions 定时触发，真正的零运维

---

## 总结

这个项目让我对 **Multi-Agent 系统**有了更深的理解：

1. **分工明确比能力强更重要**：每个 Agent 只做一件事，反而比一个"全能 Agent"效果更好
2. **Prompt 是核心竞争力**：`backstory` 写得好不好，直接决定输出质量的上限
3. **工具设计要简单**：工具的 `description` 要让 LLM 一眼看懂，不要过度封装

如果你也有类似的"重复性信息处理"需求，CrewAI 是一个非常值得尝试的框架。

**项目地址**：[github.com/avinzhang/avin-kit](https://github.com/avinzhang/avin-kit)（欢迎 Star ⭐）

---

*如果这篇文章对你有帮助，欢迎点赞收藏，也欢迎在评论区交流你的 Agent 实践经验。*
