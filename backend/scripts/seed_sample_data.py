"""Create or remove deliberately-labelled sample projects and analyses.

The migration credential is requested at run time and never read from a file or
environment variable, printed, or saved. Migrations contain no sample data; this
script is the only route to it and must be run on purpose.
"""

import argparse
import getpass
import sys

import psycopg

_STATES = ("queued", "running", "complete", "failed")
_PROJECT_NAME = "Sample project"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Create or remove sample projects and analyses for named teams."
    )
    parser.add_argument(
        "--team",
        action="append",
        dest="teams",
        required=True,
        metavar="TEAM_ID",
        help="Team identifier to write sample rows for. Repeat for each team.",
    )
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="Required acknowledgement that this writes sample data.",
    )
    parser.add_argument(
        "--remove",
        action="store_true",
        help="Remove only rows previously marked as samples for the named teams.",
    )
    return parser


def _connection_string() -> str:
    value = getpass.getpass("Migration role connection string: ").strip()
    if not value:
        raise ValueError("a connection string is required")
    return value


def _create_samples(connection: psycopg.Connection[tuple[object, ...]], teams: list[str]) -> int:
    created = 0
    with connection.transaction():
        for team_id in teams:
            existing = connection.execute(
                """
                select exists (
                    select 1
                    from public.projects
                    where team_id = %s and is_sample = true
                )
                """,
                (team_id,),
            ).fetchone()
            if existing is not None and existing[0] is True:
                raise RuntimeError(f"team {team_id} already has sample data; remove it first")

            project = connection.execute(
                """
                insert into public.projects (team_id, name, is_sample)
                values (%s, %s, true)
                returning id
                """,
                (team_id, _PROJECT_NAME),
            ).fetchone()
            assert project is not None
            project_id = project[0]

            for state in _STATES:
                connection.execute(
                    """
                    insert into public.analyses (team_id, project_id, state, is_sample)
                    values (%s, %s, %s, true)
                    """,
                    (team_id, project_id, state),
                )
                created += 1
    return created


def _remove_samples(connection: psycopg.Connection[tuple[object, ...]], teams: list[str]) -> int:
    removed = 0
    with connection.transaction():
        analyses = connection.execute(
            """
            delete from public.analyses
            where is_sample = true and team_id = any(%s)
            """,
            (teams,),
        )
        removed += analyses.rowcount

        projects = connection.execute(
            """
            delete from public.projects
            where is_sample = true and team_id = any(%s)
            """,
            (teams,),
        )
        removed += projects.rowcount
    return removed


def main() -> int:
    parser = _parser()
    arguments = parser.parse_args()

    teams = [team.strip() for team in arguments.teams if team.strip()]
    if not teams:
        parser.error("at least one non-blank team identifier is required")
    if not arguments.confirm:
        parser.error("--confirm is required; this script writes or removes data")

    try:
        connection_string = _connection_string()
    except ValueError, EOFError:
        print("No connection string entered. Nothing was changed.", file=sys.stderr)
        return 1

    try:
        with psycopg.connect(connection_string, connect_timeout=10) as connection:
            if arguments.remove:
                removed = _remove_samples(connection, teams)
                print(f"Removed {removed} sample rows for {len(teams)} team(s).")
            else:
                created = _create_samples(connection, teams)
                print(f"Created {created} sample analyses for {len(teams)} team(s).")
    except psycopg.Error:
        print("The database operation failed. No connection details were printed.", file=sys.stderr)
        return 1
    except RuntimeError as error:
        print(str(error), file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
