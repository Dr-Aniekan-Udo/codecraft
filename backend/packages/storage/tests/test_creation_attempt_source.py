"""Keep the creation-attempt table inside the connection factory.

The migration fixes the table's policies and grants. Naming the table in one
module means the API route cannot drift into raw SQL that skips the claims and
the advisory lock the store sets up for every attempt.
"""

from pathlib import Path

_TABLE = "organisation_creation_attempts"
_ALLOWED = "packages/storage/src/codecraft_storage/database.py"


def test_only_the_connection_factory_names_the_attempt_table() -> None:
    backend_root = Path(__file__).resolve().parents[3]
    allowed = (backend_root / _ALLOWED).resolve()
    test_file = Path(__file__).resolve()
    assert allowed.exists()

    offenders: list[str] = []
    for directory in ("packages", "scripts"):
        for path in sorted((backend_root / directory).rglob("*.py")):
            resolved = path.resolve()
            if resolved in {allowed, test_file}:
                continue
            if _TABLE in path.read_text(encoding="utf-8"):
                offenders.append(path.relative_to(backend_root).as_posix())

    assert offenders == []

    # Inside database.py the name is allowed only in the private store that is
    # bound to the creation connection. Another method in the same module would
    # otherwise be able to open a separate connection and skip the lock.
    source = allowed.read_text(encoding="utf-8").splitlines()
    store_start = next(
        index
        for index, line in enumerate(source, start=1)
        if line.startswith("class _CreationAttemptStore:")
    )
    database_start = next(
        index for index, line in enumerate(source, start=1) if line.startswith("class Database:")
    )
    for index, line in enumerate(source, start=1):
        if _TABLE in line:
            assert store_start <= index < database_start, (
                f"{_TABLE} appears at database.py:{index} outside _CreationAttemptStore"
            )
