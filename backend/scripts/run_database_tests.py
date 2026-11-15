"""Run the database security checks against the linked Supabase project.

Every check runs in a transaction that is always rolled back. The connection
string is requested with hidden input, checked against the linked project, used
for this process only, and never printed or written anywhere.

This is an operator check, not API runtime. It deliberately opens its own
migration connection because it must set roles the API never holds.
"""

import argparse
import getpass
import json
import re
import sys
from collections.abc import Callable
from pathlib import Path
from typing import LiteralString, cast
from urllib.parse import urlsplit
from uuid import uuid4

import psycopg
from psycopg import Connection, errors, sql

_TABLES = (
    "projects",
    "analyses",
    "files",
    "edges",
    "routes",
    "explanations",
    "file_roles",
    "insights",
)
_ALL_TABLES = ("membership", *_TABLES)
_CREATION_TABLE = "organisation_creation_attempts"
_CREATION_ROLE = "codecraft_creation"
_EXPOSED_TABLES = (*_ALL_TABLES, _CREATION_TABLE)
_SUBJECT_POLICY = re.compile(
    r"^\s*\(\s*user_id\s*=\s*\(\s*select\s+\(\s*auth\.jwt\(\)\s*"
    r"->>\s*'sub'::text\s*\)\s*\)\s*\)\s*$",
    re.IGNORECASE,
)
_ALLOWED_TABLE_PRIVILEGES = frozenset(
    {"SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE", "REFERENCES", "TRIGGER", "MAINTAIN"}
)
_STATES = ("queued", "running", "complete", "failed")
# The deletion fixture inserts these rows for each organisation. The files table gets
# two rows because every fixture edge has a source file and a target file.
_FIXTURE_ROWS = {
    "membership": 1,
    "projects": 1,
    "analyses": 1,
    "files": 2,
    "edges": 1,
    "routes": 1,
    "explanations": 1,
    "file_roles": 1,
    "insights": 1,
    "organisation_creation_attempts": 1,
}
_FUNCTION = "public.delete_organisation_rows(text)"
_LINKED_PROJECT_FILE = Path(__file__).resolve().parents[2] / "supabase" / ".temp" / "project-ref"


class CheckFailed(Exception):
    """A database check did not hold."""


class RoleRefused(Exception):
    """SET ROLE was refused, so the run must stop."""

    def __init__(self, role: str, error: psycopg.Error) -> None:
        self.role = role
        self.error = error
        super().__init__(f"SET ROLE {role} was refused")


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise CheckFailed(message)


def _integer(row: tuple[object, ...] | None) -> int:
    _require(row is not None, "a count query returned no row")
    assert row is not None
    value = row[0]
    _require(isinstance(value, int), "a count query did not return an integer")
    return cast(int, value)


def _identifier(table: str) -> sql.Identifier:
    return sql.Identifier(cast(LiteralString, table))


def _linked_project_ref() -> str:
    try:
        project_ref = _LINKED_PROJECT_FILE.read_text(encoding="utf-8").strip()
    except OSError as error:
        raise SystemExit(
            f"cannot read the linked project reference at {_LINKED_PROJECT_FILE}: {error}"
        ) from error

    if not project_ref:
        raise SystemExit(f"the linked project reference at {_LINKED_PROJECT_FILE} is empty")
    return project_ref


def _project_ref_from_dsn(dsn: str) -> str | None:
    parsed = urlsplit(dsn)
    host = parsed.hostname or ""
    username = parsed.username or ""

    if host.startswith("db.") and host.endswith(".supabase.co"):
        parts = host.split(".")
        if len(parts) >= 4:
            return parts[1]

    if username.startswith("postgres."):
        return username.split(".", 1)[1]

    return None


def _membership_count(connection: Connection[tuple[object, ...]]) -> int:
    return _integer(
        connection.execute(sql.SQL("select count(*) from public.membership")).fetchone()
    )


def _counts(connection: Connection[tuple[object, ...]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    membership_values: list[int] = []
    with connection.transaction():
        for table in _ALL_TABLES:
            if table == "membership":
                membership_values.clear()

                def read_membership() -> None:
                    membership_values.append(_membership_count(connection))

                _as_sync(connection, read_membership)
                counts[table] = membership_values[0]
            else:
                counts[table] = _integer(
                    connection.execute(
                        sql.SQL("select count(*) from public.{}").format(_identifier(table))
                    ).fetchone()
                )
    return counts


def _set_role(connection: Connection[tuple[object, ...]], role: str) -> None:
    try:
        # The application's connection factory uses SET LOCAL ROLE for the
        # transaction, so the checks use the same form.
        connection.execute(
            sql.SQL("set local role {}").format(sql.Identifier(cast(LiteralString, role)))
        )
    except psycopg.Error as error:
        raise RoleRefused(role, error) from error


def _current_role(connection: Connection[tuple[object, ...]]) -> str:
    row = connection.execute("select current_user").fetchone()
    if row is None or not isinstance(row[0], str):
        return "unknown"
    return row[0]


def _as_user(
    connection: Connection[tuple[object, ...]],
    user_id: str,
    action: Callable[[], None],
) -> None:
    _set_role(connection, "authenticated")
    connection.execute(
        "select set_config('request.jwt.claims', %s, true)",
        (json.dumps({"sub": user_id, "role": "authenticated"}),),
    )
    try:
        action()
    except psycopg.Error as error:
        raise CheckFailed(
            f"query failed as authenticated for subject {user_id}: {error}"
        ) from error
    connection.execute("reset role")


def _as_sync(
    connection: Connection[tuple[object, ...]],
    action: Callable[[], None],
) -> None:
    """Read or write membership as its owner, because RLS hides other rows."""
    connection.execute("grant codecraft_membership_sync to current_user")
    connection.execute("set local role codecraft_membership_sync")
    try:
        action()
    except psycopg.Error as error:
        raise CheckFailed(f"query failed as the membership sync role: {error}") from error
    finally:
        try:
            connection.execute("reset role")
            connection.execute("revoke codecraft_membership_sync from current_user")
        except psycopg.Error:
            # The transaction is already aborted; its rollback restores the role.
            pass


def _returned_id(row: tuple[object, ...] | None) -> object:
    _require(row is not None, "an insert returned no row")
    assert row is not None
    return row[0]


def _insert_organisation_rows(
    connection: Connection[tuple[object, ...]], organisation_id: str, project_name: str
) -> None:
    project_id = _returned_id(
        connection.execute(
            "insert into public.projects (organisation_id, name) values (%s, %s) returning id",
            (organisation_id, project_name),
        ).fetchone()
    )
    analysis_id = _returned_id(
        connection.execute(
            """
            insert into public.analyses (organisation_id, project_id, state)
            values (%s, %s, 'complete')
            returning id
            """,
            (organisation_id, project_id),
        ).fetchone()
    )
    source_file_id = _returned_id(
        connection.execute(
            """
            insert into public.files (organisation_id, analysis_id, path)
            values (%s, %s, %s)
            returning id
            """,
            (organisation_id, analysis_id, "src/source.ts"),
        ).fetchone()
    )
    target_file_id = _returned_id(
        connection.execute(
            """
            insert into public.files (organisation_id, analysis_id, path)
            values (%s, %s, %s)
            returning id
            """,
            (organisation_id, analysis_id, "src/target.ts"),
        ).fetchone()
    )
    connection.execute(
        """
        insert into public.edges (
            organisation_id, analysis_id, source_file_id, target_file_id, kind
        )
        values (%s, %s, %s, %s, 'import')
        """,
        (organisation_id, analysis_id, source_file_id, target_file_id),
    )
    connection.execute(
        """
        insert into public.routes (organisation_id, analysis_id, file_id, method, path)
        values (%s, %s, %s, 'GET', '/sample')
        """,
        (organisation_id, analysis_id, source_file_id),
    )
    connection.execute(
        """
        insert into public.explanations (organisation_id, analysis_id, file_id, content_hash, body)
        values (%s, %s, %s, 'hash', 'body')
        """,
        (organisation_id, analysis_id, source_file_id),
    )
    connection.execute(
        """
        insert into public.file_roles (organisation_id, analysis_id, file_id, role)
        values (%s, %s, %s, 'page')
        """,
        (organisation_id, analysis_id, source_file_id),
    )
    connection.execute(
        """
        insert into public.insights (organisation_id, analysis_id, kind, detail)
        values (%s, %s, 'cycle', '{}'::jsonb)
        """,
        (organisation_id, analysis_id),
    )
    connection.execute(
        """
        insert into public.organisation_creation_attempts
            (user_id, idempotency_key, status, organisation_id)
        values (%s, %s, 'created', %s)
        """,
        (
            f"user_creation_{organisation_id}",
            f"key_creation_{organisation_id}",
            organisation_id,
        ),
    )


def _count_for_organisation(
    connection: Connection[tuple[object, ...]], table: str, organisation_id: str
) -> int:
    if table == "membership":
        values: list[int] = []

        def read_membership() -> None:
            values.append(
                _integer(
                    connection.execute(
                        "select count(*) from public.membership where organisation_id = %s",
                        (organisation_id,),
                    ).fetchone()
                )
            )

        _as_sync(connection, read_membership)
        return values[0]

    return _integer(
        connection.execute(
            sql.SQL("select count(*) from public.{} where organisation_id = %s").format(
                _identifier(table)
            ),
            (organisation_id,),
        ).fetchone()
    )


def _count_all(connection: Connection[tuple[object, ...]], table: str) -> int:
    if table == "membership":
        values: list[int] = []

        def read_membership() -> None:
            values.append(
                _integer(
                    connection.execute(
                        sql.SQL("select count(*) from public.{}").format(_identifier(table))
                    ).fetchone()
                )
            )

        _as_sync(connection, read_membership)
        return values[0]

    return _integer(
        connection.execute(
            sql.SQL("select count(*) from public.{}").format(_identifier(table))
        ).fetchone()
    )


def _is_subject_equality_policy(expression: object) -> bool:
    # Only the exact equality form is accepted. Any other comparison operator,
    # extra predicate, or different claim would fail this match.
    return isinstance(expression, str) and _SUBJECT_POLICY.fullmatch(expression) is not None


def _creation_policy_report(connection: Connection[tuple[object, ...]]) -> None:
    rows = connection.execute(
        """
        select cmd, roles, qual, with_check
        from pg_policies
        where schemaname in ('public', 'graphql_public') and tablename = %s
        """,
        (_CREATION_TABLE,),
    ).fetchall()
    _require(len(rows) == 3, "the creation table does not have exactly three policies")

    policies: dict[str, tuple[object, object]] = {}
    for cmd, roles, qual, with_check in rows:
        _require(isinstance(cmd, str), "a creation policy has no command")
        _require(cmd in {"SELECT", "INSERT", "UPDATE"}, f"unexpected creation policy {cmd}")
        _require(cmd not in policies, f"duplicate creation policy for {cmd}")
        _require(
            isinstance(roles, list) and [str(role) for role in roles] == ["codecraft_creation"],
            f"creation policy {cmd} is not limited to codecraft_creation",
        )
        policies[cmd] = (qual, with_check)

    _require(
        set(policies) == {"SELECT", "INSERT", "UPDATE"},
        "the creation table does not have select, insert and update policies",
    )
    select_qual, select_check = policies["SELECT"]
    _require(_is_subject_equality_policy(select_qual), "the creation select policy has no subject")
    _require(select_check is None, "the creation select policy has a write check")
    insert_qual, insert_check = policies["INSERT"]
    _require(insert_qual is None, "the creation insert policy has a read expression")
    _require(_is_subject_equality_policy(insert_check), "the creation insert policy has no subject")
    update_qual, update_check = policies["UPDATE"]
    _require(
        _is_subject_equality_policy(update_qual), "the creation update policy has no read subject"
    )
    _require(
        _is_subject_equality_policy(update_check), "the creation update policy has no write subject"
    )


def _creation_role_report(connection: Connection[tuple[object, ...]]) -> None:
    row = connection.execute(
        """
        select rolcanlogin, rolbypassrls, rolinherit
        from pg_roles
        where rolname = 'codecraft_creation'
        """
    ).fetchone()
    _require(row is not None, "the codecraft_creation role does not exist")
    assert row is not None
    _require(
        row[0] is False and row[1] is False and row[2] is False,
        "codecraft_creation must be NOLOGIN, NOBYPASSRLS and NOINHERIT",
    )


def _catalog_report(connection: Connection[tuple[object, ...]]) -> None:
    tables = connection.execute(
        """
        select c.relname, c.relrowsecurity, owner.rolname
        from pg_class as c
        join pg_namespace as n on n.oid = c.relnamespace
        join pg_roles as owner on owner.oid = c.relowner
        where n.nspname in ('public', 'graphql_public') and c.relkind = 'r'
        order by c.relname
        """
    ).fetchall()
    table_names = {row[0] for row in tables}
    _require(table_names == set(_EXPOSED_TABLES), "the exposed table set changed")

    policy_rows = connection.execute(
        """
        select tablename, count(*)
        from pg_policies
        where schemaname in ('public', 'graphql_public') and cmd in ('SELECT', 'ALL')
        group by tablename
        """
    ).fetchall()
    policy_counts = {row[0]: row[1] for row in policy_rows if row[0] != _CREATION_TABLE}
    _require(
        policy_counts == {table: 1 for table in _ALL_TABLES},
        "an exposed table does not have exactly one select policy",
    )
    _creation_policy_report(connection)
    _creation_role_report(connection)

    owners = {row[0]: row[2] for row in tables}
    for table, row_security, _ in tables:
        _require(row_security is True, f"row-level security is disabled on {table}")

    routine_owner_row = connection.execute(
        """
        select pg_catalog.pg_get_userbyid(p.proowner)
        from pg_catalog.pg_proc as p
        join pg_catalog.pg_namespace as n on n.oid = p.pronamespace
        where n.nspname = 'public' and p.proname = 'delete_organisation_rows'
        """
    ).fetchone()
    _require(routine_owner_row is not None, "the cleanup routine does not exist")
    assert routine_owner_row is not None
    _require(
        isinstance(routine_owner_row[0], str),
        "the cleanup routine owner is not a role",
    )
    routine_owner = cast(str, routine_owner_row[0])

    privileges = connection.execute(
        """
        select c.relname, coalesce(grantee.rolname, 'PUBLIC'), acl.privilege_type
        from pg_class as c
        join pg_namespace as n on n.oid = c.relnamespace
        cross join lateral aclexplode(
          coalesce(c.relacl, acldefault('r', c.relowner))
        ) as acl
        left join pg_roles as grantee on grantee.oid = acl.grantee
        where n.nspname in ('public', 'graphql_public') and c.relkind = 'r'
        """
    ).fetchall()

    sync_grants: dict[str, list[str]] = {table: [] for table in _ALL_TABLES}
    creation_grants: list[str] = []
    for table, grantee, privilege in privileges:
        _require(
            isinstance(table, str) and isinstance(grantee, str) and isinstance(privilege, str),
            "a table privilege row has an unexpected type",
        )
        _require(
            privilege in _ALLOWED_TABLE_PRIVILEGES,
            f"unknown privilege {privilege} on {table}",
        )
        if table == _CREATION_TABLE:
            allowed = grantee == owners[table] or (
                grantee == "codecraft_creation" and privilege in ("SELECT", "INSERT", "UPDATE")
            )
            _require(allowed, f"{grantee} holds {privilege} on {table}")
            if grantee == "codecraft_creation":
                creation_grants.append(privilege)
            continue
        allowed = (
            grantee == owners[table]
            or (grantee == "authenticated" and privilege == "SELECT")
            or (
                table == "membership"
                and grantee == routine_owner
                and privilege in ("SELECT", "DELETE")
            )
        )
        _require(allowed, f"{grantee} holds {privilege} on {table}")
        if grantee == "codecraft_membership_sync":
            sync_grants[table].append(privilege)

    _require(
        set(creation_grants) == {"SELECT", "INSERT", "UPDATE"},
        "codecraft_creation does not hold exactly select, insert and update",
    )

    function_privileges = connection.execute(
        """
        select coalesce(grantee.rolname, 'PUBLIC'), acl.privilege_type
        from pg_proc as p
        join pg_namespace as n on n.oid = p.pronamespace
        cross join lateral aclexplode(
          coalesce(p.proacl, acldefault('f', p.proowner))
        ) as acl
        left join pg_roles as grantee on grantee.oid = acl.grantee
        where n.nspname = 'public'
          and p.proname in ('delete_organisation_rows', 'delete_membership_rows')
        """
    ).fetchall()

    function_grantees = {row[0] for row in function_privileges}
    _require("codecraft_membership_sync" in function_grantees, "sync cannot execute the routine")
    for forbidden in ("PUBLIC", "anon", "authenticated", "service_role"):
        _require(forbidden not in function_grantees, f"{forbidden} can execute the routine")
    for grantee, privilege in function_privileges:
        _require(privilege == "EXECUTE", f"unexpected function privilege {privilege}")
        allowed_grantees = {"codecraft_membership_sync"} | {owners[table] for table in _ALL_TABLES}
        _require(grantee in allowed_grantees, f"{grantee} can execute the routine")

    print("catalog checks")
    for table in _ALL_TABLES:
        grants = ", ".join(sorted(sync_grants[table])) or "none"
        print(f"  {table}: rls=true select_policies=1 sync_grants={grants}")
    print(
        f"  {_CREATION_TABLE}: rls=true policies=select/insert/update "
        f"to codecraft_creation grants={', '.join(sorted(creation_grants))}"
    )
    print(
        "  cleanup routines: outer execute=sync; membership helper execute=owner; "
        "public, anon, authenticated, service_role absent"
    )


def _check_catalog(connection: Connection[tuple[object, ...]]) -> None:
    with connection.transaction(force_rollback=True):
        _catalog_report(connection)


def _check_role_switch(connection: Connection[tuple[object, ...]]) -> None:
    with connection.transaction(force_rollback=True):
        _set_role(connection, "authenticated")
        connection.execute("reset role")
    print("role switch checks: authenticated accepted")


def _check_policy(connection: Connection[tuple[object, ...]]) -> None:
    suffix = uuid4().hex

    with connection.transaction(force_rollback=True):
        # The database can be empty, so the member fixture is created here and
        # rolled back. Membership belongs to the sync role, so write it as that
        # role; the policy check then runs as the authenticated user.
        member_user = f"user_member_{suffix}"
        member_organisation = f"org_member_{suffix}"
        other_organisation = f"org_other_{suffix}"
        non_member = f"user_non_member_{suffix}"

        def insert_member() -> None:
            connection.execute(
                """
                insert into public.membership (user_id, organisation_id)
                values (%s, %s)
                """,
                (member_user, member_organisation),
            )

        _as_sync(connection, insert_member)

        non_member_rows: list[tuple[object, ...] | None] = []

        def read_non_member() -> None:
            non_member_rows.append(
                connection.execute(
                    "select exists (select 1 from public.membership where user_id = %s)",
                    (non_member,),
                ).fetchone()
            )

        _as_sync(connection, read_non_member)
        non_member_exists = non_member_rows[0] if non_member_rows else None
        _require(
            non_member_exists is not None and non_member_exists[0] is False,
            "the generated non-member already has a membership",
        )

        _insert_organisation_rows(connection, member_organisation, "project-member")
        _insert_organisation_rows(connection, other_organisation, "project-other")

        def member_checks() -> None:
            for table in _TABLES:
                _require(
                    _count_for_organisation(connection, table, member_organisation) >= 1,
                    f"member cannot read its own {table} row",
                )
                _require(
                    _count_for_organisation(connection, table, other_organisation) == 0,
                    f"member can read another organisation's {table} row",
                )

        _as_user(connection, member_user, member_checks)

        def non_member_checks() -> None:
            for table in _TABLES:
                _require(
                    _count_for_organisation(connection, table, member_organisation) == 0,
                    f"non-member can read {table} rows",
                )
                _require(
                    _count_all(connection, table) == 0,
                    f"non-member sees unexpected {table} rows",
                )

        _as_user(connection, non_member, non_member_checks)

    print("policy checks: member sees own organisation only; non-member sees nothing")


def _require_fixture_counts(expected: dict[str, int], actual: dict[str, int]) -> None:
    all_tables = list(_TABLES) + sorted(set(actual) - set(_TABLES))
    print("deletion counts:")
    for table in all_tables:
        print(
            f"  {table}: expected={expected.get(table, 'missing')} "
            f"actual={actual.get(table, 'missing')}"
        )

    if actual != expected:
        details = "; ".join(
            f"{table}: expected {expected.get(table, 'missing')}, "
            f"actual {actual.get(table, 'missing')}"
            for table in all_tables
            if expected.get(table) != actual.get(table)
        )
        raise CheckFailed(f"cleanup counts do not match ({details})")


def _check_deletion(connection: Connection[tuple[object, ...]]) -> None:
    suffix = uuid4().hex
    organisation_a = f"org_a_{suffix}"
    organisation_b = f"org_b_{suffix}"

    with connection.transaction(force_rollback=True):
        print(
            "deletion fixture organisations: "
            f"organisation_a={organisation_a} organisation_b={organisation_b}"
        )
        print(f"deletion fixture rows per organisation: {_FIXTURE_ROWS}")
        _insert_organisation_rows(connection, organisation_a, "project-a")
        _insert_organisation_rows(connection, organisation_b, "project-b")

        def insert_memberships() -> None:
            connection.execute(
                """
                insert into public.membership (user_id, organisation_id, is_owner)
                values (%s, %s, true), (%s, %s, false)
                """,
                (f"user_a_{suffix}", organisation_a, f"user_b_{suffix}", organisation_b),
            )

        _as_sync(connection, insert_memberships)
        membership_before = _count_all(connection, "membership")

        # The connection role owns the routine and the eight tables; the routine
        # calls the sync-owned helper for membership. The catalog check separately
        # proves the sync role is the only other role with EXECUTE.
        deleted_rows = connection.execute(
            "select * from public.delete_organisation_rows(%s)", (organisation_a,)
        ).fetchall()

        counts: dict[str, int] = {}
        for row in deleted_rows:
            _require(len(row) == 2, "the cleanup routine returned an unexpected row")
            table_name, deleted = row
            _require(isinstance(table_name, str) and isinstance(deleted, int), "bad row")
            counts[table_name] = deleted

        _require_fixture_counts(_FIXTURE_ROWS, counts)
        for table in _TABLES:
            _require(
                _count_for_organisation(connection, table, organisation_a) == 0,
                f"{table} was not removed",
            )
            _require(
                _count_for_organisation(connection, table, organisation_b) == _FIXTURE_ROWS[table],
                f"{table} of the other organisation changed",
            )
        _require(
            _count_for_organisation(connection, _CREATION_TABLE, organisation_a) == 0,
            "the deleted organisation's creation-attempt rows were not removed",
        )
        _require(
            _count_for_organisation(connection, _CREATION_TABLE, organisation_b)
            == _FIXTURE_ROWS[_CREATION_TABLE],
            "the other organisation's creation-attempt rows changed",
        )
        _require(
            _count_for_organisation(connection, "membership", organisation_a) == 0,
            "the deleted organisation's membership rows were not removed",
        )
        _require(
            _count_for_organisation(connection, "membership", organisation_b) == 1,
            "the other organisation's membership row changed",
        )
        _require(
            _count_all(connection, "membership") == membership_before - 1,
            "the membership count did not match the deleted organisation",
        )

    print(
        "deletion checks: named organisation removed across eight tables, "
        "creation attempts and membership; other organisation kept"
    )


def _check_function_guards(connection: Connection[tuple[object, ...]]) -> None:
    for organisation_id in (None, "", "   "):
        with connection.transaction(force_rollback=True):
            try:
                connection.execute(
                    "select * from public.delete_organisation_rows(%s)", (organisation_id,)
                )
            except errors.RaiseException:
                continue
            raise CheckFailed("the cleanup routine accepted a null or empty identifier")
    print("function guard checks: null and empty identifiers refused")


def _enter_creation_role(connection: Connection[tuple[object, ...]]) -> bool:
    # The migration role owns codecraft_creation but is not a member. Grant it
    # for this verification transaction only, then remove it again. The API
    # role is already a member, so it must not be revoked here.
    row = connection.execute(
        "select pg_has_role(current_user, %s, 'member')",
        (_CREATION_ROLE,),
    ).fetchone()
    granted = row is None or row[0] is not True
    if granted:
        connection.execute("grant codecraft_creation to current_user")
    _set_role(connection, _CREATION_ROLE)
    return granted


def _leave_creation_role(connection: Connection[tuple[object, ...]], granted: bool) -> None:
    try:
        connection.execute("reset role")
        if granted:
            connection.execute("revoke codecraft_creation from current_user")
    except psycopg.Error:
        # The transaction is already aborted; rollback restores the grant.
        pass


def _check_creation_policy_access(connection: Connection[tuple[object, ...]]) -> None:
    user_a = f"creation_policy_a_{uuid4().hex}"
    user_b = f"creation_policy_b_{uuid4().hex}"
    key_a = f"creation_key_a_{uuid4().hex}"
    key_b = f"creation_key_b_{uuid4().hex}"
    key_c = f"creation_key_c_{uuid4().hex}"

    with connection.transaction(force_rollback=True):
        connection.execute(
            "select set_config('request.jwt.claims', %s, true)",
            (json.dumps({"sub": user_a}),),
        )
        granted = _enter_creation_role(connection)
        try:
            connection.execute(
                """
                insert into public.organisation_creation_attempts
                    (user_id, idempotency_key, status)
                values (%s, %s, 'failed')
                """,
                (user_a, key_a),
            )
            _require(
                _integer(
                    connection.execute(
                        """
                        select count(*)
                        from public.organisation_creation_attempts
                        where user_id = %s and idempotency_key = %s
                        """,
                        (user_a, key_a),
                    ).fetchone()
                )
                == 1,
                "creation policy blocked the caller's own select",
            )
            update_own = connection.execute(
                """
                update public.organisation_creation_attempts
                set status = 'claimed'
                where user_id = %s and idempotency_key = %s
                """,
                (user_a, key_a),
            )
            _require(update_own.rowcount == 1, "creation policy blocked the caller's own update")

            connection.execute(
                "select set_config('request.jwt.claims', %s, true)",
                (json.dumps({"sub": user_b}),),
            )
            connection.execute(
                """
                insert into public.organisation_creation_attempts
                    (user_id, idempotency_key, status)
                values (%s, %s, 'failed')
                """,
                (user_b, key_b),
            )
            connection.execute(
                "select set_config('request.jwt.claims', %s, true)",
                (json.dumps({"sub": user_a}),),
            )
            _require(
                _integer(
                    connection.execute(
                        """
                        select count(*)
                        from public.organisation_creation_attempts
                        where user_id = %s and idempotency_key = %s
                        """,
                        (user_b, key_b),
                    ).fetchone()
                )
                == 0,
                "creation policy exposed another user's row to the caller",
            )
            update_other = connection.execute(
                """
                update public.organisation_creation_attempts
                set status = 'claimed'
                where user_id = %s and idempotency_key = %s
                """,
                (user_b, key_b),
            )
            _require(update_other.rowcount == 0, "creation policy updated another user's row")
        finally:
            _leave_creation_role(connection, granted)

    with connection.transaction(force_rollback=True):
        connection.execute(
            "select set_config('request.jwt.claims', %s, true)",
            (json.dumps({"sub": user_a}),),
        )
        granted = _enter_creation_role(connection)
        try:
            try:
                connection.execute(
                    """
                    insert into public.organisation_creation_attempts
                        (user_id, idempotency_key, status)
                    values (%s, %s, 'failed')
                    """,
                    (user_b, key_c),
                )
            except errors.InsufficientPrivilege:
                pass
            else:
                raise CheckFailed("creation policy allowed an insert for another user")
        finally:
            _leave_creation_role(connection, granted)

    print(
        "creation policy access checks: own select/insert/update pass; "
        "other user's select/update return no rows; other user's insert refused"
    )


def _diff_counts(before: dict[str, int], after: dict[str, int]) -> list[str]:
    return [
        f"{table}: {before[table]} -> {after[table]}"
        for table in _ALL_TABLES
        if before[table] != after[table]
    ]


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run phase 2 database checks against the linked Supabase project."
    )
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="Required acknowledgement that this is the linked project.",
    )
    return parser


def main() -> int:
    arguments = _parser().parse_args()
    if not arguments.confirm:
        print("refusing to run without --confirm", file=sys.stderr)
        return 1

    linked_ref = _linked_project_ref()
    connection_string = getpass.getpass("Migration role connection string: ").strip()
    if not connection_string:
        print("no connection string entered", file=sys.stderr)
        return 1

    found_ref = _project_ref_from_dsn(connection_string)
    if found_ref is None or found_ref != linked_ref:
        print(
            "refusing: the connection does not name the linked project "
            f"(expected {linked_ref}, found {found_ref or 'unknown'})",
            file=sys.stderr,
        )
        return 1

    try:
        connection = psycopg.connect(connection_string, connect_timeout=15, prepare_threshold=None)
    except psycopg.Error as error:
        print(f"connection failed: {type(error).__name__}", file=sys.stderr)
        return 1

    with connection.transaction():
        print("connection role:", _current_role(connection))

    results: list[tuple[str, str]] = []
    refused = False
    before: dict[str, int] = {}
    try:
        before = _counts(connection)
        print("row counts before:", before)

        checks: tuple[tuple[str, Callable[[], None]], ...] = (
            ("catalog", lambda: _check_catalog(connection)),
            ("role switch", lambda: _check_role_switch(connection)),
            ("policy", lambda: _check_policy(connection)),
            ("deletion", lambda: _check_deletion(connection)),
            ("function guards", lambda: _check_function_guards(connection)),
            ("creation policy access", lambda: _check_creation_policy_access(connection)),
        )

        for name, check in checks:
            if refused:
                results.append((name, "not run: role switch refused"))
                continue
            print(f"running {name} checks")
            try:
                check()
            except RoleRefused as error:
                refused = True
                message = error.error.diag.message_primary or str(error.error)
                result = f"refused SET ROLE {error.role}: {message}"
                results.append((name, result))
                print(f"{name}: {result}", file=sys.stderr)
            except (CheckFailed, psycopg.Error) as error:
                result = f"fail: {type(error).__name__}: {error}"
                results.append((name, result))
                print(f"{name}: {result}", file=sys.stderr)
            else:
                results.append((name, "pass"))
    finally:
        try:
            after = _counts(connection)
            print("row counts after:", after)
            changed = _diff_counts(before, after) if before else []
            if changed:
                detail = "; ".join(changed)
                results.append(("counts", f"fail: changed {detail}"))
                print("counts changed, rollback failed:", file=sys.stderr)
                for line in changed:
                    print(f"  {line}", file=sys.stderr)
            else:
                results.append(("counts", "pass"))
        except psycopg.Error as error:
            results.append(("counts", f"fail: could not read counts: {type(error).__name__}"))
            print(f"could not read counts after the run: {type(error).__name__}", file=sys.stderr)
        finally:
            connection.close()

    print("check results:")
    for name, result in results:
        print(f"  {name}: {result}")

    failed = [name for name, result in results if result != "pass"]
    if failed:
        print(f"failed checks: {', '.join(failed)}", file=sys.stderr)
        return 1
    print("all database checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
