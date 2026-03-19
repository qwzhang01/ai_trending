# ============================================
# AI Trending — 生产级 Dockerfile
# ============================================
# 多阶段构建 + 非 root 用户 + 最小镜像

# ---- 阶段 1: 构建依赖 ----
FROM python:3.12-slim AS builder

# 安装 uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# 先复制依赖文件（利用 Docker 层缓存）
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# 再复制源代码
COPY . .
RUN uv sync --frozen --no-dev

# ---- 阶段 2: 运行环境 ----
FROM python:3.12-slim AS runtime

# 安全：创建非 root 用户
RUN groupadd -r appuser && useradd -r -g appuser -d /app -s /sbin/nologin appuser

WORKDIR /app

# 从构建阶段复制虚拟环境和源代码
COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/src /app/src
COPY --from=builder /app/pyproject.toml /app/
COPY --from=builder /app/run.py /app/

# 创建输出目录并设置权限
RUN mkdir -p /app/reports /app/output /app/logs \
    && chown -R appuser:appuser /app

# 环境变量
ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

USER appuser

# 健康检查：确认 LangGraph 图可以正常构建
HEALTHCHECK --interval=60s --timeout=10s --retries=3 \
    CMD python -c "from ai_trending.graph import build_graph; print('ok')" || exit 1

# 默认入口
ENTRYPOINT ["python", "run.py"]
