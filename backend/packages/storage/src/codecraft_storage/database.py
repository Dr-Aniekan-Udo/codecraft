"""The only module allowed to open database connections.

Row-level security depends on every request running with the verified person's
claims. Keeping the driver and the connection pools here means no other module
can accidentally open a connection that skips those claims.
"""

import json
from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from psycopg import AsyncConnection, OperationalError
from psycopg_pool import AsyncConnectionPool

# Supabase's transaction pooler does not support named prepared statements, so
# every pooled connection disables psycopg's prepared-statement threshold.
_CONNECTION_KWARGS: dict[str, object] = {"prepare_threshold": None}

_CLAIMS_ROLE = "authenticated"

# Supabase publishes no Supavisor idle or lifetime timeout. These values are
# deliberately shorter than the common hosted and OSS defaults so the pool
# recycles connections before an idle server socket can be closed underneath it.
_POOL_MIN_SIZE = 1
_POOL_MAX_SIZE = 4
_POOL_MAX_IDLE_SECONDS = 30.0
_POOL_MAX_LIFETIME_SECONDS = 300.0

_CONNECTION_LOST_SQLSTATES = frozenset({"08003", "08006"})


@dataclass(frozen=True)
class AnalysisSummary:
    id: UUID
    project_name: str
    state: str
    created_at: datetime
    is_sample: bool


def _is_connection_lost(error: OperationalError) -> bool:
    return (
        error.sqlstate in _CONNECTION_LOST_SQLSTATES
        or "server closed the connection unexpectedly" in str(error)
    )


async def _retry_closed_connection(operation: Callable[[], Awaitable[None]]) -> None:
    """Retry one idempotent write when the pooled connection was already closed."""
    try:
        await operation()
    except OperationalError as error:
        if not _is_connection_lost(error):
            raise
        await operation()


def _analysis_summary(row: tuple[object, ...]) -> AnalysisSummary:
    """Reject a row whose columns are not the types the query promised."""
    analysis_id, project_name, state, created_at, is_sample = row
    if (
        not isinstance(analysis_id, UUID)
        or not isinstance(project_name, str)
        or not isinstance(state, str)
        or not isinstance(created_at, datetime)
        or not isinstance(is_sample, bool)
    ):
        raise TypeError("unexpected column type in analyses query")
    return AnalysisSummary(
        id=analysis_id,
        project_name=project_name,
        state=state,
        created_at=created_at,
        is_sample=is_sample,
    )


def _make_pool(
    connection_string: str,
) -> AsyncConnectionPool[AsyncConnection[tuple[object, ...]]]:
    return AsyncConnectionPool(
        connection_string,
        kwargs=_CONNECTION_KWARGS,
        min_size=_POOL_MIN_SIZE,
        max_size=_POOL_MAX_SIZE,
        max_idle=_POOL_MAX_IDLE_SECONDS,
        max_lifetime=_POOL_MAX_LIFETIME_SECONDS,
        # A stale idle connection is detected before it is handed out.
        check=AsyncConnectionPool.check_connection,
        open=False,
    )


class DatabaseLike(Protocol):
    """The database operations the API needs, without driver types."""

    async def open(self) -> None: ...

    async def close(self) -> None: ...

    async def is_member(self, user_id: str, team_id: str) -> bool: ...

    async def list_analyses(self, user_id: str, team_id: str) -> list[AnalysisSummary]: ...

    async def delete_team(self, team_id: str) -> None: ...

    async def upsert_membership(self, user_id: str, team_id: str) -> None: ...

    async def delete_membership(self, user_id: str, team_id: str) -> None: ...


class Database:
    """Two pools: request-scoped policy access and the membership sync role."""

    def __init__(
        self, request_connection_string: str, membership_sync_connection_string: str
    ) -> None:
        self._request_pool: AsyncConnectionPool[AsyncConnection[tuple[object, ...]]] = _make_pool(
            request_connection_string
        )
        self._membership_sync_pool: AsyncConnectionPool[AsyncConnection[tuple[object, ...]]] = (
            _make_pool(membership_sync_connection_string)
        )

    async def open(self) -> None:
        # Wait for both pools before serving, so a bad connection string or an
        # unreachable database stops startup instead of failing the first request.
        await self._request_pool.open(wait=True)
        try:
            await self._membership_sync_pool.open(wait=True)
        except Exception:
            await self._request_pool.close()
            raise

    async def close(self) -> None:
        try:
            await self._request_pool.close()
        finally:
            await self._membership_sync_pool.close()

    @asynccontextmanager
    async def request_connection(
        self, user_id: str
    ) -> AsyncGenerator[AsyncConnection[tuple[object, ...]]]:
        """Run one transaction as the API role, then as the authenticated role."""
        async with self._request_pool.connection() as connection, connection.transaction():
            # SET LOCAL keeps the role and claims scoped to this transaction.
            await connection.execute(f"set local role {_CLAIMS_ROLE}")
            # auth.jwt() reads request.jwt.claims; the database, not the token,
            # decides which rows the claims can see.
            await connection.execute(
                "select set_config('request.jwt.claims', %s, true)",
                (json.dumps({"sub": user_id, "role": _CLAIMS_ROLE}),),
            )
            yield connection

    @asynccontextmanager
    async def membership_sync_connection(
        self,
    ) -> AsyncGenerator[AsyncConnection[tuple[object, ...]]]:
        """Write through the narrow membership sync role."""
        async with (
            self._membership_sync_pool.connection() as connection,
            connection.transaction(),
        ):
            yield connection

    async def is_member(self, user_id: str, team_id: str) -> bool:
        async with self.request_connection(user_id) as connection:
            cursor = await connection.execute(
                """
                select exists (
                    select 1
                    from public.membership
                    where user_id = %s and team_id = %s
                )
                """,
                (user_id, team_id),
            )
            row = await cursor.fetchone()
            return row is not None and bool(row[0])

    async def list_analyses(self, user_id: str, team_id: str) -> list[AnalysisSummary]:
        # The select policies on analyses and projects decide what this person
        # can see, so no membership check is repeated here.
        async with self.request_connection(user_id) as connection:
            cursor = await connection.execute(
                """
                select a.id, p.name as project_name, a.state, a.created_at, a.is_sample
                from public.analyses as a
                join public.projects as p on p.id = a.project_id and p.team_id = a.team_id
                where a.team_id = %s
                order by a.created_at desc, a.id desc
                limit 50
                """,
                (team_id,),
            )
            rows = await cursor.fetchall()
        return [_analysis_summary(row) for row in rows]

    async def delete_team(self, team_id: str) -> None:
        # The sync role holds no table privilege, so the routine is the only way
        # it can remove a deleted team's rows. Deleting twice is harmless.
        async def delete() -> None:
            async with self.membership_sync_connection() as connection:
                cursor = await connection.execute(
                    "select * from public.delete_team_rows(%s)",
                    (team_id,),
                )
                await cursor.fetchall()

        await _retry_closed_connection(delete)

    async def upsert_membership(self, user_id: str, team_id: str) -> None:
        async def write() -> None:
            async with self.membership_sync_connection() as connection:
                await connection.execute(
                    """
                    insert into public.membership (user_id, team_id)
                    values (%s, %s)
                    on conflict (user_id, team_id) do nothing
                    """,
                    (user_id, team_id),
                )

        await _retry_closed_connection(write)

    async def delete_membership(self, user_id: str, team_id: str) -> None:
        async def write() -> None:
            async with self.membership_sync_connection() as connection:
                await connection.execute(
                    "delete from public.membership where user_id = %s and team_id = %s",
                    (user_id, team_id),
                )

        await _retry_closed_connection(write)
