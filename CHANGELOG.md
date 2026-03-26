# Changelog

本文件记录项目的所有重要变更，格式遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/)，版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [Unreleased]

### 计划中
- 支持飞书机器人发布渠道
- 支持钉钉机器人发布渠道
- 支持邮件订阅发布
- 增加 Web Dashboard 查看历史报告
- 支持自定义报告模板

---

## [0.1.0] - 2026-03-17

### 新增
- **LangGraph 编排层**：基于 LangGraph 状态机实现全局流程控制，支持并行采集和条件分支
- **GitHub 趋势采集**：通过 GitHub Search API 采集热点 AI 开源项目，支持关键词规划 → 搜索采集 → 趋势排名三阶段流水线
- **AI 新闻采集**：多源并发抓取（Hacker News、Reddit、NewsData.io、知乎），支持跨日去重
- **趋势评分**：基于 CrewAI Agent 对项目和新闻进行综合评分排名
- **日报生成**：`ReportWritingCrew` 将结构化数据转化为标准四段式 Markdown 日报
- **GitHub 发布**：自动将日报推送到指定 GitHub 仓库的 Issues 或文件
- **微信公众号发布**：将 Markdown 转换为符合微信规范的内联样式 HTML，推送到草稿箱
- **三档 LLM 体系**：`light` / `default` / `strong` 三档模型，按场景选择，控制成本
- **运行指标采集**：`RunMetrics` 记录每次运行的耗时、Token 用量、费用估算
- **Webhook 通知**：支持企业微信、飞书、钉钉、Slack 机器人通知运行结果
- **Docker 支持**：提供多阶段构建 Dockerfile 和 docker-compose 定时调度配置
- **GitHub Actions**：内置每日定时运行工作流（北京时间早 8 点）
- **去重缓存**：`DedupCache` 实现跨日内容去重，避免重复推送相同内容
- **错误处理**：三级错误体系（L1 可忽略 / L2 可降级 / L3 致命），单渠道失败不影响整体流程

### 技术栈
- Python 3.10+
- LangGraph 1.1+（全局流程编排）
- CrewAI 1.11（Agent 内部推理）
- LiteLLM（统一 LLM 调用，支持 OpenAI / Anthropic / DeepSeek / Ollama 等）
- Pydantic v2（结构化数据模型）
- uv（依赖管理）

---

## 版本说明

### 版本号规则

本项目遵循 [语义化版本 2.0.0](https://semver.org/lang/zh-CN/)：

- **MAJOR**（主版本）：不兼容的 API 变更，如 `TrendingState` 字段重命名、Crew 接口变更
- **MINOR**（次版本）：向后兼容的新功能，如新增发布渠道、新增数据源
- **PATCH**（修订版）：向后兼容的问题修复，如 Bug 修复、性能优化

### 变更类型说明

| 类型 | 说明 |
|------|------|
| `新增` | 新功能 |
| `变更` | 对现有功能的变更 |
| `废弃` | 即将移除的功能 |
| `移除` | 已移除的功能 |
| `修复` | Bug 修复 |
| `安全` | 安全漏洞修复 |

---

[Unreleased]: https://github.com/your-username/ai-trending/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/your-username/ai-trending/releases/tag/v0.1.0
