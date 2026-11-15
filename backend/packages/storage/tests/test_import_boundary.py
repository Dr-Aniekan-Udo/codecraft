"""Keep driver imports out of the API runtime packages.

The operator scripts under backend/scripts are not API runtime. They run with
the migration connection and deliberately open their own connection, so this
check covers the installed packages only.
"""

import ast
from pathlib import Path

_ALLOWED = "packages/storage/src/codecraft_storage/database.py"
_DRIVER_PACKAGES = {"psycopg", "psycopg_pool"}


def _imported_roots(tree: ast.Module) -> set[str]:
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            roots.add(node.module.split(".")[0])
    return roots


def test_only_the_connection_factory_imports_the_driver() -> None:
    backend_root = Path(__file__).resolve().parents[3]
    allowed = (backend_root / _ALLOWED).resolve()
    assert allowed.exists()

    offenders: list[str] = []
    for path in sorted((backend_root / "packages").glob("*/src/**/*.py")):
        if path.resolve() == allowed:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        if _imported_roots(tree) & _DRIVER_PACKAGES:
            offenders.append(path.relative_to(backend_root).as_posix())

    assert offenders == []
