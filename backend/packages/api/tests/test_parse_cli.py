"""The command-line entry point, and the output file it writes."""

import os
import subprocess
import sys
from pathlib import Path

import pytest
from codecraft_api.config import Settings
from codecraft_api.parse_cli import main
from codecraft_core import RepositoryParse

_ENV = {
    "DATABASE_URL": "postgresql://api@example/db",
    "MEMBERSHIP_SYNC_DATABASE_URL": "postgresql://sync@example/db",
    "CLERK_JWT_ISSUER": "https://clerk.example",
    "CLERK_WEBHOOK_SIGNING_SECRET": "whsec_c2VjcmV0",
    "CLERK_SECRET_KEY": "sk_test_secret",
    "CODECRAFT_FRONTEND_ORIGIN": "http://localhost:5173",
    "PARSE_MAX_FILES": "50000",
    "PARSE_MAX_FILE_BYTES": "2000000",
}

_PARSER_VERSION = (
    "codecraft-parsing 0.1.0 (language python; tree-sitter 0.26.0; tree-sitter-python 0.25.0)"
)


def _run(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "codecraft_api.parse_cli", *arguments],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
        env={**os.environ, **_ENV},
    )


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def _fake_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    # No real env file is read, and every required name has a fake value.
    monkeypatch.setitem(Settings.model_config, "env_file", None)
    for name, value in _ENV.items():
        monkeypatch.setenv(name, value)


def test_written_output_reads_back_with_every_field_and_type(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _write(repo / "helper.py", "VALUE = 1\n")
    _write(repo / "app.py", "import helper\n\nVALUE = 2\n")
    output = tmp_path / "output.json"
    assert repo.is_absolute()

    completed = _run(str(repo), "--output", str(output))

    assert completed.returncode == 0, completed.stderr
    assert "references" in completed.stdout
    raw = output.read_text(encoding="utf-8")
    assert raw.endswith("\n")
    parsed = RepositoryParse.model_validate_json(raw)
    assert parsed.parser_version == _PARSER_VERSION
    assert parsed.python is not None
    assert parsed.python.import_root == "."
    assert parsed.coverage.references == 1
    assert all(isinstance(record.line_count, int) for record in parsed.files)
    assert all(record.content_hash is not None for record in parsed.files)


def test_the_go_summary_reports_the_cgo_count(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _write(repo / "go.mod", "module example.com/app\n\ngo 1.22\n")
    _write(
        repo / "main.go",
        'package main\n\n/*\n#include <stdio.h>\n*/\nimport "C"\n\nfunc main() {}\n',
    )

    completed = _run(str(repo), "--language", "go")

    assert completed.returncode == 0, completed.stderr
    assert "1 cgo" in completed.stdout


def test_the_go_summary_reports_a_module_file_parse_failure(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _write(
        repo / "go.mod",
        "module example.com/app\ngo 1.22\nrequire (\n    example.com/dep v1.2.3\n",
    )
    _write(repo / "main.go", 'package main\n\nimport "example.com/app/pkg"\n\nfunc main() {}\n')
    _write(repo / "pkg" / "pkg.go", "package pkg\n")

    completed = _run(str(repo), "--language", "go")

    assert completed.returncode == 0, completed.stderr
    assert "parse failures:" in completed.stdout
    assert "malformed module file: 1" in completed.stdout


def test_a_missing_directory_exits_with_a_message(tmp_path: Path) -> None:
    completed = _run(str(tmp_path / "absent"))
    assert completed.returncode == 2
    assert completed.stderr.strip() != ""


def test_a_missing_parse_limit_exits_2_and_names_it(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _fake_environment(monkeypatch)
    monkeypatch.delenv("PARSE_MAX_FILES")

    assert main([str(tmp_path)]) == 2

    assert "PARSE_MAX_FILES" in capsys.readouterr().err


def test_the_file_limit_exits_2_with_the_limit_reason(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _fake_environment(monkeypatch)
    monkeypatch.setenv("PARSE_MAX_FILES", "1")
    _write(tmp_path / "one.py", "VALUE = 1\n")
    _write(tmp_path / "two.py", "VALUE = 2\n")

    assert main([str(tmp_path)]) == 2

    assert "repository exceeds the 1 file limit" in capsys.readouterr().err
