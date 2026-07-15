# US Importer Hunter — Backend

FastAPI backend. See the [repo README](../../README.md) for setup and the
[architecture doc](../../docs/architecture.md) for layering rules.

```bash
uv sync                                  # install dependencies
uv run uvicorn app.main:app --reload     # run with hot reload
uv run pytest                            # tests
uv run ruff check . && uv run mypy app   # lint + type check
```
