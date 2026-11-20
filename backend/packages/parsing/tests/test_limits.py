"""The two bounded-parsing limits."""

import io
from collections.abc import Callable
from pathlib import Path

import codecraft_parsing.common.walker as walker
import pytest
from codecraft_core import RepositoryParse
from codecraft_parsing import parse_repository as _parse_repository
from codecraft_parsing.common.walker import RepositoryLimitError


def parse_repository(
    root: Path,
    language: str = "python",
    *,
    max_file_count: int = 50_000,
    max_file_bytes: int = 2_000_000,
) -> RepositoryParse:
    return _parse_repository(
        root,
        language,
        max_file_count=max_file_count,
        max_file_bytes=max_file_bytes,
    )


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def test_file_count_limit_fails_the_run(tmp_path: Path) -> None:
    _write(tmp_path / "one.py", "VALUE = 1\n")
    _write(tmp_path / "two.py", "VALUE = 2\n")

    with pytest.raises(RepositoryLimitError, match="file limit"):
        parse_repository(tmp_path, max_file_count=1)


def test_file_count_at_the_limit_succeeds(tmp_path: Path) -> None:
    _write(tmp_path / "one.py", "VALUE = 1\n")
    _write(tmp_path / "two.py", "VALUE = 2\n")

    result = parse_repository(tmp_path, max_file_count=2)

    assert result.file_coverage.found == 2
    assert result.file_coverage.parsed == 2


class _RecordingStream(io.BytesIO):
    """A fake binary file that reports the size each read asked for."""

    def __init__(self, data: bytes) -> None:
        super().__init__(data)
        self.requested: list[int] = []

    def read(self, size: int | None = -1) -> bytes:
        self.requested.append(-1 if size is None else size)
        return super().read(size)


def _open_stream(stream: io.BytesIO) -> Callable[..., io.BytesIO]:
    def _open(*_args: object, **_kwargs: object) -> io.BytesIO:
        return stream

    return _open


def test_the_capped_read_asks_for_at_most_the_limit_plus_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A handle that is longer than the size check saw proves the read itself is
    # capped: the helper never asks for the whole file.
    path = tmp_path / "growing.bin"
    path.write_bytes(b"")

    accepted = _RecordingStream(b"x" * 10)
    monkeypatch.setattr(Path, "open", _open_stream(accepted))
    assert walker.read_within_limit(path, 10) == b"x" * 10
    assert accepted.requested == [11]

    rejected = _RecordingStream(b"x" * 11)
    monkeypatch.setattr(Path, "open", _open_stream(rejected))
    assert walker.read_within_limit(path, 10) is None
    assert rejected.requested == [11]


def test_file_size_limit_excludes_the_file_through_the_capped_read(tmp_path: Path) -> None:
    _write(tmp_path / "big.py", "VALUE = 123456789\n")

    result = parse_repository(tmp_path, max_file_bytes=10)
    record = result.files[0]

    assert record.path == "big.py"
    assert not record.is_node
    assert record.excluded_reason == "file exceeds size limit"
    assert record.content_hash is None
    assert record.line_count is None
    assert result.coverage.references == 0


def test_an_import_of_an_oversized_file_is_excluded(tmp_path: Path) -> None:
    _write(tmp_path / "big.py", "VALUE = 123456789\n")
    _write(tmp_path / "app.py", "import big\n")

    result = parse_repository(tmp_path, max_file_bytes=15)

    assert [(record.reference, record.reason) for record in result.excluded_references] == [
        ("big", "file exceeds size limit")
    ]
    assert result.coverage.external == 0


def test_an_import_of_an_excluded_init_is_excluded(tmp_path: Path) -> None:
    _write(tmp_path / "pkg" / "__init__.py", 'VALUE = "this package init is too large"\n')
    _write(tmp_path / "pkg" / "mod.py", "VALUE = 1\n")
    _write(tmp_path / "app.py", "import pkg\n")

    result = parse_repository(tmp_path, max_file_bytes=20)

    assert [(record.reference, record.reason) for record in result.excluded_references] == [
        ("pkg", "file exceeds size limit")
    ]
    record = next(item for item in result.files if item.path == "pkg/mod.py")
    assert record.python is not None
    assert record.python.package_kind is not None
    assert record.python.package_kind.value == "regular"
