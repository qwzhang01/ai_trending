# Security Policy

## 支持的版本

我们为以下版本提供安全更新支持：

| 版本 | 支持状态 |
| ---- | -------- |
| `main` 分支 | ✅ 持续支持 |
| `0.1.x` | ✅ 支持 |
| 更早版本 | ❌ 不再支持 |

---

## 报告安全漏洞

**请勿通过 GitHub Issues 公开报告安全漏洞。**

如果你发现了安全漏洞，请通过以下方式私下联系我们：

### 方式一：GitHub Security Advisories（推荐）

1. 前往本仓库的 [Security Advisories](../../security/advisories/new) 页面
2. 点击 **"Report a vulnerability"**
3. 填写漏洞详情并提交

### 方式二：邮件报告

发送邮件至项目维护者，邮件主题格式：

```
[SECURITY] <漏洞简要描述>
```

请在报告中包含以下信息：

- **漏洞类型**（如：API Key 泄露、命令注入、SSRF 等）
- **影响范围**（哪些版本、哪些功能受影响）
- **复现步骤**（详细的操作步骤）
- **概念验证代码**（如有）
- **潜在影响**（攻击者可以做什么）
- **建议修复方案**（如有）

---

## 响应时间承诺

| 阶段 | 时间目标 |
| ---- | -------- |
| 确认收到报告 | 48 小时内 |
| 初步评估结果 | 7 个工作日内 |
| 修复方案确认 | 14 个工作日内 |
| 发布安全补丁 | 视严重程度，通常 30 天内 |

---

## 安全最佳实践

在使用本项目时，请遵循以下安全建议：

### API Key 管理

```bash
# ✅ 正确：使用 .env 文件存储密钥（已在 .gitignore 中排除）
cp .env.example .env
# 编辑 .env，填入真实密钥

# ❌ 错误：直接在代码中硬编码密钥
OPENAI_API_KEY = "sk-..."  # 绝对禁止
```

**关键原则**：
- 所有 API Key、Token、Secret 必须通过环境变量传入
- `.env` 文件已在 `.gitignore` 中排除，**永远不要** commit `.env` 文件
- 在 GitHub Actions 中使用 [Encrypted Secrets](https://docs.github.com/en/actions/security-guides/encrypted-secrets) 管理密钥
- 定期轮换 API Key，尤其是 GitHub Token 和 OpenAI API Key

### GitHub Token 权限最小化

本项目的 GitHub Token 只需要以下最小权限：

```
# Fine-grained Personal Access Token 推荐权限：
- Contents: Read and Write（用于推送报告）
- Issues: Read and Write（用于发布 Issue 报告，可选）
- Metadata: Read（必须）
```

**不要使用** 拥有全部权限的 Classic Token。

### Docker 部署安全

```bash
# ✅ 推荐：通过 --env-file 传入密钥，不要在 docker run 命令中明文传入
docker run --env-file .env ai-trending

# ❌ 避免：命令行明文传入密钥（会出现在进程列表和 shell 历史中）
docker run -e OPENAI_API_KEY=sk-xxx ai-trending
```

### 网络请求安全

本项目会向以下外部服务发起网络请求：

| 服务 | 用途 | 数据类型 |
| ---- | ---- | -------- |
| `api.openai.com`（或自定义 Base） | LLM 推理 | 项目名称、新闻标题等公开数据 |
| `api.github.com` | 获取 GitHub Trending | 公开仓库信息 |
| `newsdata.io` | 获取 AI 新闻 | 公开新闻数据 |
| `api.weixin.qq.com` | 发布微信公众号草稿 | 日报内容 |

**注意**：本项目不会收集、存储或传输任何用户个人信息。

---

## 已知安全注意事项

### 1. LLM Prompt Injection

本项目将外部数据（GitHub 仓库描述、新闻标题）作为 LLM Prompt 的一部分。恶意构造的仓库描述或新闻标题理论上可能影响 LLM 输出内容。

**缓解措施**：
- 日报内容仅用于信息展示，不会触发任何系统操作
- 发布前有内容校验步骤

### 2. 微信 Access Token 存储

微信 `access_token` 有效期为 7200 秒，本项目在内存中缓存，不持久化到磁盘。

### 3. 日志中的敏感信息

默认日志级别为 `INFO`，不会记录 API Key 等敏感信息。开启 `DEBUG` 模式时请注意日志文件的访问权限。

---

## 漏洞披露政策

我们遵循**协调披露（Coordinated Disclosure）**原则：

1. 报告者私下提交漏洞
2. 维护者确认并修复漏洞
3. 发布安全补丁
4. 补丁发布后，报告者可公开披露漏洞详情（通常在补丁发布 7 天后）

我们会在 [CHANGELOG.md](CHANGELOG.md) 和 GitHub Release Notes 中注明安全修复，并致谢报告者（除非报告者要求匿名）。

---

## 致谢

感谢所有负责任地报告安全问题的研究者。你们的贡献让这个项目更安全。

---

*本安全政策参考 [GitHub Security Policy 最佳实践](https://docs.github.com/en/code-security/getting-started/adding-a-security-policy-to-your-repository) 制定。*
