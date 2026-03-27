#!/usr/bin/env python3
"""测试优化后的 AI 日报生成系统是否符合新标准。

测试重点：
1. 叙事性表达 vs 模板化填充
2. So What 分析深度
3. 三轮工作流执行效果
4. 格式校验规则有效性
"""

import json

import pytest

from ai_trending.crew.report_writing.crew import ReportWritingCrew, _validate_report


class TestOptimizedReportGeneration:
    """测试优化后的日报生成系统。"""

    def test_validate_report_structure(self):
        """测试格式校验函数是否能正确识别新结构要求。"""

        # 测试用例：符合新标准的日报
        good_report = """# 🤖 AI 日报 · 2026-03-25

**[今日信号强度]** 🟡 常规更新日

> **[今日一句话]** LLMOps 从可选变必选

---

## 今日头条

**omlx — 让 Mac 跑大模型终于不再是「能用就行」** ⭐ 6777（+1840）

一个月前还没人听过这个名字，现在它是 Apple Silicon 上跑 LLM 最快的开源方案。核心做法是针对 Metal 后端重写了推理内核，实测 Llama 3 70B 的吞吐量比 llama.cpp 高出 40%。增速是同赛道项目的 2 倍——端侧推理的需求显然被低估了。

**值得关注如果你**：在 Mac 上做本地推理、关注端侧部署成本、需要高性能推理框架。

---

## GitHub 热点项目

### 1. **[omlx](https://github.com/apple/omlx)** ⭐ 6777（+1840）

一个月前还没人听过这个名字，现在它是 Apple Silicon 上跑 LLM 最快的开源方案。针对 Metal 后端重写了推理内核，实测 Llama 3 70B 的吞吐量比 llama.cpp 高出 40%。增速是同赛道项目的 2 倍。

### 2. **[bisheng](https://github.com/dataelement/bisheng)** ⭐ 15432（+1200）

单日涨星 1200+，这不是个例。过去一个季度，提供全链路 LLM 开发管理能力的平台型项目整体增速明显快于单点工具。原因很直接：企业发现自己拼凑的 RAG + Agent + 监控工具链维护成本太高了。

---

## AI 热点新闻

**[🟢 一手信源]** **[大厂动态]** Palantir 进入铀浓缩领域 — Centrus Energy 宣布合作
> **[So What]** 值得注意的不是技术本身，而是信号：连核能这种强监管行业都开始买单了，工业 AI 的采购决策正在松动。
来源：Bloomberg | [[原文链接]](https://bloomberg.com/)

**[🟡 社区讨论]** **[开源生态]** Meta 开源 Code Llama 70B，支持 100K 上下文
> **[So What]** 真正的信号在于：大厂正在把最先进的模型开源，竞争焦点从模型能力转向应用生态。
来源：Hacker News | [[讨论]](https://news.ycombinator.com/)

---

## 趋势洞察

- **LLMOps 平台化**：过去一个季度，全链路 LLM 开发管理平台的整体增速明显快于单点工具。原因很直接：企业发现自己拼凑的 RAG + Agent + 监控工具链维护成本太高了。

- **端侧推理爆发**：Apple Silicon 上的推理框架增速是同赛道项目的 2 倍，端侧推理的需求被低估了。预计未来 3 个月会有更多针对特定硬件的优化方案出现。

---

## 本周行动建议

### 本周作业
**具体任务** 用 CLI-Anything 把你最常用的 3 个工具 Agent 化，并分享体验
**预期收获** 理解 Agent 化工具的实际效果和局限性
**时间投入** 预计 30 分钟，适合周末尝试
**时效理由** 下周有重要版本更新，现在体验可以对比效果

**[参与方式]** 欢迎在评论区分享你的测试结果。

---

*数据截至：2026-03-25 | 由 AI Agent 自动生成 | 数据来源：GitHub、Hacker News、Reddit 等公开渠道，仅供参考*
"""

        issues = _validate_report(good_report)
        assert len(issues) == 0, f"格式校验失败：{issues}"

    def test_validate_report_banned_words(self):
        """测试禁用词检测功能。"""

        # 包含禁用词的报告
        bad_report = """# 🤖 AI 日报 · 2026-03-25

**[今日信号强度]** 🔴 重大变化日

> **[今日一句话]** 重磅！LLMOps 革命性突破！

---

## 🔥 GitHub 热点项目

### 1. **[omlx](https://github.com/apple/omlx)** ⭐ 6777（+1840）

这是一个划时代的项目！强烈推荐大家必看！不容错过！

---

*数据截至：2026-03-25 | 由 AI Agent 自动生成 | 数据来源：GitHub、Hacker News、Reddit 等公开渠道，仅供参考*
"""

        issues = _validate_report(bad_report)

        # 检查是否检测到禁用词
        banned_word_issues = [issue for issue in issues if "禁用词" in issue]
        assert len(banned_word_issues) > 0, "应该检测到禁用词"

        # 检查具体禁用词
        assert any("重磅" in issue for issue in banned_word_issues)
        assert any("革命性" in issue for issue in banned_word_issues)
        assert any("划时代" in issue for issue in banned_word_issues)
        assert any("强烈推荐" in issue for issue in banned_word_issues)
        assert any("必看" in issue for issue in banned_word_issues)
        assert any("不容错过" in issue for issue in banned_word_issues)

    def test_narrative_structure_validation(self):
        """测试叙事性结构校验。"""

        # 缺少叙事元素的报告
        non_narrative_report = """# 🤖 AI 日报 · 2026-03-25

**[今日信号强度]** 🟢 平静日

> **[今日一句话]** 常规更新

---

## 🔥 GitHub 热点项目

### 1. **[omlx](https://github.com/apple/omlx)** ⭐ 6777

这是一个 AI 项目。它有很多星星。

---

## 📰 AI 热点新闻

**[🟡 社区讨论]** Meta 开源 Code Llama 70B
> **[So What]** 这是一个重要更新。

---

*数据截至：2026-03-25 | 由 AI Agent 自动生成 | 数据来源：GitHub、Hacker News、Reddit 等公开渠道，仅供参考*
"""

        issues = _validate_report(non_narrative_report)

        # 检查是否检测到叙事风格问题
        narrative_issues = [
            issue for issue in issues if "叙事" in issue or "相当于" in issue
        ]
        assert len(narrative_issues) > 0, "应该检测到叙事风格问题"

    def test_so_what_analysis_validation(self):
        """测试 So What 分析校验。"""

        # 缺少 So What 分析的报告
        no_so_what_report = """# 🤖 AI 日报 · 2026-03-25

**[今日信号强度]** 🟡 常规更新日

> **[今日一句话]** 常规更新

---

## 📰 AI 热点新闻

**[🟢 一手信源]** Palantir 进入铀浓缩领域
> 这是一个新闻。

---

*数据截至：2026-03-25 | 由 AI Agent 自动生成 | 数据来源：GitHub、Hacker News、Reddit 等公开渠道，仅供参考*
"""

        issues = _validate_report(no_so_what_report)

        # 检查是否检测到 So What 分析问题
        so_what_issues = [issue for issue in issues if "So What" in issue]
        assert len(so_what_issues) > 0, "应该检测到 So What 分析问题"

    def test_signal_strength_validation(self):
        """测试信号强度标签校验。"""

        # 使用无效信号强度的报告
        invalid_signal_report = """# 🤖 AI 日报 · 2026-03-25

**[今日信号强度]** 🔵 超级重要日

> **[今日一句话]** 常规更新

---

*数据截至：2026-03-25 | 由 AI Agent 自动生成 | 数据来源：GitHub、Hacker News、Reddit 等公开渠道，仅供参考*
"""

        issues = _validate_report(invalid_signal_report)

        # 检查是否检测到信号强度问题
        signal_issues = [issue for issue in issues if "信号强度" in issue]
        assert len(signal_issues) > 0, "应该检测到信号强度问题"

    def test_credibility_labels_validation(self):
        """测试可信度标签校验。"""

        # 使用无效可信度标签的报告
        invalid_credibility_report = """# 🤖 AI 日报 · 2026-03-25

**[今日信号强度]** 🟡 常规更新日

> **[今日一句话]** 常规更新

---

## 📰 AI 热点新闻

**[🔵 官方发布]** Meta 开源 Code Llama 70B
> **[So What]** 这是一个重要更新。

---

*数据截至：2026-03-25 | 由 AI Agent 自动生成 | 数据来源：GitHub、Hacker News、Reddit 等公开渠道，仅供参考*
"""

        issues = _validate_report(invalid_credibility_report)

        # 检查是否检测到可信度标签问题
        credibility_issues = [issue for issue in issues if "可信度" in issue]
        assert len(credibility_issues) > 0, "应该检测到可信度标签问题"

    def test_length_validation(self):
        """测试字数校验。"""

        # 过短的报告
        short_report = "# 🤖 AI 日报 · 2026-03-25\n\n**[今日信号强度]** 🟡 常规更新日\n\n> **[今日一句话]** 常规更新\n\n*数据截至：2026-03-25*"

        issues = _validate_report(short_report)

        # 检查是否检测到字数问题
        length_issues = [issue for issue in issues if "过短" in issue]
        assert len(length_issues) > 0, "应该检测到字数过短问题"

    def test_emoji_density_validation(self):
        """测试 emoji 密度校验。"""

        # emoji 过密的报告
        emoji_dense_report = """# 🤖 AI 日报 · 2026-03-25 🔥 📰 🧭 💡 📊 📋 💬 🔴 🟡 🟢 🔥 📰 🧭 💡 📊 📋 💬 🔴 🟡 🟢

**[今日信号强度]** 🟡 常规更新日

> **[今日一句话]** 常规更新

---

## 🔥 GitHub 热点项目

### 1. **[omlx](https://github.com/apple/omlx)** ⭐ 6777（+1840）

这是一个项目。🔥 📰 🧭 💡 📊 📋 💬 🔴 🟡 🟢

---

*数据截至：2026-03-25 | 由 AI Agent 自动生成 | 数据来源：GitHub、Hacker News、Reddit 等公开渠道，仅供参考*
"""

        issues = _validate_report(emoji_dense_report)

        # 检查是否检测到 emoji 密度问题
        emoji_issues = [
            issue for issue in issues if "emoji" in issue or "密度" in issue
        ]
        assert len(emoji_issues) > 0, "应该检测到 emoji 密度问题"

    @pytest.mark.skip(reason="需要真实 LLM 调用，仅在集成测试中运行")
    def test_full_report_generation(self):
        """测试完整的日报生成流程（集成测试）。"""

        # 模拟输入数据
        mock_github_data = """GitHub 热门 AI 项目：
1. omlx - Apple Silicon 上的 LLM 推理优化框架，⭐ 6777（+1840）
2. bisheng - 企业级 LLM 应用低代码平台，⭐ 15432（+1200）
"""

        mock_news_data = """AI 行业新闻：
1. Palantir 与 Centrus Energy 合作进入铀浓缩领域（Bloomberg）
2. Meta 开源 Code Llama 70B，支持 100K 上下文（Hacker News）
"""

        mock_scoring_result = json.dumps(
            {
                "scored_repos": [
                    {
                        "repo": "apple/omlx",
                        "name": "omlx",
                        "url": "https://github.com/apple/omlx",
                        "stars": 6777,
                        "language": "C++",
                        "is_ai": True,
                        "category": "推理框架",
                        "scores": {
                            "热度": 8,
                            "技术前沿性": 9,
                            "成长潜力": 8,
                            "综合": 8.3,
                        },
                        "one_line_reason": "Apple Silicon 上最快的 LLM 推理方案",
                        "story_hook": "一个月前还没人听过这个名字，现在它是 Apple Silicon 上跑 LLM 最快的开源方案",
                        "technical_detail": "针对 Metal 后端重写了推理内核，实测 Llama 3 70B 的吞吐量比 llama.cpp 高出 40%",
                        "target_audience": "在 Mac 上做本地推理的开发者",
                        "scenario_description": "相当于苹果硅设备的本地化 LLM 推理服务优化版",
                    }
                ],
                "scored_news": [
                    {
                        "title": "Palantir 进入铀浓缩领域 — Centrus Energy 宣布合作",
                        "url": "https://bloomberg.com/",
                        "source": "Bloomberg",
                        "category": "大厂动态",
                        "impact_score": 8,
                        "impact_reason": "工业 AI 采购决策正在松动",
                        "so_what_analysis": "值得注意的不是技术本身，而是信号：连核能这种强监管行业都开始买单了",
                        "credibility_label": "🟢 一手信源",
                        "time_window": "中期（3-12个月）",
                        "affected_audience": "技术决策者 / 投资人",
                    }
                ],
                "daily_summary": {
                    "top_trend": "LLMOps 从可选变必选",
                    "hot_directions": ["端侧推理", "平台化", "工具 Agent 化"],
                    "overall_sentiment": "积极",
                    "causal_explanation": "企业发现自己拼凑的 RAG + Agent + 监控工具链维护成本太高了，所以转向全链路平台",
                    "data_support": "过去一个季度，全链路 LLM 开发管理平台的整体增速明显快于单点工具",
                    "forward_looking": "预计未来 3 个月会有更多企业级 LLMOps 解决方案出现",
                },
            }
        )

        # 调用 ReportWritingCrew
        crew = ReportWritingCrew()
        result = crew.run(
            github_data=mock_github_data,
            news_data=mock_news_data,
            scoring_result=mock_scoring_result,
            current_date="2026-03-25",
        )

        # 验证输出
        assert result.content is not None
        assert len(result.content) > 800
        assert len(result.content) < 1600

        # 验证格式
        issues = _validate_report(result.content)
        assert len(issues) == 0, f"生成的日报格式校验失败：{issues}"

        # 验证关键元素
        assert "相当于" in result.content, "应该包含场景化描述"
        assert "So What" in result.content, "应该包含 So What 分析"
        assert "一个月前" in result.content, "应该包含叙事性开篇"
        assert "🟢 一手信源" in result.content, "应该包含可信度标签"
        assert "（+1840）" in result.content, "应该包含星数增长信息"


if __name__ == "__main__":
    # 运行测试
    pytest.main([__file__, "-v"])
