# AI 日报优化实施指南

## 概述

本指南提供将 AI 日报从「信息搬运」模式优化为「信息判断」模式的具体实施步骤。优化核心是引入三轮工作流、叙事性表达和 So What 分析。

## 一、准备工作

### 1.1 环境检查

确保项目环境满足以下要求：

```bash
# 检查项目结构
ls -la src/ai_trending/
# 应该包含：
# - crew/           # CrewAI 模块
# - tools/          # 工具层
# - nodes.py        # LangGraph 节点
# - graph.py        # 图定义
# - llm_client.py   # LLM 客户端

# 检查配置文件
ls -la config/
# 应该包含：
# - agents.yaml     # Agent 配置
# - tasks.yaml      # Task 配置
# - .env            # 环境变量
```

### 1.2 备份现有配置

在开始优化前，备份关键文件：

```bash
# 备份关键文件
cp src/ai_trending/crew/report_writing/config/agents.yaml src/ai_trending/crew/report_writing/config/agents.yaml.backup
cp src/ai_trending/crew/report_writing/config/tasks.yaml src/ai_trending/crew/report_writing/config/tasks.yaml.backup
cp src/ai_trending/crew/report_writing/crew.py src/ai_trending/crew/report_writing/crew.py.backup
cp src/ai_trending/nodes.py src/ai_trending/nodes.py.backup
```

## 二、分步实施

### 2.1 第一步：更新 Agent 配置（agents.yaml）

**目标**：优化 Agent 的 backstory，强调叙事性表达

**操作步骤**：

1. 打开文件：`src/ai_trending/crew/report_writing/config/agents.yaml`
2. 找到 `report_writer` Agent 配置
3. 更新 backstory，加入叙事性表达要求：

```yaml
report_writer:
  role: "AI 日报撰写专家"
  goal: >
    将 GitHub 热点项目和 AI 新闻数据整合为一份结构清晰、判断精准的 AI 日报，
    总字数控制在 700-1500 字之间。
  backstory: >
    你是一位专注 AI 领域的技术编辑，文风克制、精准、有判断力。
    你的原则：每一条内容都必须回答「这对行业意味着什么」。
    你绝不使用「重磅」「颠覆」「震撼」等词，不用感叹号，用事实说话。
    你深知读者是忙碌的技术从业者，他们需要的是信息密度高、判断准确的内容，
    而不是堆砌数据或情绪渲染。
    
    **新增职责**：
    - 用讲故事的方式介绍项目，而不是填表格
    - 为每条新闻提供「So What」分析
    - 为趋势洞察提供因果解释
    - 制造信息差悬念，提供具体技术细节支撑
```

**验证方法**：
```python
# 验证 Agent 配置
from ai_trending.crew.report_writing.config.agents import agents_config
assert "讲故事" in agents_config["report_writer"]["backstory"]
assert "So What" in agents_config["report_writer"]["backstory"]
assert "重磅" not in agents_config["report_writer"]["backstory"]
```

### 2.2 第二步：更新 Task 配置（tasks.yaml）

**目标**：实现三轮工作流设计

**操作步骤**：

1. 打开文件：`src/ai_trending/crew/report_writing/config/tasks.yaml`
2. 更新 `write_report_task` 的 description：

```yaml
write_report_task:
  description: >
    基于以下数据生成今日 AI 日报：
    
    【GitHub 热点数据】
    {github_data}
    
    【AI 新闻数据】
    {news_data}
    
    【趋势分析结果】
    {scoring_result}
    
    当前日期：{current_date}
    
    **三轮工作流要求**：
    1. **信息提取阶段**：从原始数据中提取核心信息，结构化但不僵化
    2. **判断生成阶段**：回答关键问题：为什么值得关注？实质是什么？对谁有影响？
    3. **文案润色阶段**：将判断转化为叙事性文字
    
    **输出要求**：
    1. 严格按照规定的四段式结构输出（标题导语 → GitHub 热点 → AI 新闻 → 趋势洞察）
    2. 总字数控制在 700-1500 字
    3. 禁止使用：重磅、震撼、颠覆、革命性、划时代、感叹号
    4. 每个 GitHub 项目包含「相当于……的……版」句式
    5. 每条新闻包含「So What 分析」
    6. 趋势洞察每条不超过 60 字
    7. 输出纯 Markdown 格式，不要包含任何解释性文字
  expected_output: >
    一份完整的 AI 日报 Markdown 文本，包含四个 Section：
    标题导语、GitHub 热点项目（3-5个）、AI 热点新闻（6-8条）、趋势洞察（3-5条）。
    总字数 700-1500 字，无禁用词，无感叹号。
  agent: report_writer
```

**验证方法**：
```python
# 验证 Task 配置
from ai_trending.crew.report_writing.config.tasks import tasks_config
task_desc = tasks_config["write_report_task"]["description"]
assert "三轮工作流" in task_desc
assert "So What 分析" in task_desc
assert "相当于" in task_desc
```

### 2.3 第三步：增强格式校验（crew.py）

**目标**：添加 18 项新校验规则

**操作步骤**：

1. 打开文件：`src/ai_trending/crew/report_writing/crew.py`
2. 找到 `_validate_report` 函数
3. 添加新校验规则：

```python
def _validate_report(content: str) -> list[str]:
    """校验日报内容是否符合新标准。"""
    issues = []
    
    # 1. 结构检查
    required_sections = ["## 🔥 GitHub 热点项目", "## 📰 AI 热点新闻", "## 🧭 趋势洞察"]
    for section in required_sections:
        if section not in content:
            issues.append(f"缺少必要 Section：{section}")
    
    # 2. 字数检查
    char_count = len(content.replace(" ", "").replace("\n", ""))
    if char_count < 700:
        issues.append(f"内容过短：{char_count} 字（最少 700 字）")
    if char_count > 1500:
        issues.append(f"内容过长：{char_count} 字（最多 1500 字）")
    
    # 3. 禁用词检查
    banned_words = ["重磅", "震撼", "颠覆", "革命性", "划时代", "里程碑", "历史性", "！"]
    for word in banned_words:
        if word in content:
            issues.append(f"包含禁用词：「{word}」")
    
    # 4. 叙事风格检查
    if "相当于" not in content:
        issues.append("缺少叙事性表达：应包含「相当于……的……版」句式")
    
    if "So What" not in content:
        issues.append("缺少深度分析：应包含「So What 分析」")
    
    # 5. 信号强度标签检查
    signal_strength_patterns = ["🔴 重大变化日", "🟡 常规更新日", "🟢 平静日"]
    if not any(pattern in content for pattern in signal_strength_patterns):
        issues.append("缺少信号强度标签：应包含 🔴/🟡/🟢 标签")
    
    # 6. 可信度标签检查
    credibility_patterns = ["🟢 一手信源", "🟡 社区讨论", "🔴 待验证"]
    if not any(pattern in content for pattern in credibility_patterns):
        issues.append("缺少可信度标签：应包含 🟢/🟡/🔴 标签")
    
    # 7. emoji 密度检查
    emoji_count = sum(1 for char in content if char in "🔴🟡🟢🔥📰🧭💡📊📋💬")
    if emoji_count > 20:
        issues.append(f"emoji 使用过密：{emoji_count} 个（建议不超过 20 个）")
    
    return issues
```

**验证方法**：
```python
# 测试校验函数
from ai_trending.crew.report_writing.crew import _validate_report

# 测试好报告
good_report = "# 🤖 AI 日报 · 2026-03-25\n**[今日信号强度]** 🟡 常规更新日\n..."
issues = _validate_report(good_report)
assert len(issues) == 0

# 测试坏报告
bad_report = "# 🤖 AI 日报 · 2026-03-25\n重磅！革命性突破！\n..."
issues = _validate_report(bad_report)
assert len(issues) > 0
```

### 2.4 第四步：优化评分 Prompt（nodes.py）

**目标**：为叙事性日报提供判断依据

**操作步骤**：

1. 打开文件：`src/ai_trending/nodes.py`
2. 找到评分相关的 Prompt 定义
3. 更新 Prompt，加入叙事性判断标准：

```python
# 在评分节点中添加叙事性判断字段
SCORING_PROMPT_TEMPLATE = """...

**新增字段（为叙事性日报提供素材）**
"story_hook": "故事开篇钩子，不超过 20 字，制造信息差或悬念，如「一个月前还没人听过这个名字，现在它是...」",
"technical_detail": "具体技术细节，不超过 25 字，支撑判断，如「针对 Metal 后端重写了推理内核，实测吞吐量高出 40%」",
"target_audience": "谁应该关注，不超过 15 字，明确指向，如「在 Mac 上做本地推理的开发者」",
"scenario_description": "场景化描述，用「相当于……的……版」句式，不超过 25 字，如「相当于苹果硅设备的本地化 LLM 推理服务优化版」"

...
"""
```

**验证方法**：
```python
# 验证 Prompt 包含新字段
assert "story_hook" in SCORING_PROMPT_TEMPLATE
assert "technical_detail" in SCORING_PROMPT_TEMPLATE
assert "target_audience" in SCORING_PROMPT_TEMPLATE
assert "scenario_description" in SCORING_PROMPT_TEMPLATE
```

## 三、测试验证

### 3.1 运行单元测试

```bash
# 运行优化后的测试
cd /Users/avinzhang/git/ai_trending
.venv/bin/python -m pytest tests/test_optimized_report_generation.py -v
```

**预期输出**：所有测试通过

### 3.2 生成测试日报

```bash
# 运行一次完整的日报生成流程
.venv/bin/python -c "
from ai_trending.graph import build_graph
graph = build_graph()
result = graph.invoke({'query': 'AI Agent', 'current_date': '2026-03-25'})
print('日报生成成功，长度:', len(result.get('report_content', '')))
print('错误列表:', result.get('errors', []))
"
```

**验证标准**：
- 日报长度：700-1500 字
- 无格式校验错误
- 包含叙事性元素
- 无禁用词

### 3.3 手动检查日报质量

检查生成的日报是否包含以下元素：

- [ ] **叙事性开篇**：每个项目有「相当于……的……版」句式
- [ ] **So What 分析**：每条新闻有深度分析
- [ ] **信号强度标签**：🔴/🟡/🟢 标签正确使用
- [ ] **可信度标签**：🟢/🟡/🔴 标签正确使用
- [ ] **禁用词检查**：无「重磅」「震撼」等词
- [ ] **结构完整性**：所有必要 Section 都存在

## 四、常见问题解决

### 4.1 日报过于模板化

**问题**：日报仍然像填表格，缺乏叙事性

**解决方案**：
1. 检查 Agent backstory 是否强调叙事性表达
2. 验证 Task description 是否包含三轮工作流要求
3. 确保评分 Prompt 提供足够的叙事素材

### 4.2 So What 分析过于空泛

**问题**：So What 分析都是「这是一个重要更新」等空话

**解决方案**：
1. 在评分 Prompt 中提供具体分析框架
2. 在格式校验中加强 So What 分析的质量检查
3. 提供更多具体示例

### 4.3 格式校验过于严格

**问题**：格式校验导致日报无法生成

**解决方案**：
1. 适当放宽非核心校验规则
2. 增加校验规则的容错性
3. 提供降级生成机制

### 4.4 日报长度超出预期

**问题**：日报过长，影响阅读体验

**解决方案**：
1. 调整字数限制范围
2. 优化内容密度，减少冗余信息
3. 提供摘要版本选项

## 五、性能优化建议

### 5.1 缓存机制

对于频繁访问的数据，添加缓存：

```python
from functools import lru_cache

@lru_cache(maxsize=100)
def get_cached_github_data(date: str) -> list:
    """缓存 GitHub 数据，避免重复请求。"""
    # 实现缓存逻辑
    pass
```

### 5.2 异步处理

对于耗时操作，使用异步：

```python
import asyncio

async def generate_report_async():
    """异步生成日报。"""
    tasks = [
        asyncio.create_task(fetch_github_data()),
        asyncio.create_task(fetch_news_data()),
        asyncio.create_task(score_trends())
    ]
    results = await asyncio.gather(*tasks)
    return results
```

### 5.3 增量更新

对于历史数据，支持增量更新：

```python
def generate_incremental_report(last_date: str, current_date: str):
    """生成增量日报，只处理新数据。"""
    # 只处理 last_date 之后的新数据
    pass
```

## 六、监控与维护

### 6.1 质量监控

定期检查日报质量：

```python
def monitor_report_quality():
    """监控日报质量，发现问题及时告警。"""
    # 检查日报长度、格式、内容质量等
    pass
```

### 6.2 用户反馈收集

收集用户反馈，持续优化：

```python
def collect_user_feedback():
    """收集用户反馈，用于优化日报质量。"""
    # 实现反馈收集机制
    pass
```

### 6.3 定期优化

定期评估和优化：

- 每月评估日报质量
- 根据用户反馈调整 Prompt
- 更新禁用词列表
- 优化校验规则

## 七、总结

通过以上步骤，您可以将 AI 日报从「信息搬运」模式成功优化为「信息判断」模式。关键成功因素包括：

1. **三轮工作流设计**：信息提取 → 判断生成 → 文案润色
2. **叙事性表达**：讲故事而非填表格
3. **深度分析**：So What 分析、因果解释
4. **质量保障**：18 项格式校验规则
5. **持续优化**：基于反馈的持续改进

实施完成后，您的 AI 日报将更好地服务于忙碌的技术从业者，让他们真正「带走判断」而非仅仅「获取信息」。