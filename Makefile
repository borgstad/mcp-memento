.PHONY: install test smoke lock

install:
	uv sync

lock:
	uv lock

test:
	uv run pytest tests/

smoke:
	uv run pytest tests/smoke/ -v
