"""The two bounded-parsing limits."""

from pathlib import Path

import codecraft_parsing.common.walker as walker
import pytest
from codecraft_parsing import parse_repository
from codecraft_parsing.cli import main
from codecraft_parsing.common.walker import RepositoryLimitError


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def test_the_default_limits_are_the_contract_values() -> None:
    assert walker.MAX_FILE_COUNT == 50_000
    assert walker.MAX_FILE_BYTES == 2_000_000


def test_file_count_limit_fails_the_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(walker, "MAX_FILE_COUNT", 1)
    _write(tmp_path / "one.py", "VALUE = 1\n")
    _write(tmp_path / "two.py", "VALUE = 2\n")

    with pytest.raises(RepositoryLimitError, match="file limit"):
        parse_repository(tmp_path)


def test_file_size_limit_excludes_the_file_without_reading_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(walker, "MAX_FILE_BYTES", 10)
    _write(tmp_path / "big.py", "VALUE = 123456789\n")

    result = parse_repository(tmp_path)
    record = result.files[0]

    assert record.path == "big.py"
    assert not record.is_node
    assert record.excluded_reason == "file exceeds size limit"
    assert record.content_hash is None
    assert record.line_count is None
    assert result.coverage.references == 0


def test_an_import_of_an_oversized_file_is_excluded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(walker, "MAX_FILE_BYTES", 15)
    _write(tmp_path / "big.py", "VALUE = 123456789\n")
    _write(tmp_path / "app.py", "import big\n")

    result = parse_repository(tmp_path)

    assert [(record.reference, record.reason) for record in result.excluded_references] == [
        ("big", "file exceeds size limit")
    ]
    assert result.coverage.external == 0


def test_an_import_of_an_excluded_init_is_excluded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(walker, "MAX_FILE_BYTES", 20)
    _write(tmp_path / "pkg" / "__init__.py", 'VALUE = "this package init is too large"\n')
    _write(tmp_path / "pkg" / "mod.py", "VALUE = 1\n")
    _write(tmp_path / "app.py", "import pkg\n")

    result = parse_repository(tmp_path)

    assert [(record.reference, record.reason) for record in result.excluded_references] == [
        ("pkg", "file exceeds size limit")
    ]
    record = next(item for item in result.files if item.path == "pkg/mod.py")
    assert record.python is not None
    assert record.python.package_kind is not None
    assert record.python.package_kind.value == "regular"


def test_the_cli_reports_a_file_count_limit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(walker, "MAX_FILE_COUNT", 1)
    _write(tmp_path / "one.py", "VALUE = 1\n")
    _write(tmp_path / "two.py", "VALUE = 2\n")

    assert main([str(tmp_path)]) == 2
    assert "file limit" in capsys.readouterr().err
