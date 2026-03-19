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
3. 提交更改 (`git commit -m 'Add some amazing feature'`)
4. 推送到分支 (`git push origin feature/amazing-feature`)
5. 创建 Pull Request

### 开发环境设置

```bash
# 克隆仓库
git clone https://github.com/your-username/ai-trending.git
cd ai-trending

# 安装依赖
uv sync

# 运行测试
uv run pytest
```

## 代码规范

### Python 代码风格
- 遵循 PEP 8 规范
- 使用 Black 进行代码格式化
- 使用 isort 进行导入排序
- 类型注解推荐但不强制

### 提交信息规范
- 使用英文描述提交内容
- 格式：`类型: 简短描述`
- 类型包括：feat, fix, docs, style, refactor, test, chore

### 测试要求
- 新功能必须包含测试用例
- 确保所有现有测试通过
- 测试覆盖率不应降低

## 项目结构说明

- `src/ai_trending/` - 核心代码
- `tests/` - 测试代码
- `reports/` - 生成的日报
- `output/` - 输出文件
- `metrics/` - 运行指标

## 沟通渠道

- GitHub Issues: 问题讨论和功能请求
- Pull Requests: 代码审查和合并
- 项目 Wiki: 详细文档和使用指南

## 行为准则

请遵守我们的 [行为准则](CODE_OF_CONDUCT.md)，确保社区环境友好和尊重。