## Why

当前日报中新闻和 GitHub 项目是两条完全独立的信息流，读者需要自己在脑中建立关联。当同一个技术方向（如 MCP）同时出现在 GitHub Trending 和 HN 热帖时，这种"共振"本身就是最强的趋势信号，但系统目前无法识别和放大它。此外，所有项目都以相同方式呈现，读者无法快速判断一个项目是刚刚爆发的新星还是持续增长的稳健项目，错失了差异化的关注价值。

## What Changes

- **新增新闻×项目共振检测**：在编辑策划层检测同一技术关键词同时出现在新闻和 GitHub Trending 中的情况，生成"共振信号"标注，写作层在趋势洞察中优先呈现
- **新增项目生命周期标签**：根据项目年龄、7日星数增长率、绝对星数等维度，为每个项目自动打上生命周期标签（🌱新生 / 🚀爆发 / 📈稳健 / ⚠️异常），在日报中随项目名展示
- **编辑策划层输出扩展**：`EditorialPlan` 模型新增 `resonance_signals` 字段，记录检测到的共振信号列表
- **写作简报扩展**：`RepoBrief` 模型新增 `lifecycle_tag` 字段，传递到写作层

## Capabilities

### New Capabilities

- `news-repo-resonance`: 检测新闻与 GitHub 项目的关键词共振，生成共振信号列表，在趋势洞察中优先呈现
- `repo-lifecycle-tagging`: 根据项目年龄、增长率、星数等维度自动计算并标注项目生命周期阶段

### Modified Capabilities

- `trend-scoring-narrative`: 评分层输出需新增 `lifecycle_tag` 字段，供编辑策划层和写作层使用

## Impact

- `src/ai_trending/crew/editorial_planning/models.py`：`EditorialPlan` 新增 `resonance_signals` 字段
- `src/ai_trending/crew/editorial_planning/config/tasks.yaml`：编辑策划任务新增共振检测步骤
- `src/ai_trending/crew/trend_scoring/models.py`：`ScoredRepo` 新增 `lifecycle_tag` 字段
- `src/ai_trending/crew/trend_scoring/config/tasks.yaml`：评分任务新增生命周期标签计算规则
- `src/ai_trending/crew/report_writing/models.py`：`RepoBrief` 新增 `lifecycle_tag` 字段
- `src/ai_trending/crew/report_writing/config/tasks.yaml`：写作任务新增共振信号和生命周期标签的使用规范
- `src/ai_trending/nodes.py`：`_build_writing_brief` 函数传递 `lifecycle_tag` 字段
