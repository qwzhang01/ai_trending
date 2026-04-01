# Claude Code 启发的优化任务清单

> 📅 创建日期：2026-04-01
> 💡 灵感来源：Claude Code v2.1.88 源码（2026-03 泄露）
> 🎯 核心目标：从"批处理流水线"升级为"高信噪比 Agent 系统"
> 🏷️ 任务状态：⬜ 待开始 | 🔄 进行中 | ✅ 已完成 | ⏸️ 暂缓

---

## 问题诊断

当前系统是**批处理流水线**：数据一次性全量推送给 LLM，LLM 需要从大量噪音字段中自行
筛选信息，导致注意力分散、输出质量不稳定。

Claude Code 的核心设计是**查询循环 Agent**：Agent 按需获取上下文，每步决策基于精准信息。

| 维度 | 当前系统 | Claude Code 启发的改进 |
|------|---------|----------------------|
| 信息传递 | 全量 JSON + 原始数据一次性塞入 | 精简 Brief，只传核心信号 |
| 事实核对 | 无（只做格式校验） | 核对报告数字与数据源一致性 |
| 上下文获取 | 全量推送（被动接收） | Agent 主动按需查询工具 |
| Prompt 缓存 | 静态/动态混用，每次重算 | 静态段可缓存，动态段分离 |
| 记忆层 | 2 层（表达 + 话题） | 新增第 3 层：编辑决策记忆 |
| 质量反馈 | 写作完成即记录 | 发布成功后才记录好模式 |

---

## OPT-001: 削减 WritingBrief 噪音字段

**优先级**: 🔴 P1（性价比最高）
**预估工时**: 2h
**状态**: ✅ 已完成（2026-04-01）

### 问题

`WritingBrief.format_for_prompt()` 当前输出约 3000-5000 tokens，包含大量低价值字段：
- `url`（写作时不需要 URL，发布时才需要）
- `language`（编程语言对内容质量影响极小）
- `content_excerpt`（原始正文摘要，已经有 `so_what_analysis` 更好的加工版）
- 原始数据 `github_data`、`news_data`、`scoring_result` 同时传入（三份冗余）

此外，`tasks.yaml` 中同时传入 `writing_brief` 和 `scoring_result`（原始 JSON），
LLM 面对两份相互重叠的数据，注意力被严重稀释。

### 改动

**`models.py` — `format_for_prompt()` 精简输出**：
- 删除：`url`、`language`、`content_excerpt`（从 Brief 中，写作层不需要）
- 保留：`name`、`stars`、`stars_growth_7d`、`story_hook`、`technical_detail`、
  `target_audience`、`suggested_angle`、`one_line_reason`
- 新闻保留：`title`、`source`、`credibility_label`、`category`、`so_what_analysis`
- 删除新闻的 `url`（写作层不需要，发布层有完整数据）

**`tasks.yaml` — 移除 `scoring_result` 原始 JSON**：
- `{scoring_result}` 作为 prompt 输入对写作层没有增量价值（已经有 WritingBrief）
- 同理去掉 `{github_data}` 和 `{news_data}` 原始数据（保留 WritingBrief 即可）

### 预期效果

- Prompt 长度从 ~5000 tokens 压缩到 ~2500 tokens
- LLM 注意力更集中，减少"从噪音中提取信号"的认知负担

### 验收标准

- [x] `format_for_prompt()` 不再输出 `url`、`language`、`content_excerpt`
- [x] `tasks.yaml` 移除 `{github_data}`、`{news_data}`、`{scoring_result}` 占位符
- [x] 测试：`format_for_prompt()` 输出 token 估算 < 3000
- [x] 测试：精简后 Brief 仍包含所有核心写作素材

---

## OPT-002: QualityReviewCrew 加入事实核对

**优先级**: 🔴 P1
**预估工时**: 3h
**状态**: ✅ 已完成（2026-04-01）

### 问题

当前 `QualityReviewCrew` 只检查**格式规范**（是否有禁用词、是否有 Section 等），
没有检查**内容事实**。典型的 LLM 幻觉场景：

- 日报写"⭐ 12,000（+3,000）"但 WritingBrief 中是"⭐ 8,500（+1,200）"
- 日报写"发布仅 2 周"但 created_at 是 3 个月前
- 日报写"推理成本降低 50%"但 so_what_analysis 没有这个数字

### 改动

**`QualityReviewCrew` — 新增 `FactCheckTask`**：
- 输入：`report_content` + `writing_brief`（包含真实数字的来源）
- 检查项：
  1. 日报中所有出现的 `⭐` 星数 是否与 WritingBrief 一致（允许 ±5% 误差）
  2. 日报中的"发布仅 N 天/周/月"是否有对应的 `created_at` 支撑
  3. 日报中百分比数字是否来自 WritingBrief 的 `so_what_analysis`（无来源的数字标记为疑似虚构）

**`nodes.py` — `write_report_node` 传入 `writing_brief_text` 给 quality_review_node**：
- `writing_brief` 是事实核对的基准来源

### 验收标准

- [x] `QualityReviewCrew.run()` 接收 `writing_brief` 参数
- [x] 能检测出星数不一致的情况（测试用例）
- [x] 能检测出无来源的百分比数字（测试用例）
- [x] 事实核对结果记录到 `quality_review` 字段，不阻断发布

---

## OPT-003: EditorialPlanningCrew 配备按需查询工具

**优先级**: 🟡 P2
**预估工时**: 4h
**状态**: ✅ 已完成（2026-04-01）

### 问题

当前 `editorial_planning_node` 在调用 Crew 之前，预先推送了所有可能需要的上下文
（`topic_context`），这是"批量推送"模式。

Claude Code 的设计是 Agent 配备工具，**自己决定需要什么上下文**：
- 有时不需要历史，直接做决策
- 有时需要查看近 3 天话题，避免重复
- 有时需要查看近期风格记忆，避免重复表达

### 改动

**新建 `crew/editorial_planning/tools.py`**：

```python
def make_topic_history_tool(tracker: TopicTracker) -> BaseTool:
    """查询近期话题记录工具。"""

def make_style_memory_tool(memory: StyleMemory) -> BaseTool:
    """查询近期风格记忆工具。"""

def make_search_prev_reports_tool(reports_dir: Path) -> BaseTool:
    """搜索历史日报中是否报道过某话题。"""
```

**`EditorialPlanningCrew` — Agent 配备工具列表**：
- Agent 主动调用工具，而非被动接收推送的 `topic_context` 字符串
- `topic_context` 改为工具可查询的来源，不再直接塞入 Prompt

### 验收标准

- [x] EditorialPlanningCrew 的 Agent 配备 3 个工具
- [x] 工具均通过工厂函数创建，无全局状态
- [x] 测试：Agent 能正确调用 topic_history 工具并返回记录

---

## OPT-004: tasks.yaml 静态/动态分段

**优先级**: 🟡 P2
**预估工时**: 2h
**状态**: ✅ 已完成（2026-04-01）

### 问题

Claude Code 将 System Prompt 分为**可缓存**（静态：角色定义、规范）和**不可缓存**
（动态：时间戳、环境信息）两段。

当前 `tasks.yaml` 把静态约束（写作规范、示例、结构说明）和动态数据（`{writing_brief}`、
`{style_guidance}`、`{current_date}`）混在一起，每次 `style_guidance` 变化都会使
整个 prompt cache 失效，增加 API 成本。

### 改动

**`tasks.yaml` 结构重组**：

```yaml
write_report_task:
  description: >
    # ======== 静态段（写作规范，可被 API 缓存）========
    [角色定义 + 质量标准 + 段落示例 + 七段式结构说明]
    [这部分内容每次完全一致，可被 prompt cache 缓存]

    # ======== 动态段（今日数据，每次不同）========
    当前日期：{current_date}

    ## 编辑决策
    {editorial_plan}

    ## 写作简报
    {writing_brief}

    ## 风格记忆
    {style_guidance}

    ## 上期回顾数据
    {previous_report_context}
```

关键原则：静态段放在 description 前部，动态段放在后部，保证静态段的 cache key 稳定。

### 验收标准

- [x] tasks.yaml 静态规范部分移到 description 前部
- [x] 动态数据（{current_date} 等）全部在 description 后部
- [x] 移除 `{github_data}`、`{news_data}`、`{scoring_result}`（OPT-001 同步完成）

---

## OPT-005: 新增 DecisionMemory — 编辑决策记忆层

**优先级**: 🟢 P3
**预估工时**: 4h
**状态**: ✅ 已完成（2026-04-01）

### 问题

当前记忆系统有 2 层：
- `StyleMemory`：记录表达模式（文字层面）
- `TopicTracker`：记录近期话题（内容层面）

缺少第 3 层：**编辑决策记忆**，记录"什么样的编辑决策导致了好/坏的日报"。

例如：
- 当 GitHub 有 3 个以上 Agent 框架时，选小众的做头条效果更好
- 当新闻全是大厂发布时，信号强度降为 🟡 反而更真实
- "对比切入"角度比"规模切入"更少产生模板感

### 改动

**新建 `crew/report_writing/decision_memory.py`**：

```python
class DecisionRecord(BaseModel):
    date: str
    signal_strength: str          # 本次信号强度
    headline_type: str            # 头条类型：repo/news
    angle_used: str               # 主要使用的切入角度
    kill_list_size: int           # Kill List 大小
    validation_passed: bool       # 格式校验是否通过
    quality_score: int            # 质量审核通过的检查项数

class DecisionMemory:
    def record_decision(self, plan: EditorialPlan, quality_result: ...) -> None
    def get_decision_guidance(self) -> str  # 注入到 editorial_planning 的 Prompt
    def get_best_patterns(self) -> list[str]  # 历史上效果好的编辑决策模式
```

**集成到 `editorial_planning_node`**：
- 在调用 Crew 前，注入 `decision_guidance` 到编辑决策 Prompt
- 在 `quality_review_node` 完成后，记录本次决策结果

### 验收标准

- [x] `DecisionMemory` 类实现完整
- [x] `editorial_planning_node` 注入 decision_guidance
- [x] `quality_review_node` 完成后触发 decision 记录
- [x] 测试覆盖：记录/读取/过期清理

---

## OPT-006: Post-publish Hook — 发布成功后才记录好模式

**优先级**: 🟢 P3
**预估工时**: 2h
**状态**: ✅ 已完成（2026-04-01）

### 问题

当前 `StyleMemory.record_quality_result()` 在 `write_report_node` 完成后立即触发，
即使后续 `quality_review_node` 发现严重问题，这份日报的写作模式也已经被记录为"好模式"。

Claude Code 的 post-sampling hook 逻辑：**只有最终"成功"的输出才触发记忆提取**。

### 改动

**`publish_node` 发布成功后触发记忆记录**：

```python
# 当前：write_report_node 完成就记录（可能是低质量日报）
# 改为：publish_node 发布成功后才记录

def publish_node(state):
    ...
    if all_published_successfully:
        _record_successful_patterns(state)  # post-publish hook

def _record_successful_patterns(state):
    """发布成功后，把这期日报的好模式记录到 StyleMemory。"""
    report = state.get("report_content", "")
    current_date = state.get("current_date", "")
    quality_review = state.get("quality_review", "")

    # 只在质量审核通过的情况下记录好模式
    if "passed=True" in quality_review or not quality_review:
        style_mem = StyleMemory()
        good_patterns, _ = style_mem.extract_patterns_from_report(report)
        style_mem.record_quality_result(
            date=current_date,
            validation_issues=[],  # 发布成功 = 无阻断性问题
            good_patterns=good_patterns,
            bad_patterns=[],       # 不记录坏模式（已经通过了）
        )
```

**`write_report_node` 移除 StyleMemory 记录**：
- 写作完成时只提取 patterns（检测），不记录到文件
- 记录动作推迟到发布成功后

### 验收标准

- [x] `write_report_node` 不再调用 `StyleMemory.record_quality_result()`
- [x] `publish_node` 发布成功后调用 `_record_successful_patterns()`
- [x] 质量审核失败的日报不触发好模式记录
- [x] 测试：发布失败时 StyleMemory 不被写入

---

## 实施顺序

```
OPT-001（削减噪音）→ OPT-004（分段缓存）  # 同时做，都是 tasks.yaml 改动
OPT-002（事实核对）                        # 独立，QualityReview 改动
OPT-003（按需工具）                        # Editorial 改动
OPT-005（决策记忆）→ OPT-006（发布钩子）  # 记忆层，最后做
```

---

## 预期效果

| 指标 | 当前 | 优化后 |
|------|------|--------|
| 写作 Prompt 长度 | ~5000 tokens | ~2500 tokens |
| LLM 幻觉率（数字错误） | ~20% | ~5% |
| 编辑决策重复率 | 无追踪 | < 10% |
| 好模式记录准确性 | 低（所有日报都记录） | 高（只记录发布成功的） |
| API 缓存命中率 | 低（动静混用） | 提升 ~30% |

---

*每完成一个任务后更新状态标记。*
