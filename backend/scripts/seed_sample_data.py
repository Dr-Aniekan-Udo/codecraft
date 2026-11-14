"""Create or remove deliberately-labelled sample projects and analyses.

The three organisations are discovered from the membership table, so no
identifier is typed on the command line. The migration credential is requested
at run time and never read from a file or environment variable, printed, or
saved. Migrations contain no sample data; this script is the only route to it
and must be run on purpose.
"""

import argparse
import getpass
import sys
from datetime import datetime
from typing import NamedTuple

import psycopg

_ORGANISATION_COUNT = 3
_STATES = ("queued", "running", "complete", "failed")
_FLOWER_NAMES = (
    ("Aster", "Bluebell"),
    ("Camellia", "Dahlia"),
    ("Edelweiss", "Foxglove"),
)
_STATE_ORDERS = (
    ("complete", "complete", "running", "failed"),
    ("running", "complete", "running", "queued"),
    ("failed", "failed", "queued", "complete"),
)


class _ReportRow(NamedTuple):
    organisation_id: str
    project_names: str
    state_counts: tuple[int, int, int, int]


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Create or remove sample projects and analyses for the discovered organisations."
        )
    )
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="Required acknowledgement that this writes sample data.",
    )
    parser.add_argument(
        "--remove",
        action="store_true",
        help="Remove only rows previously marked as samples for the discovered organisations.",
    )
    return parser


def _connection_string() -> str:
    value = getpass.getpass("Migration role connection string: ").strip()
    if not value:
        raise ValueError("a connection string is required")
    return value


def _discover_organisations(
    connection: psycopg.Connection[tuple[object, ...]],
) -> list[str]:
    rows = connection.execute(
        "select distinct organisation_id from public.membership order by organisation_id"
    ).fetchall()

    organisations: list[str] = []
    for row in rows:
        value = row[0]
        if not isinstance(value, str) or not value.strip():
            raise RuntimeError("a membership row has a blank organisation identifier")
        organisations.append(value)

    if len(organisations) != _ORGANISATION_COUNT:
        raise RuntimeError(
            f"expected {_ORGANISATION_COUNT} organisations, found {len(organisations)}; "
            "nothing was changed"
        )
    return organisations


def _has_sample_rows(
    connection: psycopg.Connection[tuple[object, ...]], organisation_id: str
) -> bool:
    row = connection.execute(
        """
        select exists (
            select 1
            from public.projects
            where organisation_id = %s and is_sample = true
        ) or exists (
            select 1
            from public.analyses
            where organisation_id = %s and is_sample = true
        )
        """,
        (organisation_id, organisation_id),
    ).fetchone()
    return row is not None and row[0] is True


def _verify_samples(
    connection: psycopg.Connection[tuple[object, ...]], organisations: list[str]
) -> list[_ReportRow]:
    expected_names = {name for names in _FLOWER_NAMES for name in names}
    report: list[_ReportRow] = []
    seen_names: list[str] = []
    newest_analyses: list[datetime] = []
    state_vectors: list[tuple[int, int, int, int]] = []

    for organisation_id in organisations:
        project_rows = connection.execute(
            """
            select name, is_sample
            from public.projects
            where organisation_id = %s
            order by created_at
            """,
            (organisation_id,),
        ).fetchall()
        if len(project_rows) != 2:
            raise RuntimeError(
                f"organisation {organisation_id} has {len(project_rows)} projects, expected 2"
            )

        project_names: list[str] = []
        for row in project_rows:
            name = row[0]
            is_sample = row[1]
            if not isinstance(name, str) or is_sample is not True:
                raise RuntimeError(
                    f"organisation {organisation_id} has a project that is not a labelled sample"
                )
            project_names.append(name)

        analysis_rows = connection.execute(
            """
            select state, is_sample, created_at
            from public.analyses
            where organisation_id = %s
            """,
            (organisation_id,),
        ).fetchall()
        if len(analysis_rows) != 4:
            raise RuntimeError(
                f"organisation {organisation_id} has {len(analysis_rows)} analyses, expected 4"
            )

        state_counts = dict.fromkeys(_STATES, 0)
        newest_analysis: datetime | None = None
        for row in analysis_rows:
            state = row[0]
            is_sample = row[1]
            created_at = row[2]
            if (
                not isinstance(state, str)
                or state not in state_counts
                or is_sample is not True
                or not isinstance(created_at, datetime)
            ):
                raise RuntimeError(
                    f"organisation {organisation_id} has an analysis that is not a labelled sample"
                )
            state_counts[state] += 1
            if newest_analysis is None or created_at > newest_analysis:
                newest_analysis = created_at

        if newest_analysis is None:
            raise RuntimeError(f"organisation {organisation_id} has no analyses")

        counts = (
            state_counts["queued"],
            state_counts["running"],
            state_counts["complete"],
            state_counts["failed"],
        )
        state_vectors.append(counts)
        newest_analyses.append(newest_analysis)
        seen_names.extend(project_names)
        report.append(_ReportRow(organisation_id, ", ".join(project_names), counts))

    if len(seen_names) != len(expected_names):
        raise RuntimeError(
            f"the three organisations hold {len(seen_names)} project names, expected "
            f"{len(expected_names)}"
        )
    if len(set(seen_names)) != len(seen_names):
        raise RuntimeError("project names are not globally unique across the three organisations")
    if set(seen_names) != expected_names:
        raise RuntimeError("project names are not the fixed six flower names")
    if any("sample" in name.lower() for name in seen_names):
        raise RuntimeError("a project name contains the word sample")
    if len(set(state_vectors)) != len(state_vectors):
        raise RuntimeError("the organisations do not have distinct state count vectors")
    if len(set(newest_analyses)) != len(newest_analyses):
        raise RuntimeError("the organisations do not have distinct newest analysis times")

    return report


def _print_report(report: list[_ReportRow]) -> None:
    print(
        f"{'organisation_id':<16} {'project_names':<23} "
        f"{'queued':>6} {'running':>7} {'complete':>8} {'failed':>6}"
    )
    for row in report:
        queued, running, complete, failed = row.state_counts
        print(
            f"{row.organisation_id:<16} {row.project_names:<23} "
            f"{queued:>6} {running:>7} {complete:>8} {failed:>6}"
        )


def _create_samples(
    connection: psycopg.Connection[tuple[object, ...]],
) -> list[_ReportRow]:
    with connection.transaction():
        organisations = _discover_organisations(connection)
        for organisation_id in organisations:
            if _has_sample_rows(connection, organisation_id):
                raise RuntimeError(
                    f"organisation {organisation_id} already has sample rows; remove them first"
                )

        for organisation_index, organisation_id in enumerate(organisations):
            for project_index, project_name in enumerate(_FLOWER_NAMES[organisation_index]):
                project = connection.execute(
                    """
                    insert into public.projects (organisation_id, name, created_at, is_sample)
                    values (%s, %s, now() - make_interval(hours => %s), true)
                    returning id
                    """,
                    (organisation_id, project_name, organisation_index * 4 + 6 + project_index),
                ).fetchone()
                if project is None:
                    raise RuntimeError(
                        f"the sample project insert for organisation {organisation_id} "
                        "returned no identifier"
                    )
                project_id = project[0]

                for position in (project_index * 2, project_index * 2 + 1):
                    connection.execute(
                        """
                        insert into public.analyses (
                            organisation_id, project_id, state, created_at, is_sample
                        )
                        values (%s, %s, %s, now() - make_interval(hours => %s), true)
                        """,
                        (
                            organisation_id,
                            project_id,
                            _STATE_ORDERS[organisation_index][position],
                            organisation_index * 4 + position + 1,
                        ),
                    )

        return _verify_samples(connection, organisations)


def _remove_samples(connection: psycopg.Connection[tuple[object, ...]]) -> int:
    with connection.transaction():
        organisations = _discover_organisations(connection)

        analyses = connection.execute(
            """
            delete from public.analyses
            where is_sample = true and organisation_id = any(%s)
            """,
            (organisations,),
        )
        removed = analyses.rowcount

        projects = connection.execute(
            """
            delete from public.projects
            where is_sample = true and organisation_id = any(%s)
            """,
            (organisations,),
        )
        removed += projects.rowcount
    return removed


def main() -> int:
    parser = _parser()
    arguments = parser.parse_args()

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
                removed = _remove_samples(connection)
                print(f"Removed {removed} sample rows.")
            else:
                report = _create_samples(connection)
                _print_report(report)
    except psycopg.Error:
        print("The database operation failed. No connection details were printed.", file=sys.stderr)
        return 1
    except RuntimeError as error:
        print(str(error), file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
