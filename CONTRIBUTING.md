# 贡献指南

感谢您对 AI Trending 项目的关注！我们欢迎各种形式的贡献。

## 如何贡献

### 报告问题
- 在 [Issues](https://github.com/your-username/ai-trending/issues) 页面创建新的 issue
- 提供清晰的问题描述、复现步骤和期望结果
- 如果是功能请求，请说明使用场景和预期收益

### 提交代码
1. Fork 本仓库
2. 创建功能分支 (`git checkout -b feature/amazing-feature`)
3. 提交更改 (`git commit -m 'feat: add amazing feature'`)
4. 推送到分支 (`git push origin feature/amazing-feature`)
5. 创建 Pull Request

---

## 开发环境设置

### 前置要求

- Python 3.10 ~ 3.13
- [uv](https://docs.astral.sh/uv/) 包管理器

### 安装

```bash
# 克隆仓库
git clone https://github.com/your-username/ai-trending.git
cd ai-trending

# 安装依赖（uv 会自动创建 .venv）
uv sync

# 复制并填写环境变量
cp .env.example .env
```

### 运行

```bash
# 使用项目虚拟环境运行（推荐）
.venv/bin/python run.py

# 或激活虚拟环境后运行
source .venv/bin/activate
python run.py

# 指定日期
.venv/bin/python run.py --date 2026-03-19

# 只校验配置，不执行
.venv/bin/python run.py --dry-run
```

---

## 运行测试

```bash
# 运行所有单元测试
.venv/bin/python -m pytest tests/ -v

# 运行指定测试文件
.venv/bin/python -m pytest tests/test_github_trending_tool.py -v

# 运行并显示覆盖率
.venv/bin/python -m pytest tests/ --cov=src/ai_trending --cov-report=term-missing

# 运行集成测试（需真实密钥）
RUN_INTEGRATION_TESTS=1 .venv/bin/python -m pytest tests/integration/ -v
```

> **注意**：单元测试全部使用 mock，不发起真实 LLM / HTTP 调用，无需配置 `.env` 即可运行。

---

## 项目分层结构

```
src/ai_trending/
├── graph.py          # LangGraph 图定义（只定义拓扑结构）
├── nodes.py          # LangGraph 节点实现（采集 / 评分 / 写作 / 发布）
├── llm_client.py     # 统一 LLM 客户端（三档模型：light / default / tool_only）
├── config.py         # 环境变量加载与校验
├── logger.py         # 日志配置
├── metrics.py        # 运行指标采集与持久化
├── retry.py          # HTTP 重试工具
├── main.py           # 模块入口
├── crew/
│   ├── github_trending/   # GitHub 趋势分析（关键词规划 → 趋势排名）
│   │   ├── crew.py        # 编排器（GitHubTrendingOrchestrator）
│   │   ├── models.py      # Pydantic 数据模型
│   │   ├── utils.py       # 过滤规则和工具函数
│   │   ├── keyword_planning/  # 子 Crew：关键词规划
│   │   └── trend_ranking/     # 子 Crew：趋势排名
│   ├── new_collect/       # AI 新闻多源采集与 LLM 筛选
│   │   ├── crew.py        # NewsCollectCrew
│   │   └── fetchers.py    # 多源新闻抓取器（HN / Reddit / newsdata.io / 知乎）
│   └── util/              # 共享工具
│       └── dedup_cache.py # 本地去重缓存
└── tools/                 # 工具层（供节点和 Crew 调用）
    ├── github_trending_tool.py   # GitHub API 搜索工具
    ├── ai_news_tool.py           # 多源新闻抓取工具
    ├── github_publish_tool.py    # GitHub 报告推送工具
    └── wechat_publish_tool.py    # 微信公众号 HTML 生成 + 草稿箱推送
```

### 分层职责

| 层级 | 文件 | 职责 |
|------|------|------|
| **编排层** | `graph.py` + `nodes.py` | LangGraph 状态流转，调用 Crew / Tool |
| **Agent 层** | `crew/` | CrewAI 多步推理（筛选、分析、排名） |
| **工具层** | `tools/` | 外部 API 调用（GitHub、微信、新闻源） |
| **基础设施** | `llm_client.py` 等 | LLM 调用、日志、配置、重试 |

---

## 代码规范

### Python 代码风格
- 遵循 PEP 8 规范
- 使用 Black 进行代码格式化（行宽 88）
- 使用 isort 进行导入排序
- 推荐使用类型注解

### 提交信息规范

格式：`类型: 简短描述`

| 类型 | 说明 |
|------|------|
| `feat` | 新功能 |
| `fix` | 问题修复 |
| `refact` | 重构（不影响功能） |
| `docs` | 文档更新 |
| `test` | 测试相关 |
| `chore` | 构建/依赖/配置 |

### 新增功能检查清单

新增 LangGraph 节点、CrewAI Crew 或发布渠道时，请确认：

- [ ] 节点层不直接调用 `call_llm`（语义判断下沉到 Crew）
- [ ] LLM 调用统一走 `llm_client.py`，节点用 `call_llm` / `call_llm_with_usage`，CrewAI Agent 用 `build_crewai_llm(tier)`
- [ ] 模型档位选择正确：`light`（采集整理）/ `default`（分析写作）/ `tool_only`（纯工具调用 Agent）
- [ ] API Key 从 `config.py` / 环境变量读取，不硬编码
- [ ] 有完整的异常处理和兜底策略
- [ ] 新增了对应的单元测试（使用 mock，不发起真实调用）
- [ ] 在 `.env.example` 中补充新增的环境变量说明

---

## 项目结构说明

- `src/ai_trending/` — 核心代码
- `tests/` — 测试代码（单元测试 + 集成测试）
- `reports/` — 生成的 Markdown 日报
- `output/` — 微信 HTML + 去重缓存
- `metrics/` — 运行指标 JSON

## 沟通渠道

- GitHub Issues：问题讨论和功能请求
- Pull Requests：代码审查和合并

## 行为准则

请遵守我们的 [行为准则](CODE_OF_CONDUCT.md)，确保社区环境友好和尊重。