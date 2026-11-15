"""Lock-order regression test for sample cleanup.

A project that receives a real analysis immediately before the lock must be
kept. The lock statement must run before the existence check, in the same
transaction, so the check cannot miss an analysis that committed first.
"""

import importlib.util
from collections.abc import Callable, Generator
from contextlib import contextmanager
from pathlib import Path
from typing import cast
from uuid import UUID, uuid4

import psycopg

_SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "seed_sample_data.py"


class _Cursor:
    def __init__(self, rows: list[tuple[object, ...]], rowcount: int = 0) -> None:
        self._rows = rows
        self.rowcount = rowcount

    def fetchall(self) -> list[tuple[object, ...]]:
        return self._rows


class _Connection:
    def __init__(self, project_id: UUID) -> None:
        self._project_id = project_id
        self.statements: list[str] = []

    @contextmanager
    def transaction(self) -> Generator[None]:
        yield

    def execute(self, query: str, params: tuple[object, ...] | None = None) -> _Cursor:
        normalized = " ".join(query.lower().split())
        self.statements.append(normalized)
        if "select distinct organisation_id" in normalized:
            return _Cursor([("org_1",), ("org_2",), ("org_3",)])
        if "for update" in normalized:
            return _Cursor([(self._project_id,)])
        if "exists" in normalized:
            return _Cursor([(self._project_id, True)])
        if normalized.startswith("delete from public.analyses"):
            return _Cursor([], rowcount=0)
        if normalized.startswith("delete from public.projects"):
            return _Cursor([], rowcount=1)
        raise AssertionError(f"unexpected statement: {normalized}")


def _load_remove_samples() -> Callable[[psycopg.Connection[tuple[object, ...]]], int]:
    spec = importlib.util.spec_from_file_location("_seed_sample_data_lock", _SCRIPT)
    assert spec is not None
    loader = spec.loader
    assert loader is not None
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return cast(Callable[[psycopg.Connection[tuple[object, ...]]], int], module._remove_samples)


def test_project_with_a_real_analysis_committed_before_the_lock_is_kept() -> None:
    project_id = uuid4()
    connection = _Connection(project_id)
    remove_samples = _load_remove_samples()

    removed = remove_samples(cast("psycopg.Connection[tuple[object, ...]]", connection))

    assert removed == 0
    assert not any(
        statement.startswith("delete from public.projects") for statement in connection.statements
    )
    lock_index = next(
        index for index, statement in enumerate(connection.statements) if "for update" in statement
    )
    check_index = next(
        index for index, statement in enumerate(connection.statements) if "exists" in statement
    )
    assert lock_index < check_index
