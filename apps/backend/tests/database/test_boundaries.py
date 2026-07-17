"""Persistence boundary rules: repositories must not leak ORM models."""

import inspect
import typing

import pytest

from app.core.config import Settings
from app.database.base import Base
from app.database.repositories import (
    SqlAlchemyCompanyRepository,
    SqlAlchemyOpportunityRepository,
    SqlAlchemyOutreachRepository,
    SqlAlchemyTaskRepository,
)
from app.database.session import create_engine


def _flatten(hint: object) -> list[object]:
    found = [hint]
    for arg in typing.get_args(hint):
        found.extend(_flatten(arg))
    return found


@pytest.mark.parametrize(
    "repo_cls",
    [
        SqlAlchemyCompanyRepository,
        SqlAlchemyOpportunityRepository,
        SqlAlchemyOutreachRepository,
        SqlAlchemyTaskRepository,
    ],
)
def test_repository_signatures_never_mention_orm_models(repo_cls: type) -> None:
    for name, method in inspect.getmembers(repo_cls, inspect.isfunction):
        if name.startswith("_"):
            continue
        for hint in typing.get_type_hints(method).values():
            for candidate in _flatten(hint):
                assert not (isinstance(candidate, type) and issubclass(candidate, Base)), (
                    f"{repo_cls.__name__}.{name} leaks ORM model {candidate!r}"
                )


async def test_database_engine_does_not_echo_bound_values() -> None:
    settings = Settings(_env_file=None, debug=True)
    engine = create_engine(settings.database_url)
    try:
        assert engine.echo is False
    finally:
        await engine.dispose()
