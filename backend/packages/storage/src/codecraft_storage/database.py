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


@dataclass(frozen=True)
class OrganisationSummary:
    organisation_id: str
    is_owner: bool
    created_at: datetime


@dataclass(frozen=True)
class ProjectSummary:
    id: UUID
    name: str
    created_at: datetime
    is_sample: bool
    latest_analysis_state: str | None
    latest_analysis_created_at: datetime | None


@dataclass(frozen=True)
class ProjectRecord:
    id: UUID
    name: str
    created_at: datetime
    is_sample: bool


@dataclass(frozen=True)
class ProjectAnalysisSummary:
    id: UUID
    state: str
    created_at: datetime
    is_sample: bool


@dataclass(frozen=True)
class AnalysisDetail:
    id: UUID
    project_id: UUID
    project_name: str
    state: str
    created_at: datetime
    is_sample: bool


@dataclass(frozen=True)
class ProjectDetail:
    project: ProjectRecord
    analyses: list[ProjectAnalysisSummary]


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


def _organisation_summary(row: tuple[object, ...]) -> OrganisationSummary:
    organisation_id, is_owner, created_at = row
    if (
        not isinstance(organisation_id, str)
        or not organisation_id
        or not isinstance(is_owner, bool)
        or not isinstance(created_at, datetime)
    ):
        raise TypeError("unexpected column type in organisations query")
    return OrganisationSummary(
        organisation_id=organisation_id, is_owner=is_owner, created_at=created_at
    )


def _project_summary(row: tuple[object, ...]) -> ProjectSummary:
    project_id, name, created_at, is_sample, latest_state, latest_created_at = row
    if (
        not isinstance(project_id, UUID)
        or not isinstance(name, str)
        or not isinstance(created_at, datetime)
        or not isinstance(is_sample, bool)
        or (latest_state is not None and not isinstance(latest_state, str))
        or (latest_created_at is not None and not isinstance(latest_created_at, datetime))
    ):
        raise TypeError("unexpected column type in projects query")
    return ProjectSummary(
        id=project_id,
        name=name,
        created_at=created_at,
        is_sample=is_sample,
        latest_analysis_state=latest_state,
        latest_analysis_created_at=latest_created_at,
    )


def _project_record(row: tuple[object, ...]) -> ProjectRecord:
    project_id, name, created_at, is_sample = row
    if (
        not isinstance(project_id, UUID)
        or not isinstance(name, str)
        or not isinstance(created_at, datetime)
        or not isinstance(is_sample, bool)
    ):
        raise TypeError("unexpected column type in project query")
    return ProjectRecord(
        id=project_id,
        name=name,
        created_at=created_at,
        is_sample=is_sample,
    )


def _project_analysis_summary(row: tuple[object, ...]) -> ProjectAnalysisSummary:
    analysis_id, state, created_at, is_sample = row
    if (
        not isinstance(analysis_id, UUID)
        or not isinstance(state, str)
        or not isinstance(created_at, datetime)
        or not isinstance(is_sample, bool)
    ):
        raise TypeError("unexpected column type in project analyses query")
    return ProjectAnalysisSummary(
        id=analysis_id,
        state=state,
        created_at=created_at,
        is_sample=is_sample,
    )


def _analysis_detail(row: tuple[object, ...]) -> AnalysisDetail:
    analysis_id, project_id, project_name, state, created_at, is_sample = row
    if (
        not isinstance(analysis_id, UUID)
        or not isinstance(project_id, UUID)
        or not isinstance(project_name, str)
        or not isinstance(state, str)
        or not isinstance(created_at, datetime)
        or not isinstance(is_sample, bool)
    ):
        raise TypeError("unexpected column type in analysis detail query")
    return AnalysisDetail(
        id=analysis_id,
        project_id=project_id,
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

    async def is_member(self, user_id: str, organisation_id: str) -> bool: ...

    async def list_organisations(self, user_id: str) -> list[OrganisationSummary]: ...

    async def is_owner(self, user_id: str, organisation_id: str) -> bool: ...

    async def has_other_owned_organisation(self, user_id: str, organisation_id: str) -> bool: ...

    async def has_other_organisation(self, user_id: str, organisation_id: str) -> bool: ...

    async def list_analyses(self, user_id: str, organisation_id: str) -> list[AnalysisSummary]: ...

    async def list_projects(self, user_id: str, organisation_id: str) -> list[ProjectSummary]: ...

    async def get_project(self, user_id: str, project_id: UUID) -> ProjectDetail | None: ...

    async def get_analysis(self, user_id: str, analysis_id: UUID) -> AnalysisDetail | None: ...

    async def delete_organisation(self, organisation_id: str) -> None: ...

    async def upsert_membership(self, user_id: str, organisation_id: str) -> None: ...

    async def set_owner(self, user_id: str, organisation_id: str) -> None: ...

    async def delete_membership(self, user_id: str, organisation_id: str) -> None: ...


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

    async def is_member(self, user_id: str, organisation_id: str) -> bool:
        async with self.request_connection(user_id) as connection:
            cursor = await connection.execute(
                """
                select exists (
                    select 1
                    from public.membership
                    where user_id = %s and organisation_id = %s
                )
                """,
                (user_id, organisation_id),
            )
            row = await cursor.fetchone()
            return row is not None and bool(row[0])

    async def list_organisations(self, user_id: str) -> list[OrganisationSummary]:
        async with self.request_connection(user_id) as connection:
            cursor = await connection.execute(
                """
                select organisation_id, is_owner, created_at
                from public.membership
                where user_id = %s
                order by created_at asc, organisation_id asc
                """,
                (user_id,),
            )
            rows = await cursor.fetchall()
        return [_organisation_summary(row) for row in rows]

    async def is_owner(self, user_id: str, organisation_id: str) -> bool:
        # The caller may be checking another member (the owner cannot be
        # removed), so their row-level policy would hide the answer. This is a
        # boolean authority check, not organisation data, so read it through the narrow
        # membership sync role instead.
        async with self.membership_sync_connection() as connection:
            cursor = await connection.execute(
                """
                select exists (
                    select 1
                    from public.membership
                    where user_id = %s and organisation_id = %s and is_owner
                )
                """,
                (user_id, organisation_id),
            )
            row = await cursor.fetchone()
            return row is not None and bool(row[0])

    async def has_other_owned_organisation(self, user_id: str, organisation_id: str) -> bool:
        async with self.request_connection(user_id) as connection:
            cursor = await connection.execute(
                """
                select exists (
                    select 1
                    from public.membership
                    where user_id = %s and is_owner and organisation_id <> %s
                )
                """,
                (user_id, organisation_id),
            )
            row = await cursor.fetchone()
            return row is not None and bool(row[0])

    async def has_other_organisation(self, user_id: str, organisation_id: str) -> bool:
        # The caller may be checking another member, whose rows their policy
        # does not expose. This is a boolean authority check, not organisation data, so
        # read it through the narrow membership sync role instead.
        async with self.membership_sync_connection() as connection:
            cursor = await connection.execute(
                """
                select exists (
                    select 1
                    from public.membership
                    where user_id = %s and organisation_id <> %s
                )
                """,
                (user_id, organisation_id),
            )
            row = await cursor.fetchone()
            return row is not None and bool(row[0])

    async def list_analyses(self, user_id: str, organisation_id: str) -> list[AnalysisSummary]:
        # The select policies on analyses and projects decide what this person
        # can see, so no membership check is repeated here.
        async with self.request_connection(user_id) as connection:
            cursor = await connection.execute(
                """
                select a.id, p.name as project_name, a.state, a.created_at, a.is_sample
                from public.analyses as a
                join public.projects as p
                  on p.id = a.project_id and p.organisation_id = a.organisation_id
                where a.organisation_id = %s
                order by a.created_at desc, a.id desc
                limit 50
                """,
                (organisation_id,),
            )
            rows = await cursor.fetchall()
        return [_analysis_summary(row) for row in rows]

    async def list_projects(self, user_id: str, organisation_id: str) -> list[ProjectSummary]:
        # The select policies on projects and analyses decide what this person
        # can see, so no membership check is repeated here.
        async with self.request_connection(user_id) as connection:
            cursor = await connection.execute(
                """
                select p.id, p.name, p.created_at, p.is_sample, latest.state, latest.created_at
                from public.projects as p
                left join lateral (
                    select a.state, a.created_at
                    from public.analyses as a
                    where a.project_id = p.id and a.organisation_id = p.organisation_id
                    order by a.created_at desc, a.id desc
                    limit 1
                ) as latest on true
                where p.organisation_id = %s
                order by p.created_at desc, p.id desc
                limit 50
                """,
                (organisation_id,),
            )
            rows = await cursor.fetchall()
        return [_project_summary(row) for row in rows]

    async def get_project(self, user_id: str, project_id: UUID) -> ProjectDetail | None:
        async with self.request_connection(user_id) as connection:
            cursor = await connection.execute(
                """
                select id, name, created_at, is_sample
                from public.projects
                where id = %s
                """,
                (project_id,),
            )
            project_row = await cursor.fetchone()
            if project_row is None:
                # A project hidden by the policy and a project that does not exist
                # look the same to the caller.
                return None
            analyses_cursor = await connection.execute(
                """
                select id, state, created_at, is_sample
                from public.analyses
                where project_id = %s
                order by created_at desc, id desc
                limit 50
                """,
                (project_id,),
            )
            analysis_rows = await analyses_cursor.fetchall()
        return ProjectDetail(
            project=_project_record(project_row),
            analyses=[_project_analysis_summary(row) for row in analysis_rows],
        )

    async def get_analysis(self, user_id: str, analysis_id: UUID) -> AnalysisDetail | None:
        async with self.request_connection(user_id) as connection:
            cursor = await connection.execute(
                """
                select a.id, a.project_id, p.name, a.state, a.created_at, a.is_sample
                from public.analyses as a
                join public.projects as p
                  on p.id = a.project_id and p.organisation_id = a.organisation_id
                where a.id = %s
                """,
                (analysis_id,),
            )
            row = await cursor.fetchone()
        if row is None:
            return None
        return _analysis_detail(row)

    async def delete_organisation(self, organisation_id: str) -> None:
        # The sync role holds no table privilege, so the routine is the only way
        # it can remove a deleted organisation's rows. Deleting twice is harmless.
        async def delete() -> None:
            async with self.membership_sync_connection() as connection:
                cursor = await connection.execute(
                    "select * from public.delete_organisation_rows(%s)",
                    (organisation_id,),
                )
                await cursor.fetchall()

        await _retry_closed_connection(delete)

    async def upsert_membership(self, user_id: str, organisation_id: str) -> None:
        async def write() -> None:
            async with self.membership_sync_connection() as connection:
                await connection.execute(
                    """
                    insert into public.membership (user_id, organisation_id)
                    values (%s, %s)
                    on conflict (user_id, organisation_id) do nothing
                    """,
                    (user_id, organisation_id),
                )

        await _retry_closed_connection(write)

    async def set_owner(self, user_id: str, organisation_id: str) -> None:
        async def write() -> None:
            async with self.membership_sync_connection() as connection:
                await connection.execute(
                    """
                    insert into public.membership (user_id, organisation_id, is_owner)
                    values (%s, %s, true)
                    on conflict (user_id, organisation_id) do update set is_owner = true
                    """,
                    (user_id, organisation_id),
                )

        await _retry_closed_connection(write)

    async def delete_membership(self, user_id: str, organisation_id: str) -> None:
        async def write() -> None:
            async with self.membership_sync_connection() as connection:
                await connection.execute(
                    "delete from public.membership where user_id = %s and organisation_id = %s",
                    (user_id, organisation_id),
                )

        await _retry_closed_connection(write)
