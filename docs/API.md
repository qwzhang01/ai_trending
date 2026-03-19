# API 文档

## 概述

AI Trending 提供完整的 API 接口，支持程序化调用和集成。

## 核心接口

### 运行主流程

```python
from ai_trending.main import run

# 基本运行
result = run()

# 带参数运行
result = run(
    date="2025-03-19",
    author="AI Bot",
    dry_run=False,
    verbose=True
)
```

### 状态图接口

```python
from ai_trending.graph import get_graph

# 获取状态图
graph = get_graph()

# 执行状态机
initial_state = {
    "current_date": "2025-03-19",
    "author_name": "AI Bot",
    "github_data": "",
    "news_data": "",
    "scoring_result": "",
    "report_content": "",
    "publish_results": [],
    "token_usage": {},
    "errors": [],
}

final_state = graph.invoke(initial_state)
```

## 工具接口

### GitHub 趋势工具

```python
from ai_trending.tools.github_trending_tool import GitHubTrendingTool

tool = GitHubTrendingTool()

# 搜索热门 AI 项目
result = tool._run(
    query="AI",
    top_n=5,
    exclude_forks=True,
    min_stars=100
)
```

**参数说明：**

- `query` (str): 搜索关键词，默认 "AI"
- `top_n` (int): 返回数量，默认 5
- `exclude_forks` (bool): 是否排除 fork 仓库，默认 True
- `min_stars` (int): 最小星数过滤，默认 100

### AI 新闻工具

```python
from ai_trending.tools.ai_news_tool import AINewsTool

tool = AINewsTool()

# 多源新闻采集
result = tool._run(
    sources=["hackernews", "reddit", "newsdata"],
    max_items=10,
    keywords=["AI", "machine learning", "deep learning"]
)
```

**参数说明：**

- `sources` (list): 新闻源列表，支持 "hackernews", "reddit", "newsdata"
- `max_items` (int): 最大新闻数量，默认 10
- `keywords` (list): 关键词过滤，默认 AI 相关关键词

### 去重缓存

```python
from ai_trending.tools.dedup_cache import DedupCache

cache = DedupCache()

# 检查是否已处理
if cache.is_seen("github:owner/repo"):
    print("已处理过该仓库")

# 标记为已处理
cache.mark_seen("github:owner/repo")

# 清理过期缓存
cache.cleanup()
```

## 配置接口

### 配置管理

```python
from ai_trending.config import load_config, validate_config

# 加载配置
config = load_config()

# 验证配置
validate_config(config)

# 获取特定配置项
model = config.get("MODEL", "openai/gpt-4o")
api_key = config.get("OPENAI_API_KEY")
```

### 环境变量覆盖

```python
import os
from ai_trending.config import load_config

# 临时覆盖环境变量
os.environ["MODEL"] = "anthropic/claude-sonnet-4-20250514"
os.environ["ANTHROPIC_API_KEY"] = "sk-ant-xxx"

config = load_config()
```

## LLM 客户端

### 基础使用

```python
from ai_trending.llm_client import LLMClient

client = LLMClient()

# 聊天补全
response = client.chat_completion(
    messages=[
        {"role": "system", "content": "你是一个AI助手"},
        {"role": "user", "content": "你好"}
    ],
    model="openai/gpt-4o",
    temperature=0.1
)

# 结构化输出
response = client.chat_completion(
    messages=[{"role": "user", "content": "列出5个AI趋势"}],
    model="openai/gpt-4o",
    response_format={"type": "json_object"}
)
```

### 分级模型策略

```python
# 使用轻量模型（数据采集）
light_response = client.chat_completion(
    messages=[{"role": "user", "content": "提取关键信息"}],
    model="openai/gpt-4o-mini"
)

# 使用高质量模型（写作评分）
quality_response = client.chat_completion(
    messages=[{"role": "user", "content": "写一篇高质量报告"}],
    model="openai/gpt-4o"
)
```

## 指标监控

### 运行指标

```python
from ai_trending.metrics import RunMetrics

# 创建指标实例
metrics = RunMetrics(run_date="2025-03-19")

# 开始计时
metrics.start()

# 记录阶段
metrics.stage_start("GitHub采集")
# ... 执行代码
metrics.stage_end("GitHub采集")

# 记录 Token 使用
metrics.token_usage.update({
    "prompt_tokens": 1000,
    "completion_tokens": 500,
    "total_tokens": 1500
})

# 完成运行
metrics.finish(status="success")

# 保存指标
metrics.save()
```

### 指标查询

```python
from ai_trending.metrics import load_metrics

# 加载历史指标
metrics = load_metrics("2025-03-19")

# 获取统计信息
print(f"运行时间: {metrics.duration:.2f}秒")
print(f"Token 用量: {metrics.token_usage.get('total_tokens', 0)}")
print(f"预估成本: ${metrics.estimated_cost:.4f}")
```

## 错误处理

### 重试机制

```python
from ai_trending.retry import retry_with_backoff

@retry_with_backoff(max_retries=3, backoff_factor=1.5)
def api_call():
    # API 调用代码
    pass
```

### 异常处理

```python
try:
    result = run()
except KeyboardInterrupt:
    print("用户中断执行")
except Exception as e:
    print(f"运行失败: {e}")
    # 发送错误通知
    metrics.send_webhook()
```

## Webhook 集成

### 通知配置

```python
# 企业微信机器人
os.environ["WEBHOOK_URL"] = "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=xxx"

# 飞书机器人
os.environ["WEBHOOK_URL"] = "https://open.feishu.cn/open-apis/bot/v2/hook/xxx"

# 成功时也发通知
os.environ["WEBHOOK_ON_SUCCESS"] = "true"
```

## 命令行接口

### 直接运行

```bash
# 基本运行
python run.py

# 指定日期
python run.py --date 2025-03-19

# 只校验配置
python run.py --dry-run

# 详细日志
python run.py --verbose
```

### 通过 uv 运行

```bash
# 使用 uv 运行
uv run ai_trending

# 带参数运行
uv run ai_trending --date 2025-03-19 --verbose
```

## 集成示例

### Flask Web 服务

```python
from flask import Flask, request
from ai_trending.main import run

app = Flask(__name__)

@app.route('/run', methods=['POST'])
def run_trending():
    data = request.json
    result = run(
        date=data.get('date'),
        author=data.get('author', 'API User'),
        dry_run=data.get('dry_run', False)
    )
    return {'status': 'success', 'result': result}

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
```

### 定时任务

```python
import schedule
import time
from ai_trending.main import run

def daily_job():
    print("开始执行每日AI趋势分析...")
    run()
    print("任务完成")

# 每天上午8点执行
schedule.every().day.at("08:00").do(daily_job)

while True:
    schedule.run_pending()
    time.sleep(60)
```