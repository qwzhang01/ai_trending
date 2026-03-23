# 变更日志

本项目遵循[语义化版本控制](https://semver.org/)。

## [0.2.0] - 2026-03-23

### 重构
- 🔄 使用 **LangGraph StateGraph** 全面重构流程编排层，替代原有 CrewAI Sequential Pipeline
- 🏗️ 引入显式状态机（`TrendingState`），节点间数据流转完全可追溯
- 🔀 GitHub 采集与新闻采集改为**并行执行**，互不阻塞
- 🧩 新增 `llm_client.py` 统一 LLM 调用层，支持三档模型调度（`light` / `default` / `tool_only`）
- 📦 新增 `crew/` 目录，CrewAI 下沉为 Agent 内部推理层（`github_trending/` + `new_collect/`）
- 🔧 `wechat_article_tool.py` + `wechat_draft_tool.py` 合并为 `wechat_publish_tool.py`，统一微信发布逻辑
- 📁 `dedup_cache.py` 从 `tools/` 迁移至 `crew/util/`，作为内部工具使用

### 新增
- ✨ `graph.py` — LangGraph 流程图定义，`START → [collect_github, collect_news] → score_trends → write_report → publish → END`
- ✨ `nodes.py` — 五个独立节点实现（`collect_github` / `collect_news` / `score_trends` / `write_report` / `publish`）
- ✨ `llm_client.py` — 统一 LiteLLM 封装，支持三档模型 + JSON 模式 + Token 用量统计 + `build_crewai_llm()` 工厂函数
- ✨ `crew/github_trending/` — GitHub 趋势分析 CrewAI 模块（关键词规划 → 趋势排名）
- ✨ `crew/new_collect/` — 新闻采集 CrewAI 模块（多源抓取 + LLM 筛选）
- ✨ `crew/util/dedup_cache.py` — 本地去重缓存（从 `tools/` 迁移）
- ✨ `tools/wechat_publish_tool.py` — 微信公众号一体化发布工具（HTML 生成 + 草稿箱推送）
- ✨ 新增 `MODEL_LIGHT` / `MODEL_TOOL` 分级模型环境变量
- ✨ 新增 `LLM_DISABLE_THINKING` 配置，兼容 Kimi-K2.5 / DeepSeek-R1 等推理模型
- ✨ 新增 `ZHIHU_COOKIE` 配置，支持知乎热榜作为新闻源
- ✨ 完整测试套件（`tests/`），覆盖所有 Tool 的成功/失败/降级路径

### 变更
- 🔧 `config.py` 重构为 dataclass 结构（`LLMConfig` / `GitHubConfig` / `NewsConfig` / `WeChatConfig`）
- 🔧 `logger.py` 统一日志格式，支持按模块命名的 logger
- 🔧 `retry.py` 新增 `safe_request` 封装，统一 HTTP 重试和日志
- 🔧 `run.py` 支持 `--date` / `--dry-run` / `--verbose` CLI 参数
- 🔧 `metrics.py` 重构，支持运行指标持久化（JSON）
- 🔧 `pyproject.toml` 新增 `crewai==1.11.0` 依赖，完善开发工具链配置
- 🔧 `score_trends_node` 和 `write_report_node` 直接调用 LiteLLM（`call_llm_with_usage`），精确控制 Prompt

### 移除
- ❌ 移除旧版 `crew.py`（单文件 CrewAI Sequential Pipeline）
- ❌ 移除 `config/agents.yaml` / `config/tasks.yaml`（迁移到各子 Crew 目录）
- ❌ 移除 `AGENTS.md` / `doc/blog.md`（内容已整合到 README 和 docs/）
- ❌ 移除 `tools/wechat_article_tool.py` 和 `tools/wechat_draft_tool.py`（合并为 `wechat_publish_tool.py`）
- ❌ 移除 `tools/dedup_cache.py`（迁移至 `crew/util/dedup_cache.py`）

### 依赖更新
- `langgraph >= 1.1.3`（新增）
- `crewai == 1.11.0`（新增）
- `litellm >= 1.80.0`（升级）

---

## [0.1.0] - 2025-03-19

### 新增
- 🚀 初始版本发布
- ✨ 基于 CrewAI Sequential Pipeline 的 AI 趋势分析流水线
- 📊 GitHub 热门项目自动抓取和评分
- 📰 AI 行业新闻多源采集（HN / Reddit / newsdata.io）
- 📝 Markdown 日报自动生成
- 🔄 GitHub 仓库自动推送
- 💬 微信公众号 HTML 生成
- 📈 运行指标监控和持久化
- 🐳 Docker 容器化支持
- 🔄 去重缓存机制

### 技术特性
- 使用 CrewAI Sequential Pipeline 进行流程编排
- 分级模型策略（轻量模型用于采集，高质量模型用于写作）
- LiteLLM 统一 LLM 接口支持
- 多线程并行数据采集
- JSON 结构化评分系统

### 依赖
- Python 3.10+
- LiteLLM >= 1.80.0
- uv 包管理器

---

## 版本格式

版本号遵循 `MAJOR.MINOR.PATCH` 格式：

- **MAJOR**：不兼容的 API 变更
- **MINOR**：向后兼容的功能性新增
- **PATCH**：向后兼容的问题修复

## 发布说明

每个版本发布时，变更日志将包含：

1. **新增功能**：新添加的功能和特性
2. **变更**：现有功能的修改和优化
3. **修复**：问题修复和错误修正
4. **弃用**：即将移除的功能警告
5. **移除**：已移除的功能
6. **安全**：安全相关的更新

## 贡献指南

提交变更时请：

1. 在适当的版本标题下添加变更条目
2. 使用简洁的描述性语言
3. 关联相关的 Issue 或 Pull Request
4. 遵循既定的分类格式