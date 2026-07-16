"""The domain layer must stay framework-free.

Statically scans every module under app/domain for forbidden imports —
if this test fails, business rules grew an infrastructure dependency.
"""

import ast
from pathlib import Path

import app.domain

DOMAIN_ROOT = Path(app.domain.__file__).parent

FORBIDDEN_PREFIXES = (
    "fastapi",
    "sqlalchemy",
    "redis",
    "celery",
    "openai",
    "anthropic",
    "httpx",
    "aiohttp",
    "requests",
    "pydantic",
    "app.api",
    "app.core",
    "app.database",
    "app.providers",
    "app.services",
    "app.tools",
    "app.tasks",
    "app.workflows",
    "app.memory",
    "app.events",
    "app.observability",
)


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


def test_domain_has_no_infrastructure_imports() -> None:
    violations: list[str] = []
    for path in sorted(DOMAIN_ROOT.rglob("*.py")):
        for module in _imported_modules(path):
            if module.startswith(FORBIDDEN_PREFIXES):
                violations.append(f"{path.relative_to(DOMAIN_ROOT)} imports {module}")
    assert not violations, "domain layer must stay framework-free:\n" + "\n".join(violations)
