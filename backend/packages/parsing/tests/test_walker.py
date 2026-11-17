"""File selection: nodes, excluded files and excluded directories."""

import os
from collections.abc import Iterator
from pathlib import Path
from typing import BinaryIO, cast

import pytest
from codecraft_core import AdapterRole, FileRecord, Language, PackageKind, PythonFileDetails
from codecraft_parsing import parse_repository
from codecraft_parsing.cli import main
from codecraft_parsing.common.walker import (
    UNREADABLE_DIRECTORY_REASON,
    UNREADABLE_FILE_REASON,
)


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def _python(record: FileRecord) -> PythonFileDetails:
    assert record.python is not None
    return record.python


def test_nodes_excluded_files_and_excluded_directories(tmp_path: Path) -> None:
    _write(tmp_path / "pkg" / "__init__.py", "")
    _write(tmp_path / "pkg" / "mod.py", "VALUE = 1\n")
    _write(tmp_path / "README.md", "# readme\n")
    _write(tmp_path / "pkg" / "types.pyi", "value: int\n")
    _write(tmp_path / "pkg" / "__pycache__" / "mod.cpython-314.pyc", "bytecode")

    result = parse_repository(tmp_path)
    by_path = {record.path: record for record in result.files}

    assert by_path["pkg/mod.py"].is_node
    assert _python(by_path["pkg/mod.py"]).package_kind == PackageKind.REGULAR
    assert _python(by_path["pkg/__init__.py"]).is_package
    assert by_path["README.md"].excluded_reason == "not a Python file"
    assert by_path["README.md"].content_hash is not None
    assert by_path["README.md"].adapter_role == AdapterRole.FALLBACK
    assert by_path["pkg/types.pyi"].excluded_reason == "stub file"
    assert by_path["pkg/types.pyi"].language == Language.PYTHON
    assert "pkg/__pycache__/mod.cpython-314.pyc" not in by_path

    assert [(entry.path, entry.reason) for entry in result.excluded_directories] == [
        ("pkg/__pycache__/", "bytecode cache")
    ]
    assert result.file_coverage.found == 4
    assert result.file_coverage.parsed == 2
    assert result.file_coverage.excluded == 2


def test_a_symlinked_file_is_excluded_and_never_read(tmp_path: Path) -> None:
    _write(tmp_path / "real.py", "VALUE = 1\n")
    link = tmp_path / "link.py"
    try:
        link.symlink_to(tmp_path / "real.py")
    except OSError:
        pytest.skip("symbolic links are not available on this machine")

    result = parse_repository(tmp_path)
    by_path = {record.path: record for record in result.files}

    assert by_path["link.py"].excluded_reason == "symbolic link"
    assert not by_path["link.py"].is_node
    assert by_path["link.py"].content_hash is None
    assert by_path["real.py"].is_node


def test_an_import_of_a_symlinked_file_is_excluded(tmp_path: Path) -> None:
    _write(tmp_path / "real.py", "VALUE = 1\n")
    link = tmp_path / "link.py"
    try:
        link.symlink_to(tmp_path / "real.py")
    except OSError:
        pytest.skip("symbolic links are not available on this machine")
    _write(tmp_path / "app.py", "import link\n")

    result = parse_repository(tmp_path)

    assert [(record.reference, record.reason) for record in result.excluded_references] == [
        ("link", "symbolic link")
    ]
    assert result.coverage.external == 0


def test_a_symlinked_directory_is_excluded_and_not_descended(tmp_path: Path) -> None:
    _write(tmp_path / "target" / "mod.py", "VALUE = 1\n")
    link = tmp_path / "linked"
    try:
        link.symlink_to(tmp_path / "target", target_is_directory=True)
    except OSError:
        pytest.skip("symbolic links are not available on this machine")

    result = parse_repository(tmp_path)
    by_path = {record.path: record for record in result.files}

    assert ("linked/", "symbolic link") in [
        (entry.path, entry.reason) for entry in result.excluded_directories
    ]
    assert not any(path.startswith("linked/") for path in by_path)
    assert by_path["target/mod.py"].is_node


def test_a_directory_link_loop_is_excluded(tmp_path: Path) -> None:
    _write(tmp_path / "pkg" / "mod.py", "VALUE = 1\n")
    loop = tmp_path / "pkg" / "loop"
    try:
        loop.symlink_to(tmp_path / "pkg", target_is_directory=True)
    except OSError:
        pytest.skip("symbolic links are not available on this machine")

    result = parse_repository(tmp_path)
    by_path = {record.path: record for record in result.files}

    assert ("pkg/loop/", "symbolic link") in [
        (entry.path, entry.reason) for entry in result.excluded_directories
    ]
    assert not any(path.startswith("pkg/loop/") for path in by_path)
    assert by_path["pkg/mod.py"].is_node


def test_a_committed_virtual_environment_is_excluded_as_third_party(tmp_path: Path) -> None:
    _write(tmp_path / "env" / "pyvenv.cfg", "home = /usr/bin\n")
    _write(tmp_path / "env" / "lib" / "site-packages" / "requests" / "__init__.py", "VALUE = 1\n")
    _write(tmp_path / "app.py", "import requests\n")

    result = parse_repository(tmp_path)
    by_path = {record.path: record for record in result.files}

    assert ("env/", "virtual environment") in [
        (entry.path, entry.reason) for entry in result.excluded_directories
    ]
    assert not any(path.startswith("env/") for path in by_path)
    assert [(record.reference, record.top_level) for record in result.external_references] == [
        ("requests", "requests")
    ]
    assert result.coverage.external == 1


def test_an_unreadable_directory_is_excluded_and_the_scan_is_incomplete(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A permission-denied directory is simulated for one directory.

    Windows usually needs elevation to create a directory that cannot be
    listed, so the test raises PermissionError from os.scandir for that one
    path. os.walk reaches the same handler with exactly that OSError.
    """
    _write(tmp_path / "app.py", "VALUE = 1\n")
    _write(tmp_path / "locked" / "hidden.py", "VALUE = 2\n")

    real_scandir = os.scandir

    def _scandir(path: str) -> Iterator[os.DirEntry[str]]:
        if path.endswith("locked"):
            raise PermissionError(13, "Permission denied", path)
        return real_scandir(path)

    monkeypatch.setattr(os, "scandir", _scandir)

    result = parse_repository(tmp_path)
    by_path = {record.path: record for record in result.files}

    assert ("locked/", UNREADABLE_DIRECTORY_REASON) in [
        (entry.path, entry.reason) for entry in result.excluded_directories
    ]
    assert by_path["app.py"].is_node
    assert not any(path.startswith("locked/") for path in by_path)

    assert main([str(tmp_path)]) == 0
    assert "scan: incomplete (1 directory could not be listed)" in capsys.readouterr().out


def test_an_unreadable_file_is_excluded_and_the_scan_is_incomplete(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A file that cannot be opened is simulated by raising where it is read.

    Windows usually needs elevation or a lock to make a real file unreadable,
    so this monkeypatch raises PermissionError for exactly one path. It is the
    deterministic substitute for the operating system refusing the open.
    """
    _write(tmp_path / "app.py", "VALUE = 1\n")
    _write(tmp_path / "locked.py", "VALUE = 2\n")

    real_open = Path.open

    def _open(path: Path, *_args: object, **_kwargs: object) -> BinaryIO:
        if path.name == "locked.py":
            raise PermissionError(13, "Permission denied", str(path))
        return cast("BinaryIO", real_open(path, "rb"))

    monkeypatch.setattr(Path, "open", _open)

    result = parse_repository(tmp_path)
    by_path = {record.path: record for record in result.files}

    locked = by_path["locked.py"]
    assert not locked.is_node
    assert locked.excluded_reason == UNREADABLE_FILE_REASON
    assert locked.content_hash is None
    assert locked.line_count is None
    assert by_path["app.py"].is_node

    assert main([str(tmp_path)]) == 0
    assert "scan: incomplete (1 file could not be read)" in capsys.readouterr().out
