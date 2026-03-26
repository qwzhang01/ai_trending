# 贡献指南

感谢你对 **AI Trending** 的关注！我们欢迎任何形式的贡献，包括 Bug 报告、功能建议、文档改进和代码提交。

---

## 目录

- [行为准则](#行为准则)
- [如何贡献](#如何贡献)
  - [报告 Bug](#报告-bug)
  - [提交功能建议](#提交功能建议)
  - [提交代码](#提交代码)
- [开发环境搭建](#开发环境搭建)
- [代码规范](#代码规范)
- [提交信息规范](#提交信息规范)
- [Pull Request 流程](#pull-request-流程)
- [项目架构说明](#项目架构说明)

---

## 行为准则

参与本项目即表示你同意遵守以下基本准则：

- 尊重所有参与者，保持友善和专业的交流态度
- 接受建设性批评，聚焦于问题本身而非个人
- 优先考虑对社区整体有益的决策

---

## 如何贡献

### 报告 Bug

在提交 Bug 报告前，请先：

1. 搜索 [现有 Issues](https://github.com/your-username/ai_trending/issues)，确认问题尚未被报告
2. 确认你使用的是最新版本

提交 Bug 时，请包含以下信息：

- **环境信息**：操作系统、Python 版本、依赖版本
- **复现步骤**：最小化的复现步骤
- **期望行为**：你期望发生什么
- **实际行为**：实际发生了什么
- **日志输出**：相关的错误日志（注意脱敏，不要包含 API Key）

```markdown
**环境**
- OS: macOS 14.0
- Python: 3.11.5
- ai_trending: 0.1.0

**复现步骤**
1. 配置 .env 文件
2. 运行 `python run.py`
3. 报错信息如下...

**期望行为**
正常生成日报

**实际行为**
抛出 XXX 异常
```

### 提交功能建议

在提交功能建议前，请先搜索现有 Issues 确认没有重复。

功能建议请包含：

- **使用场景**：这个功能解决什么问题
- **建议方案**：你期望的实现方式
- **替代方案**：你考虑过的其他方案
- **额外背景**：截图、参考链接等

### 提交代码

1. Fork 本仓库
2. 基于 `main` 分支创建特性分支：`git checkout -b feat/your-feature-name`
3. 完成开发并通过所有测试
4. 提交 Pull Request

---

## 开发环境搭建

### 前置要求

- Python 3.10 ~ 3.13
- [uv](https://docs.astral.sh/uv/)（推荐）或 pip

### 克隆并安装

```bash
# 克隆仓库
git clone https://github.com/your-username/ai_trending.git
cd ai_trending

# 使用 uv 安装依赖（推荐）
uv sync

# 或使用 pip
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

### 配置环境变量

```bash
cp .env.example .env
# 编辑 .env，填入必要的 API Key
```

### 验证安装

```bash
# 校验配置（不执行实际任务）
.venv/bin/python run.py --dry-run

# 运行单元测试
.venv/bin/python -m pytest tests/unit/ -v
```

---

## 代码规范

本项目使用以下工具保证代码质量：

| 工具 | 用途 | 配置文件 |
|------|------|---------|
| `ruff` | Lint + 格式化 | `pyproject.toml` |
| `black` | 代码格式化 | `pyproject.toml` |
| `mypy` | 类型检查 | `pyproject.toml` |
| `pytest` | 单元测试 | `pyproject.toml` |

### 运行代码检查

```bash
# 格式化代码
.venv/bin/python -m black src/ tests/

# Lint 检查
.venv/bin/python -m ruff check src/ tests/

# 类型检查
.venv/bin/python -m mypy src/

# 运行所有单元测试
.venv/bin/python -m pytest tests/unit/ -v

# 运行测试并查看覆盖率
.venv/bin/python -m pytest tests/unit/ --cov=src/ai_trending --cov-report=term-missing
```

### 代码风格要点

- **行长度**：最大 88 字符
- **类型注解**：所有公开函数必须有类型注解
- **文档字符串**：公开类和函数必须有 docstring
- **注释语言**：代码注释使用中文
- **导入顺序**：标准库 → 第三方库 → 本地模块（isort 自动处理）

### 架构约束（必须遵守）

在提交代码前，请确认：

- ✅ LangGraph 节点中**没有**直接调用 `call_llm` / `litellm`
- ✅ 所有 LLM 调用通过 `build_crewai_llm(tier)` 工厂函数
- ✅ API Key 从环境变量读取，**没有**硬编码
- ✅ Fetcher 层**没有**任何 LLM 调用
- ✅ 发布 Tool 只做格式转换 + API 调用，**不修改**内容
- ✅ CrewAI Task 有 `output_pydantic` 定义

---

## 提交信息规范

本项目遵循 [Conventional Commits](https://www.conventionalcommits.org/) 规范：

```
<类型>(<范围>): <简短描述>

[可选的详细描述]

[可选的关联 Issue]
```

### 类型说明

| 类型 | 说明 |
|------|------|
| `feat` | 新功能 |
| `fix` | Bug 修复 |
| `docs` | 文档更新 |
| `style` | 代码格式调整（不影响逻辑） |
| `refactor` | 代码重构（不新增功能，不修复 Bug） |
| `test` | 新增或修改测试 |
| `chore` | 构建流程、依赖更新等杂项 |
| `perf` | 性能优化 |

### 示例

```bash
feat(crew): 新增飞书发布渠道 Tool

实现 FeishuPublishTool，支持将日报推送到飞书群机器人。
- 支持 Markdown 转飞书消息卡片格式
- 从环境变量读取 FEISHU_WEBHOOK_URL
- 独立容错，失败不影响其他渠道

Closes #42
```

```bash
fix(fetcher): 修复知乎热榜解析在无 Cookie 时崩溃的问题

当 ZHIHU_COOKIE 未配置时，SSR 提取逻辑会因 NoneType 报错。
改为返回空列表并记录 warning，不影响其他数据源。
```

---

## Pull Request 流程

1. **确保测试通过**：提交前运行 `pytest tests/unit/`，确保无失败用例
2. **更新文档**：如果新增了配置项，同步更新 `.env.example`
3. **填写 PR 描述**：说明改动内容、解决的问题、测试方式
4. **关联 Issue**：如果有对应 Issue，在描述中使用 `Closes #N`
5. **等待 Review**：维护者会在 3 个工作日内回复

### PR 描述模板

```markdown
## 改动内容

简要描述本次 PR 做了什么。

## 解决的问题

- Closes #N（关联 Issue）

## 改动类型

- [ ] Bug 修复
- [ ] 新功能
- [ ] 文档更新
- [ ] 重构
- [ ] 其他

## 测试方式

描述如何验证这个改动是正确的。

## 注意事项

有没有需要 Reviewer 特别关注的地方？
```

---

## 项目架构说明

在贡献代码前，建议先了解项目的分层架构：

```
入口层 (run.py)
    ↓
编排层 (LangGraph: graph.py + nodes.py)
    ↓
Agent 层 (CrewAI: crew/)
    ↓
工具层 (tools/)
    ↓
基础设施 (llm_client.py / config.py / retry.py)
```

### 新增发布渠道

1. 在 `src/ai_trending/tools/` 下创建 `{channel}_publish_tool.py`
2. 继承 `BaseTool`，`_run` 只做格式转换 + API 调用
3. 在 `nodes.py` 的 `_get_enabled_publish_tools()` 中注册
4. 在 `.env.example` 中补充环境变量说明
5. 新增对应测试文件 `tests/unit/tools/test_{channel}_publish_tool.py`

### 新增数据源

1. 在对应 Crew 的 `fetchers.py` 中新增抓取函数
2. 使用 `safe_request` 发起 HTTP 请求
3. 返回包含 `title / url / score / source / summary / time` 字段的列表
4. 加入并发抓取（`ThreadPoolExecutor`）
5. 新增对应测试

---

如有任何问题，欢迎在 [Discussions](https://github.com/your-username/ai_trending/discussions) 中提问。
