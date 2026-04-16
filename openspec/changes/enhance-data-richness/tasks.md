## 1. 修复 formatter.py — 补充 README 和增长数据输出

- [ ] 1.1 在 `format_text_output` 函数中，为每个 repo 追加 `README摘要` 字段输出（截断到 300 字，空时输出占位符 `（暂无）`）
- [ ] 1.2 在 `format_text_output` 函数中，为每个 repo 追加 `7日增长` 字段输出（非 None 时输出 `+{N}`，None 时输出 `（暂无历史数据）`）
- [ ] 1.3 运行 `ruff format` 格式化 `formatter.py`

## 2. 更新评分层数据模型 — ScoredRepo 新增字段

- [ ] 2.1 在 `crew/trend_scoring/models.py` 的 `ScoredRepo` 模型中新增 `readme_summary: str = ""` 字段（可选，向后兼容）
- [ ] 2.2 在 `crew/trend_scoring/models.py` 的 `ScoredRepo` 模型中新增 `stars_growth_7d: int | None = None` 字段（可选，向后兼容）
- [ ] 2.3 运行 `ruff format` 格式化 `models.py`

## 3. 更新评分层 Prompt — 强化叙事字段生成规则

- [ ] 3.1 在 `crew/trend_scoring/config/tasks.yaml` 的 `scored_repos` 输出要求中，新增 `readme_summary` 字段说明：从输入 `github_data` 中读取对应项目的 README 摘要原样填入，空时填 `""`
- [ ] 3.2 在 `crew/trend_scoring/config/tasks.yaml` 的 `scored_repos` 输出要求中，新增 `stars_growth_7d` 字段说明：从输入 `github_data` 中读取 `7日增长` 数值原样填入，无数据时填 `null`
- [ ] 3.3 在 `crew/trend_scoring/config/tasks.yaml` 的 `story_hook` 生成规则中，新增约束：当 `README摘要` 非空时，必须从中引用至少一个具体技术名词、数字或对比对象；禁止使用"和X不同，Y支持..."等纯推断式模板句
- [ ] 3.4 在 `crew/trend_scoring/config/tasks.yaml` 的 `technical_detail` 生成规则中，新增约束：必须包含从 README 或描述中提取的具体技术细节，禁止使用"支持多种功能"、"采用先进技术"等无实质内容的描述

## 4. 修复写作简报构建 — _build_writing_brief 读取新字段

- [ ] 4.1 在 `nodes.py` 的 `_build_writing_brief` 函数中，从 `scored_repos` JSON 条目读取 `readme_summary` 字段，填入 `RepoBrief.readme_summary`（缺失时默认空字符串）
- [ ] 4.2 在 `nodes.py` 的 `_build_writing_brief` 函数中，从 `scored_repos` JSON 条目读取 `stars_growth_7d` 字段，填入 `RepoBrief.stars_growth_7d`（缺失时默认 None）
- [ ] 4.3 运行 `ruff format` 格式化 `nodes.py`

## 5. 验证数据流转

- [ ] 5.1 检查 `output/star_snapshots/` 目录，确认有近 7 天的快照文件（若无，说明 `_track_star_growth` 未正常运行，需排查）
- [ ] 5.2 在本地运行一次完整流水线（或单独运行 `score_trends_node`），检查 `scoring_result` JSON 中 `scored_repos[0].readme_summary` 是否非空
- [ ] 5.3 检查生成的日报，确认头条段落中包含来自 README 的真实技术细节（非模板推断句），且星数后有 `（+N）` 增长标注
