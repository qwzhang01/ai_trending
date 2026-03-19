# AI Trending

![Python](https://img.shields.io/badge/Python-3.10%2B-blue?logo=python)
![LangGraph](https://img.shields.io/badge/LangGraph-1.1%2B-green?logo=langchain)
![License](https://img.shields.io/badge/License-MIT-yellow)
![Version](https://img.shields.io/badge/Version-0.1.0-orange)

每日 AI 开源项目与新闻聚合报告系统，基于 **LangGraph** 状态机编排多步骤 AI 流水线，自动抓取 GitHub 热门项目和行业新闻，经 LLM 评分筛选后生成 Markdown 日报，并推送至 GitHub 仓库和微信公众号。

---

## 功能特性

- **并行数据采集** — GitHub 热门项目 + AI 行业新闻同步抓取，互不阻塞
- **LLM 结构化评分** — 从热度、技术前沿性、成长潜力三个维度量化评分，驱动报告详略
- **分级模型策略** — 采集/整理用轻量模型，写作/评分用高质量模型，降低成本
- **多渠道发布** — 自动推送到 GitHub 仓库 + 生成微信公众号 HTML + 推送草稿箱
- **可观测性** — 运行指标持久化（JSON）、Token 用量统计、Webhook 失败通知
- **去重缓存** — 本地缓存已处理的 URL / 仓库，避免重复收录

---

## 架构

基于 [LangGraph](https://github.com/langchain-ai/langgraph) `StateGraph` 实现显式状态流转：

```
START
  ├─► collect_github  ─┐
  └─► collect_news    ─┴─► score_trends ─► write_report ─► publish ─► END
       (并行)
```

| 节点 | 职责 | 使用模型 |
|------|------|---------|
| `collect_github` | 调用 GitHub API 抓取热门 AI 项目，LLM 筛选 Top 5 | `MODEL_LIGHT` |
| `collect_news` | 多源抓取 AI 行业新闻（HN / Reddit / newsdata.io 等），LLM 筛选 8-10 条 | `MODEL_LIGHT` |
| `score_trends` | LLM 对项目和新闻进行结构化 JSON 评分 | `MODEL` |
| `write_report` | 基于原始数据 + 评分结果生成 Markdown 日报，保存到 `reports/` | `MODEL` |
| `publish` | 推送 GitHub 仓库 + 生成微信 HTML + 推送微信草稿箱 | — |

---

## 快速开始

### 前置要求

- Python 3.10 ~ 3.13
- [uv](https://docs.astral.sh/uv/) 包管理器

### 安装

```bash
git clone https://github.com/your-username/ai-trending.git
cd ai-trending

# 安装依赖
uv sync

# 复制并填写环境变量
cp .env.example .env
```

### 运行

```bash
# 直接运行（推荐）
python run.py

# 指定日期
python run.py --date 2026-03-19

# 只校验配置，不执行
python run.py --dry-run

# 详细日志
python run.py --verbose

# 通过 uv 脚本入口
uv run ai_trending
```

---

## 环境变量

复制 `.env.example` 为 `.env` 并按需填写：

### LLM 配置（必填）

| 变量 | 说明 | 示例 |
|------|------|------|
| `MODEL` | 主模型（写作/评分） | `openai/gpt-4o` |
| `OPENAI_API_KEY` | OpenAI / 兼容 API Key | `sk-xxx` |
| `OPENAI_API_BASE` | 自定义 API Base（Ollama / 代理等） | `http://localhost:11434` |
| `MODEL_LIGHT` | 轻量模型（采集/整理），留空回退到 `MODEL` | `openai/gpt-4o-mini` |
| `LLM_TEMPERATURE` | 温度，生产环境推荐 `0.1` | `0.1` |

支持所有 [LiteLLM](https://docs.litellm.ai/docs/providers) 兼容的模型，包括 OpenAI、Anthropic、Ollama、DeepSeek 等。

### GitHub 配置（推荐）

| 变量 | 说明 |
|------|------|
| `GITHUB_TOKEN` | Personal Access Token，用于 API 搜索和报告推送 |
| `GITHUB_REPORT_REPO` | 报告推送目标仓库，格式 `owner/repo` |

未配置 `GITHUB_TOKEN` 时 API 速率限制为 60 次/小时；未配置 `GITHUB_REPORT_REPO` 时报告只保存到本地 `reports/` 目录。

### 新闻 API（可选）

| 变量 | 说明 |
|------|------|
| `NEWSDATA_API_KEY` | [newsdata.io](https://newsdata.io/register) API Key，提供更多新闻源 |

未配置时仅使用 Hacker News + Reddit 作为新闻源。

### 微信公众号（可选）

| 变量 | 说明 |
|------|------|
| `WECHAT_APP_ID` | 公众号 AppID |
| `WECHAT_APP_SECRET` | 公众号 AppSecret |
| `WECHAT_THUMB_MEDIA_ID` | 封面图素材 ID，留空则运行时自动上传 |

### 通知 Webhook（可选）

| 变量 | 说明 |
|------|------|
| `WEBHOOK_URL` | 失败时发送通知，支持企业微信 / 飞书 / 钉钉 / Slack |
| `WEBHOOK_ON_SUCCESS` | 设为 `true` 时成功也发通知 |

---

## Docker 部署

### 手动运行一次

```bash
# 构建镜像
docker compose build

# 运行一次
docker compose run --rm ai-trending

# 指定日期运行
docker compose run --rm ai-trending --date 2026-03-19

# 只校验配置
docker compose run --rm ai-trending --dry-run
```

### 定时调度（每天 08:00 CST）

```bash
# 后台启动定时任务
docker compose up -d ai-trending-cron

# 查看日志
docker compose logs -f ai-trending-cron

# 停止
docker compose down
```

报告和输出文件通过 volume 挂载到宿主机：

| 容器路径 | 宿主机路径 | 说明 |
|---------|-----------|------|
| `/app/reports` | `./reports` | Markdown 日报 |
| `/app/output` | `./output` | 微信 HTML + 去重缓存 |
| `/app/logs` | `./logs` | 运行日志 + cron 日志 |

---

## 项目结构

```
ai_trending/
├── src/ai_trending/
│   ├── graph.py          # LangGraph 流程图定义（StateGraph）
│   ├── nodes.py          # 各节点实现（采集 / 评分 / 写作 / 发布）
│   ├── main.py           # 模块入口（uv run ai_trending）
│   ├── config.py         # 环境变量加载与校验
│   ├── llm_client.py     # LiteLLM 封装（分级模型 / JSON 模式）
│   ├── metrics.py        # 运行指标采集与持久化
│   ├── retry.py          # 重试装饰器
│   ├── logger.py         # 日志配置
│   └── tools/
│       ├── github_trending_tool.py   # GitHub API 搜索工具
│       ├── ai_news_tool.py           # 多源新闻抓取工具
│       ├── github_publish_tool.py    # GitHub 报告推送工具
│       ├── wechat_article_tool.py    # 微信 HTML 生成工具
│       ├── wechat_draft_tool.py      # 微信草稿箱推送工具
│       └── dedup_cache.py            # 本地去重缓存
├── run.py                # 生产启动入口（支持 CLI 参数）
├── reports/              # 生成的 Markdown 日报
├── output/               # 微信 HTML + 去重缓存
├── metrics/              # 运行指标 JSON
├── Dockerfile
├── docker-compose.yml
├── pyproject.toml
└── .env.example
```

---

## 输出示例

日报保存在 `reports/YYYY-MM-DD.md`，格式如下：

```markdown
# AI 日报 | 2026-03-19

今天最值得关注的是 xxx 发布了 ...

## GitHub 热门项目 Top 5

### owner/repo-name
> ⭐ 12.3k · Python · 一句话定位

推荐理由 ...

[owner/repo-name](https://github.com/owner/repo-name)

## 行业动态

- **新闻标题** — 一句话判断。[来源](链接)

## 趋势观察

1. ...
```

---

## License

[MIT](LICENSE)
