"""Go fixtures, checked against output written before the parser."""

import json
import shutil
from collections.abc import Iterable
from pathlib import Path
from typing import Protocol, cast

import pytest
from codecraft_parsing import parse_repository
from jsonschema import Draft202012Validator  # pyright: ignore[reportMissingTypeStubs]

_REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
_SCHEMA_PATH = _REPOSITORY_ROOT / "docs" / "contracts" / "parser-output.schema.json"
_FIXTURES = _REPOSITORY_ROOT / "backend" / "fixtures" / "go"

_BASE_GO_FIXTURE_NAMES = (
    "01-package-edges",
    "02-external-and-unresolved",
    "03-build-constraints",
    "04-test-files",
    "05-vendor-and-testdata",
    "06-alias-blank-dot",
    "07-workspace-modules",
    "08-local-replace",
    "09-module-prefix",
)

_GO_FIXTURE_NAMES = (
    *_BASE_GO_FIXTURE_NAMES,
    "10-nested-module",
    "11-major-version",
    "12-replacement-targets",
    "13-module-file-syntax",
    "14-no-module-file",
    "15-ignored-folders",
    "16-cgo",
    "17-main-package-import",
    "18-conflicting-packages",
    "19-generated-file",
    "20-malformed-module",
    "21-ignored-module-directives",
    "22-module-file-over-replace",
    "23-grammar-failure-reasons",
    "24-malformed-module-no-path",
    "25-folder-without-package-name",
    "26-conflict-with-parse-failure",
    "27-malformed-module-external",
    "28-readable-imports-in-failed-file",
    "29-imports-in-damaged-body",
    "30-conflicting-file-with-imports",
    "31-malformed-import-spec",
    "32-legacy-build-precedence",
    "33-deep-build-expression",
    "34-underscore-file",
    "35-quoted-replace-path",
    "36-workspace-replacement-override",
    "37-non-test-helper-test",
    "38-malformed-root-nested-tools",
    "39-nested-module-ownership",
    "40-unrecognised-build-character",
    "41-replacement-over-module",
    "42-longer-external-route",
    "43-failed-nested-module-boundary",
)


def _document() -> dict[str, object]:
    return cast(
        "dict[str, object]",
        json.loads(_SCHEMA_PATH.read_text(encoding="utf-8")),
    )


class _ValidationError(Protocol):
    @property
    def message(self) -> str: ...


def _schema_errors(value: object) -> list[str]:
    validator = cast(
        "_Validator",
        Draft202012Validator(_document()),
    )
    return [error.message for error in validator.iter_errors(value)]


class _Validator(Protocol):
    def iter_errors(self, instance: object) -> Iterable[_ValidationError]: ...


def test_every_go_fixture_directory_exists() -> None:
    missing = [name for name in _GO_FIXTURE_NAMES if not (_FIXTURES / name).is_dir()]
    assert missing == []


def test_every_base_go_fixture_directory_exists() -> None:
    missing = [name for name in _BASE_GO_FIXTURE_NAMES if not (_FIXTURES / name).is_dir()]
    assert missing == []


@pytest.mark.parametrize("name", _GO_FIXTURE_NAMES)
def test_the_expected_output_matches_the_schema(name: str) -> None:
    expected: object = json.loads((_FIXTURES / name / "expected.json").read_text(encoding="utf-8"))
    assert _schema_errors(expected) == []


@pytest.mark.parametrize("name", _GO_FIXTURE_NAMES)
def test_the_go_fixture_output_matches_expected(name: str) -> None:
    fixture = _FIXTURES / name
    actual = json.dumps(
        parse_repository(fixture / "repo", "go").model_dump(mode="json"),
        indent=2,
        ensure_ascii=False,
    )
    actual += "\n"
    expected = (fixture / "expected.json").read_text(encoding="utf-8")

    assert actual == expected
    assert _schema_errors(json.loads(actual)) == []


def test_renaming_a_package_leaves_one_unresolved_reference(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    shutil.copytree(_FIXTURES / "01-package-edges" / "repo", repo)
    (repo / "pkg").rename(repo / "renamed")

    result = parse_repository(repo, "go")

    assert len(result.unresolved_references) == 1
    unresolved = result.unresolved_references[0]
    assert unresolved.source == "cmd/main.go"
    assert unresolved.reference == "example.com/app/pkg"
    assert unresolved.reason == "package folder not found in repository"
