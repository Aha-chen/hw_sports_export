FROM ghcr.io/astral-sh/uv:0.11.32 AS uv
FROM python:3.11-slim

WORKDIR /app

# 使用 lock file 安装确定版本；运行镜像不包含测试和审计工具。
COPY --from=uv /uv /uvx /bin/
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:$PATH"
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project

# 依赖层完成后再复制源码，减少普通代码修改造成的重复安装。
COPY . .

RUN addgroup --system app && adduser --system --ingroup app app \
    && mkdir -p /app/temp \
    && chown -R app:app /app

USER app

EXPOSE 8000

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
