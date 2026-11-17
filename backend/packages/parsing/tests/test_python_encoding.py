"""Encoding failures stay with the file that produced them."""

from pathlib import Path

from codecraft_parsing import parse_repository


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def test_a_source_that_cannot_be_encoded_as_utf8_is_a_parse_failure(tmp_path: Path) -> None:
    # unicode_escape decodes the literal backslash-u sequence into a lone
    # surrogate, which the grammar cannot receive because Python text is UTF-8.
    (tmp_path / "bad.py").write_bytes(b'# -*- coding: unicode_escape -*-\nNAME = "\\ud800"\n')
    _write(tmp_path / "good.py", "import other\n")
    _write(tmp_path / "other.py", "VALUE = 1\n")

    result = parse_repository(tmp_path)
    by_path = {record.path: record for record in result.files}

    bad = by_path["bad.py"]
    assert bad.is_node
    assert bad.parse_failure is not None
    assert bad.parse_failure.reason == "cannot encode source as UTF-8"
    assert bad.parse_failure.line is None
    assert bad.parse_failure.column is None
    assert not any(edge.source == "bad.py" for edge in result.edges)

    assert by_path["good.py"].parse_failure is None
    assert by_path["other.py"].parse_failure is None
    assert [(edge.source, edge.target) for edge in result.edges] == [("good.py", "other.py")]


def test_a_source_that_cannot_be_decoded_still_carries_its_parse_failure(tmp_path: Path) -> None:
    (tmp_path / "bad.py").write_bytes(b"VALUE = \xff\xfe\n")

    result = parse_repository(tmp_path)
    by_path = {record.path: record for record in result.files}

    bad = by_path["bad.py"]
    assert bad.is_node
    assert bad.parse_failure is not None
    assert bad.parse_failure.reason == "cannot decode source"
    assert bad.parse_failure.line is None
    assert bad.parse_failure.column is None
    assert result.edges == []
