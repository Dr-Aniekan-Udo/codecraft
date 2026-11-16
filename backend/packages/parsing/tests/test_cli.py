"""The command-line entry point, and the output file it writes."""

import subprocess
import sys
from pathlib import Path

from codecraft_core import RepositoryParse

_FIXTURES = Path(__file__).resolve().parents[3] / "fixtures" / "python"

_PARSER_VERSION = (
    "codecraft-parsing 0.1.0 (language python; tree-sitter 0.26.0; tree-sitter-python 0.25.0)"
)


def _run(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "codecraft_parsing", *arguments],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )


def test_written_output_reads_back_with_every_field_and_type(tmp_path: Path) -> None:
    repo = _FIXTURES / "01-flat-package" / "repo"
    output = tmp_path / "output.json"

    completed = _run(str(repo), "--output", str(output))

    assert completed.returncode == 0, completed.stderr
    assert "references" in completed.stdout
    raw = output.read_text(encoding="utf-8")
    assert raw.endswith("\n")
    parsed = RepositoryParse.model_validate_json(raw)
    assert parsed.parser_version == _PARSER_VERSION
    assert parsed.python is not None
    assert parsed.python.import_root == "."
    assert parsed.coverage.references == 3
    assert all(isinstance(record.line_count, int) for record in parsed.files)
    assert all(record.content_hash is not None for record in parsed.files)


def test_a_missing_directory_exits_with_a_message(tmp_path: Path) -> None:
    completed = _run(str(tmp_path / "absent"))
    assert completed.returncode == 2
    assert completed.stderr.strip() != ""
