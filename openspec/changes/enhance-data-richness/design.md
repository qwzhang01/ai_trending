## Context

当前数据流如下：

```
fetchers.py
  ├─ _fetch_readmes_concurrently()  → RepoCandidate.readme_summary ✅ 已实现
  └─ _track_star_growth()           → RepoCandidate.stars_growth_7d ✅ 已实现
        ↓
github_trending/crew.py
  → ranker.py 合并评分
  → formatter.format_text_output()  ← ❌ 断裂点：丢弃了 readme_summary / stars_growth_7d
        ↓
nodes.py: github_data (str)         ← 只有描述、星数、评分，无 README 无增长数据
        ↓
trend_scoring/tasks.yaml            ← LLM 只能基于一句话描述推断 story_hook
        ↓
_build_writing_brief()              ← RepoBrief.readme_summary 始终为空
        ↓
report_writing/tasks.yaml           ← 写作层无真实素材，只能套模板
```

**根本问题**：`formatter.format_text_output()` 在将 `RepoCandidate` 序列化为字符串时，只输出了基础字段（描述、星数、评分），丢弃了 `readme_summary` 和 `stars_growth_7d`。这两个字段虽然在采集层已经正确填充，但从未进入下游的 LLM Prompt。

**约束**：
- `github_data` 是纯字符串，在 LangGraph State 中传递，不能改为结构化对象（会破坏现有接口）
- 评分层 Prompt 已经有 `readme_summary` 字段的预留位置（`scored_repos` 中无此字段，但 `story_hook` 生成规则可以引用）
- `_build_writing_brief` 中 `RepoBrief.readme_summary` 字段存在但始终为空（因为 `scored_repos` JSON 里没有这个字段）

## Goals / Non-Goals

**Goals:**
- 修复 `formatter.py`，在 `github_data` 字符串中包含 `readme_summary`（截断到 300 字）和 `stars_growth_7d`
- 修复 `_build_writing_brief`，从 `github_data` 原始字符串中提取 `readme_summary` 并填入 `RepoBrief`（或通过评分层中转）
- 更新评分层 Prompt，要求在有 README 素材时 `story_hook` 必须引用真实内容
- 确保 `stars_growth_7d` 在 `WritingBrief` 的 `format_for_prompt()` 输出中可见

**Non-Goals:**
- 不修改 LangGraph State 的数据类型（`github_data` 保持 `str`）
- 不新增外部 API 调用（README 抓取已实现）
- 不修改 `star_tracker.py`（已正确实现）
- 不修改新闻采集链路

## Decisions

### 决策 1：在 formatter.py 中追加 README 和增长数据

**选择**：在 `format_text_output` 函数中，为每个 repo 追加 `README摘要` 和 `7日增长` 字段输出。

**理由**：`formatter.py` 是唯一的序列化出口，在此处修改影响最小、最集中。`github_data` 字符串是评分层 Prompt 的直接输入，只要这里有数据，评分层 LLM 就能看到。

**替代方案**：新增一个结构化的 `github_data_rich` State 字段 → 否决，会破坏现有接口，改动面太大。

**README 截断长度**：300 字符（而非 500）。原因：`github_data` 包含多个项目，总长度需控制在 ~4000 tokens 以内，避免评分层 Prompt 过长。

### 决策 2：通过评分层中转 readme_summary 到写作层

**选择**：在 `trend_scoring/config/tasks.yaml` 的 `scored_repos` 输出要求中，新增 `readme_summary` 字段（从输入的 `github_data` 中提取并原样传递），同时在 `_build_writing_brief` 中从 `scored_repos` 读取该字段填入 `RepoBrief`。

**理由**：评分层已经读取了 `github_data`，让它在输出 JSON 中原样传递 `readme_summary` 是最简单的中转方式，无需修改 State 结构。

**替代方案**：在 `_build_writing_brief` 中直接解析 `github_data` 字符串提取 README → 否决，字符串解析脆弱，不如通过结构化 JSON 中转可靠。

### 决策 3：评分层 story_hook 生成规则强化

**选择**：在 `trend_scoring/config/tasks.yaml` 中，为 `story_hook` 和 `technical_detail` 字段增加约束：**当 readme_summary 非空时，必须从中引用至少一个具体的技术名词、数字或对比对象**，禁止纯推断式描述（如"和X不同，Y支持..."这类无数据支撑的模板句）。

**理由**：这是提升叙事质量的核心杠杆。有了 README 素材，LLM 就有了真实的技术细节可以引用，不再需要靠推断填充。

## Risks / Trade-offs

- **[风险] README 内容质量参差不齐** → 缓解：在 Prompt 中说明"如果 README 内容为空或无实质信息，允许基于描述推断，但需标注为推断"
- **[风险] 评分层 Prompt 变长，token 消耗增加** → 缓解：README 截断到 300 字，预计每个项目增加约 100 tokens，5 个项目共增加 ~500 tokens，可接受
- **[风险] 评分层输出 JSON 新增 readme_summary 字段，可能导致 Pydantic 模型校验失败** → 缓解：在 `ScoredRepo` 模型中新增 `readme_summary: str = ""` 可选字段，向后兼容
- **[Trade-off] formatter.py 输出变长** → 接受：数据丰富度提升的收益远大于字符串变长的代价

## Migration Plan

1. 修改 `formatter.py` → 追加 README 和增长数据字段
2. 修改 `trend_scoring/models.py` → `ScoredRepo` 新增 `readme_summary` 字段
3. 修改 `trend_scoring/config/tasks.yaml` → 新增 `readme_summary` 输出要求 + 强化 `story_hook` 生成规则
4. 修改 `nodes.py` 中 `_build_writing_brief` → 从 `scored_repos` 读取 `readme_summary` 填入 `RepoBrief`
5. 验证：运行一次完整流水线，检查日报头条是否包含真实技术细节

**回滚**：所有修改均向后兼容（新增字段有默认值），如有问题直接 `git revert` 对应提交即可。

## Open Questions

- `readme_summary` 截断到 300 字是否足够？需要在实际运行后观察评分层的 `story_hook` 质量，可能需要调整到 400-500 字
- 是否需要对 README 内容做语言检测（部分项目 README 为中文），目前不做处理，让 LLM 自行处理多语言
