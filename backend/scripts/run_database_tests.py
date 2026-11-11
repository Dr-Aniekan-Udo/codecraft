"""Run the database security checks against the linked Supabase project.

Every check runs in a transaction that is always rolled back. The connection
string is requested with hidden input, checked against the linked project, used
for this process only, and never printed or written anywhere.
"""

import argparse
import getpass
import json
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
_ALLOWED_TABLE_PRIVILEGES = frozenset(
    {"SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE", "REFERENCES", "TRIGGER", "MAINTAIN"}
)
_STATES = ("queued", "running", "complete", "failed")
# The deletion fixture inserts these rows for each team. The files table gets
# two rows because every fixture edge has a source file and a target file.
_FIXTURE_ROWS = {
    "projects": 1,
    "analyses": 1,
    "files": 2,
    "edges": 1,
    "routes": 1,
    "explanations": 1,
    "file_roles": 1,
    "insights": 1,
}
_FUNCTION = "public.delete_team_rows(text)"
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


def _counts(connection: Connection[tuple[object, ...]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    with connection.transaction():
        for table in _ALL_TABLES:
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


def _existing_membership(
    connection: Connection[tuple[object, ...]],
) -> tuple[str, str]:
    row = connection.execute(
        """
        select user_id, team_id
        from public.membership
        order by user_id, team_id
        limit 1
        """
    ).fetchone()
    _require(row is not None, "no membership row exists to test the member policy")
    assert row is not None
    user_id, team_id = row
    _require(
        isinstance(user_id, str) and isinstance(team_id, str),
        "the membership row has unexpected types",
    )
    return user_id, team_id


def _returned_id(row: tuple[object, ...] | None) -> object:
    _require(row is not None, "an insert returned no row")
    assert row is not None
    return row[0]


def _insert_team_rows(
    connection: Connection[tuple[object, ...]], team_id: str, project_name: str
) -> None:
    project_id = _returned_id(
        connection.execute(
            "insert into public.projects (team_id, name) values (%s, %s) returning id",
            (team_id, project_name),
        ).fetchone()
    )
    analysis_id = _returned_id(
        connection.execute(
            """
            insert into public.analyses (team_id, project_id, state)
            values (%s, %s, 'complete')
            returning id
            """,
            (team_id, project_id),
        ).fetchone()
    )
    source_file_id = _returned_id(
        connection.execute(
            """
            insert into public.files (team_id, analysis_id, path)
            values (%s, %s, %s)
            returning id
            """,
            (team_id, analysis_id, "src/source.ts"),
        ).fetchone()
    )
    target_file_id = _returned_id(
        connection.execute(
            """
            insert into public.files (team_id, analysis_id, path)
            values (%s, %s, %s)
            returning id
            """,
            (team_id, analysis_id, "src/target.ts"),
        ).fetchone()
    )
    connection.execute(
        """
        insert into public.edges (team_id, analysis_id, source_file_id, target_file_id, kind)
        values (%s, %s, %s, %s, 'import')
        """,
        (team_id, analysis_id, source_file_id, target_file_id),
    )
    connection.execute(
        """
        insert into public.routes (team_id, analysis_id, file_id, method, path)
        values (%s, %s, %s, 'GET', '/sample')
        """,
        (team_id, analysis_id, source_file_id),
    )
    connection.execute(
        """
        insert into public.explanations (team_id, analysis_id, file_id, content_hash, body)
        values (%s, %s, %s, 'hash', 'body')
        """,
        (team_id, analysis_id, source_file_id),
    )
    connection.execute(
        """
        insert into public.file_roles (team_id, analysis_id, file_id, role)
        values (%s, %s, %s, 'page')
        """,
        (team_id, analysis_id, source_file_id),
    )
    connection.execute(
        """
        insert into public.insights (team_id, analysis_id, kind, detail)
        values (%s, %s, 'cycle', '{}'::jsonb)
        """,
        (team_id, analysis_id),
    )


def _count_for_team(connection: Connection[tuple[object, ...]], table: str, team_id: str) -> int:
    return _integer(
        connection.execute(
            sql.SQL("select count(*) from public.{} where team_id = %s").format(_identifier(table)),
            (team_id,),
        ).fetchone()
    )


def _count_all(connection: Connection[tuple[object, ...]], table: str) -> int:
    return _integer(
        connection.execute(
            sql.SQL("select count(*) from public.{}").format(_identifier(table))
        ).fetchone()
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
    _require(table_names == set(_ALL_TABLES), "the exposed table set changed")

    policy_rows = connection.execute(
        """
        select tablename, count(*)
        from pg_policies
        where schemaname in ('public', 'graphql_public') and cmd in ('SELECT', 'ALL')
        group by tablename
        """
    ).fetchall()
    policy_counts = {row[0]: row[1] for row in policy_rows}
    _require(
        policy_counts == {table: 1 for table in _ALL_TABLES},
        "an exposed table does not have exactly one select policy",
    )

    owners = {row[0]: row[2] for row in tables}
    for table, row_security, _ in tables:
        _require(row_security is True, f"row-level security is disabled on {table}")

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
    for table, grantee, privilege in privileges:
        _require(
            isinstance(table, str) and isinstance(grantee, str) and isinstance(privilege, str),
            "a table privilege row has an unexpected type",
        )
        _require(
            privilege in _ALLOWED_TABLE_PRIVILEGES,
            f"unknown privilege {privilege} on {table}",
        )
        allowed = grantee == owners[table] or (grantee == "authenticated" and privilege == "SELECT")
        _require(allowed, f"{grantee} holds {privilege} on {table}")
        if grantee == "codecraft_membership_sync":
            sync_grants[table].append(privilege)

    function_privileges = connection.execute(
        """
        select coalesce(grantee.rolname, 'PUBLIC'), acl.privilege_type
        from pg_proc as p
        join pg_namespace as n on n.oid = p.pronamespace
        cross join lateral aclexplode(
          coalesce(p.proacl, acldefault('f', p.proowner))
        ) as acl
        left join pg_roles as grantee on grantee.oid = acl.grantee
        where n.nspname = 'public' and p.proname = 'delete_team_rows'
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
    print("  delete_team_rows: execute=sync only; public, anon, authenticated, service_role absent")


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
        # The member is taken from the real membership table, so the test never
        # writes a membership row. That table belongs to the sync role.
        member_user, member_team = _existing_membership(connection)
        other_team = f"org_other_{suffix}"
        non_member = f"user_non_member_{suffix}"

        non_member_exists = connection.execute(
            "select exists (select 1 from public.membership where user_id = %s)",
            (non_member,),
        ).fetchone()
        _require(
            non_member_exists is not None and non_member_exists[0] is False,
            "the generated non-member already has a membership",
        )

        _insert_team_rows(connection, member_team, "project-member")
        _insert_team_rows(connection, other_team, "project-other")

        def member_checks() -> None:
            for table in _TABLES:
                _require(
                    _count_for_team(connection, table, member_team) >= 1,
                    f"member cannot read its own {table} row",
                )
                _require(
                    _count_for_team(connection, table, other_team) == 0,
                    f"member can read another team's {table} row",
                )

        _as_user(connection, member_user, member_checks)

        def non_member_checks() -> None:
            for table in _TABLES:
                _require(
                    _count_for_team(connection, table, member_team) == 0,
                    f"non-member can read {table} rows",
                )
                _require(
                    _count_all(connection, table) == 0,
                    f"non-member sees unexpected {table} rows",
                )

        _as_user(connection, non_member, non_member_checks)

    print("policy checks: member sees own team only; non-member sees nothing")


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
    team_a = f"org_a_{suffix}"
    team_b = f"org_b_{suffix}"

    with connection.transaction(force_rollback=True):
        print(f"deletion fixture teams: team_a={team_a} team_b={team_b}")
        print(f"deletion fixture rows per team: {_FIXTURE_ROWS}")
        _insert_team_rows(connection, team_a, "project-a")
        _insert_team_rows(connection, team_b, "project-b")
        membership_before = _count_all(connection, "membership")

        # The connection role owns the routine and the eight tables, so it can
        # execute the cleanup directly. The catalog check separately proves the
        # sync role is the only other role with EXECUTE.
        deleted_rows = connection.execute(
            "select * from public.delete_team_rows(%s)", (team_a,)
        ).fetchall()

        counts: dict[str, int] = {}
        for row in deleted_rows:
            _require(len(row) == 2, "the cleanup routine returned an unexpected row")
            table_name, deleted = row
            _require(isinstance(table_name, str) and isinstance(deleted, int), "bad row")
            counts[table_name] = deleted

        _require_fixture_counts(_FIXTURE_ROWS, counts)
        for table in _TABLES:
            _require(_count_for_team(connection, table, team_a) == 0, f"{table} was not removed")
            _require(
                _count_for_team(connection, table, team_b) == _FIXTURE_ROWS[table],
                f"{table} of the other team changed",
            )
        _require(
            _count_all(connection, "membership") == membership_before,
            "membership rows changed",
        )

    print("deletion checks: named team removed across eight tables; other team and membership kept")


def _check_function_guards(connection: Connection[tuple[object, ...]]) -> None:
    for team_id in (None, "", "   "):
        with connection.transaction(force_rollback=True):
            try:
                connection.execute("select * from public.delete_team_rows(%s)", (team_id,))
            except errors.RaiseException:
                continue
            raise CheckFailed("the cleanup routine accepted a null or empty identifier")
    print("function guard checks: null and empty identifiers refused")


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
