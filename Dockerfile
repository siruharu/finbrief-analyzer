# syntax=docker/dockerfile:1
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder
WORKDIR /app
# 의존성만 먼저 — 소스가 바뀌어도 이 레이어는 캐시된다
COPY pyproject.toml uv.lock* ./
RUN uv sync --frozen --no-install-project --no-dev || uv sync --no-install-project --no-dev
COPY src ./src
RUN uv sync --no-dev

FROM python:3.12-slim-bookworm
WORKDIR /app
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1
RUN useradd -m -u 10001 app
COPY --from=builder --chown=app:app /app /app
USER app
EXPOSE 8000
CMD ["python", "-m", "finbrief_analyzer.main"]
