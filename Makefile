.PHONY: install dev run test lint fmt typecheck check clean docker

install:          ## 의존성 설치 (uv.lock 생성)
	uv sync

dev: install      ## 개발 서버 (자동 리로드)
	uv run uvicorn finbrief_analyzer.main:app --reload --port 8000

run:
	uv run python -m finbrief_analyzer.main

test:
	uv run pytest

lint:
	uv run ruff check .

fmt:
	uv run ruff format .
	uv run ruff check --fix .

typecheck:
	uv run mypy

check: lint typecheck test   ## 커밋 전 필수

docker:
	docker build -t finbrief-analyzer:local .

clean:
	rm -rf .pytest_cache .ruff_cache .mypy_cache .coverage dist build

# 인프라 타깃 (up/down/psql/배포) — deploy/README.md
-include Makefile.infra
