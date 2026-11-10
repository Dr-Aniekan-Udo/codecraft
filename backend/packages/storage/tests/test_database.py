import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import ClassVar

import pytest
from codecraft_storage.database import Database
from psycopg import OperationalError


class RecordingPool:
    instances: ClassVar[list[RecordingPool]] = []

    @staticmethod
    async def check_connection(connection: object) -> None:
        return None

    def __init__(
        self,
        connection_string: str,
        *,
        kwargs: dict[str, object],
        min_size: int,
        max_size: int,
        max_idle: float,
        max_lifetime: float,
        check: object,
        open: bool,
    ) -> None:
        self.connection_string = connection_string
        self.kwargs = kwargs
        self.min_size = min_size
        self.max_size = max_size
        self.max_idle = max_idle
        self.max_lifetime = max_lifetime
        self.check = check
        self.open = open
        RecordingPool.instances.append(self)


def test_pool_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    RecordingPool.instances.clear()
    monkeypatch.setattr("codecraft_storage.database.AsyncConnectionPool", RecordingPool)

    Database("postgresql://api@example/db", "postgresql://sync@example/db")

    assert len(RecordingPool.instances) == 2
    for pool in RecordingPool.instances:
        assert pool.kwargs == {"prepare_threshold": None}
        assert pool.min_size == 1
        assert pool.max_size == 4
        assert pool.max_idle == 30.0
        assert pool.max_lifetime == 300.0
        assert pool.check is RecordingPool.check_connection
        assert pool.open is False


class FakeConnection:
    def __init__(self, *, closed: bool) -> None:
        self.closed = closed
        self.statements: list[tuple[str, tuple[object, ...] | None]] = []

    @asynccontextmanager
    async def transaction(self) -> AsyncGenerator[None]:
        yield

    async def execute(self, query: str, params: tuple[object, ...] | None = None) -> None:
        if self.closed:
            raise OperationalError("server closed the connection unexpectedly")
        self.statements.append((query, params))


class RetryPool:
    instances: ClassVar[list[RetryPool]] = []

    @staticmethod
    async def check_connection(connection: object) -> None:
        return None

    def __init__(self, connection_string: str, **_: object) -> None:
        self.connection_calls = 0
        self.dead = FakeConnection(closed=True)
        self.good = FakeConnection(closed=False)
        self.connections = [self.dead, self.good] if "sync" in connection_string else []
        RetryPool.instances.append(self)

    @asynccontextmanager
    async def connection(self) -> AsyncGenerator[FakeConnection]:
        self.connection_calls += 1
        connection = self.connections.pop(0)
        yield connection


@pytest.mark.parametrize(
    ("method_name", "statement"),
    [
        ("upsert_membership", "insert into public.membership"),
        ("delete_membership", "delete from public.membership"),
    ],
)
def test_membership_write_retries_closed_connection(
    monkeypatch: pytest.MonkeyPatch,
    method_name: str,
    statement: str,
) -> None:
    RetryPool.instances.clear()
    monkeypatch.setattr("codecraft_storage.database.AsyncConnectionPool", RetryPool)
    database = Database("postgresql://api@example/db", "postgresql://sync@example/db")

    async def call() -> None:
        if method_name == "upsert_membership":
            await database.upsert_membership("user_1", "org_1")
        else:
            await database.delete_membership("user_1", "org_1")

    asyncio.run(call())

    sync_pool = RetryPool.instances[1]
    assert sync_pool.connection_calls == 2
    assert len(sync_pool.good.statements) == 1
    assert statement in sync_pool.good.statements[0][0]
