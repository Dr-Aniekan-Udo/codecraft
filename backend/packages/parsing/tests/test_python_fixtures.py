"""The eight Part 3a fixtures, checked against output written before the parser ran."""

import json
import shutil
from pathlib import Path

import pytest
from codecraft_parsing import parse_repository

_FIXTURES = Path(__file__).resolve().parents[3] / "fixtures" / "python"

_FIXTURE_NAMES = (
    "01-flat-package",
    "02-relative-imports",
    "03-namespace-package",
    "04-shadowing",
    "05-guarded-and-dynamic",
    "06-syntax-error",
    "07-strings-and-comments",
    "08-symbol-import",
)


def test_the_part_3a_fixtures_exist() -> None:
    found = sorted(path.name for path in _FIXTURES.iterdir() if path.is_dir())
    assert found == list(_FIXTURE_NAMES)


@pytest.mark.parametrize("name", _FIXTURE_NAMES)
def test_fixture_output_matches_expected(name: str) -> None:
    fixture = _FIXTURES / name
    expected: object = json.loads((fixture / "expected.json").read_text(encoding="utf-8"))
    actual: object = parse_repository(fixture / "repo").model_dump(mode="json")
    assert actual == expected


def test_renaming_an_imported_module_leaves_one_unresolved_reference(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    shutil.copytree(_FIXTURES / "01-flat-package" / "repo", repo)
    (repo / "flatpkg" / "beta.py").rename(repo / "flatpkg" / "renamed.py")

    result = parse_repository(repo)

    assert len(result.unresolved_references) == 1
    unresolved = result.unresolved_references[0]
    assert unresolved.source == "flatpkg/alpha.py"
    assert unresolved.reference == "flatpkg.beta"
    assert unresolved.reason == "module not found in repository"
