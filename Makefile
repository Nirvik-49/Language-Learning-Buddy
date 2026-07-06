# Makefile for Language Learning Buddy

.PHONY: install playground run test clean

install:
	uv sync

playground:
	uv run adk web app --host 127.0.0.1 --port 18081 --reload_agents

run:
	uv run python app/agent_runtime_app.py

test:
	uv run pytest tests/unit tests/integration

clean:
	rm -rf .venv __pycache__ .adk .pytest_cache .ruff_cache build dist
