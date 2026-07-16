"""Cross-layer and cross-context import boundaries (Sprint 2 L8).

Static AST scans — if one of these fails, a boundary from ADR-0015/0017/
0020 was crossed in code.
"""

import ast
from pathlib import Path

import pytest

import app

APP_ROOT = Path(app.__file__).parent


def _imports_of(root: Path) -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    for path in sorted(root.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                found.extend((str(path.relative_to(root)), alias.name) for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                found.append((str(path.relative_to(root)), node.module))
    return found


def _assert_no_imports(root: Path, forbidden: tuple[str, ...], rule: str) -> None:
    violations = [
        f"{file} imports {module}"
        for file, module in _imports_of(root)
        if module.startswith(forbidden)
    ]
    assert not violations, f"{rule}:\n" + "\n".join(violations)


@pytest.mark.parametrize(
    ("package", "forbidden", "rule"),
    [
        (
            "domain/company",
            ("app.domain.opportunity", "app.domain.outreach", "app.domain.task"),
            "Company domain must not know other aggregates",
        ),
        (
            "domain/discovery",
            ("app.domain.company", "app.domain.opportunity", "app.domain.outreach"),
            "Discovery must not depend on Company or Opportunity",
        ),
        (
            "domain/opportunity",
            ("app.domain.company", "app.domain.outreach", "app.domain.discovery"),
            "Opportunity references companies by id only",
        ),
        (
            "domain/contact",
            ("app.domain.opportunity", "app.domain.task", "app.domain.discovery"),
            "Contact references companies by id only and never judges opportunities",
        ),
        (
            "workflows",
            ("sqlalchemy", "app.database"),
            "Workflows must not touch SQLAlchemy or ORM models",
        ),
        (
            "services/contact",
            ("sqlalchemy", "app.database", "httpx", "openai"),
            "Contact services must not access the database or network",
        ),
        (
            "services/scoring",
            ("sqlalchemy", "app.database", "httpx", "openai"),
            "Scoring services must not access the database or network",
        ),
        (
            "database",
            ("app.services", "app.workflows", "app.agents"),
            "Persistence must not contain business/scoring logic",
        ),
    ],
)
def test_boundary(package: str, forbidden: tuple[str, ...], rule: str) -> None:
    _assert_no_imports(APP_ROOT / package, forbidden, rule)
