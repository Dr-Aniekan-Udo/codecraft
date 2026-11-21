"""TypeScript and JavaScript fixtures, checked against hand-written output."""

import json
import os
import subprocess
from pathlib import Path

import pytest
from codecraft_core import RepositoryParse
from codecraft_parsing import parse_repository as _parse_repository
from codecraft_parsing.typescript.resolver import ResolverFailure, resolve_references


def parse_repository(
    root: Path,
    language: str = "typescript",
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


_FIXTURES = Path(__file__).resolve().parents[3] / "fixtures" / "typescript"

_FIXTURE_NAMES = (
    "01-barrel-files",
    "02-path-aliases-extends",
    "03-nearest-configuration",
    "04-type-only-dynamic",
    "05-declaration-files",
    "06-mixed-languages",
    "07-dependency-folder",
    "08-asset-imports",
    "09-workspace-package",
)


def test_every_typescript_fixture_directory_exists() -> None:
    found = sorted(path.name for path in _FIXTURES.iterdir() if path.is_dir())
    assert found == list(_FIXTURE_NAMES)


@pytest.mark.parametrize("name", _FIXTURE_NAMES)
def test_fixture_output_matches_expected(name: str) -> None:
    fixture = _FIXTURES / name
    expected: object = json.loads((fixture / "expected.json").read_text(encoding="utf-8"))
    actual: object = parse_repository(fixture / "repo").model_dump(mode="json")
    assert actual == expected


def test_the_javascript_selector_uses_the_same_parser() -> None:
    fixture = _FIXTURES / "06-mixed-languages"
    expected: object = json.loads((fixture / "expected.json").read_text(encoding="utf-8"))
    actual: object = parse_repository(fixture / "repo", "javascript").model_dump(mode="json")
    assert actual == expected


def test_a_package_name_extends_and_workspace_import_need_no_node_modules() -> None:
    fixture = _FIXTURES / "09-workspace-package" / "repo"
    assert not (fixture / "node_modules").exists()

    result = parse_repository(fixture)

    assert result.typescript is not None
    assert result.typescript.config_files == ("apps/app/tsconfig.json",)
    by_target = {edge.target: edge for edge in result.edges}
    assert by_target["packages/ui/index.ts"].resolution_path == "workspace_package"
    assert by_target["apps/app/lib/helper.ts"].resolution_path == "path_alias"
    assert by_target["packages/ui/src/nested.ts"].resolution_path == "path_alias"
    assert "packages/ui/nested.ts" not in by_target
    assert result.coverage.failed == 1
    assert result.unresolved_references[0].reason == ("workspace package subpath is not exported")


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def test_type_only_boundary_keeps_value_imports_separate() -> None:
    result = parse_repository(_FIXTURES / "04-type-only-dynamic" / "repo")
    types_edges = [edge for edge in result.edges if edge.target == "src/types.ts"]
    assert {(edge.kind.value, edge.line) for edge in types_edges} == {
        ("import", 4),
        ("type_only_import", 1),
    }


def test_generated_file_is_excluded_and_its_import_is_an_excluded_reference() -> None:
    result = parse_repository(_FIXTURES / "05-declaration-files" / "repo")
    generated = next(record for record in result.files if record.path == "src/generated.ts")
    assert generated.is_node is False
    assert generated.excluded_reason == "generated file: @generated"
    assert result.unresolved_references == []
    assert [record.reason for record in result.excluded_references] == [
        "generated file: @generated"
    ]
    assert all(edge.target != "src/generated.ts" for edge in result.edges)


def test_asset_reexport_and_bare_asset_classification() -> None:
    result = parse_repository(_FIXTURES / "08-asset-imports" / "repo")
    styles_reexport = [
        edge
        for edge in result.edges
        if edge.target == "src/styles.css" and edge.kind.value == "re_export"
    ]
    assert len(styles_reexport) == 1
    assert styles_reexport[0].resolution_path == "asset"
    assert result.coverage.typescript is not None
    assert result.coverage.typescript.re_exports == 1
    assert result.coverage.typescript.re_exports_resolved == 1
    query = [edge for edge in result.edges if edge.target == "src/query.css"]
    assert len(query) == 1
    assert query[0].resolution_path == "asset"
    assert any(record.top_level == "some-package" for record in result.external_references)


def test_dependency_target_is_an_excluded_reference(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _write(repo / "node_modules/pkg/index.js", "module.exports = 1;\n")
    _write(repo / "src/main.ts", 'import "../node_modules/pkg/index.js";\n')

    result = parse_repository(repo)

    assert result.edges == []
    assert result.external_references == []
    assert [record.reason for record in result.excluded_references] == ["dependency installation"]


def test_exports_subpath_has_no_physical_fallback(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _write(
        repo / "package.json",
        '{"private": true, "workspaces": ["packages/*"]}\n',
    )
    _write(
        repo / "packages/ui/package.json",
        '{"name": "@fixture/ui", "exports": {".": "./index.ts"}}\n',
    )
    _write(repo / "packages/ui/index.ts", "export const ui = 1;\n")
    _write(repo / "packages/ui/private.ts", "export const hidden = 1;\n")
    _write(repo / "src/main.ts", 'import "@fixture/ui/private";\n')

    result = parse_repository(repo)

    assert len(result.unresolved_references) == 1
    assert result.unresolved_references[0].reason == ("workspace package subpath is not exported")


def test_path_escape_in_extends_is_named(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _write(repo / "package.json", '{"private": true, "workspaces": ["packages/*"]}\n')
    _write(
        repo / "packages/config/package.json",
        '{"name": "@fixture/config"}\n',
    )
    _write(repo / "packages/config/tsconfig.json", '{"compilerOptions": {"strict": true}}\n')
    _write(
        repo / "tsconfig.json",
        '{"extends": "@fixture/config/../outside.json"}\n',
    )
    _write(repo / "src/main.ts", 'import "./other";\n')
    _write(repo / "src/other.ts", "export const other = 1;\n")

    result = parse_repository(repo)

    assert [record.reason for record in result.unresolved_references] == [
        "workspace path outside the repository"
    ]


def test_utf8_decode_failure_is_a_named_response_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail(*_args: object, **_kwargs: object) -> None:
        raise UnicodeDecodeError("utf-8", b"\xff", 0, 1, "invalid")

    monkeypatch.setattr(subprocess, "run", fail)

    with pytest.raises(ResolverFailure, match="js resolver returned an invalid response"):
        resolve_references(Path("."), (), max_file_bytes=1_000)


def test_symlinked_configuration_is_not_read(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    real_config = repo / "real-tsconfig.json"
    _write(
        real_config,
        '{"compilerOptions": {"baseUrl": ".", "paths": {"@alias/*": ["./src/*"]}}}\n',
    )
    _write(repo / "src/main.ts", 'import "@alias/other";\n')
    _write(repo / "src/other.ts", "export const other = 1;\n")
    link = repo / "tsconfig.json"
    try:
        os.symlink(real_config, link)
    except OSError:
        pytest.skip("symbolic links are not available on this host")

    result = parse_repository(repo)

    assert result.edges == []
    assert [record.reference for record in result.external_references] == ["@alias/other"]
    config_record = next(record for record in result.files if record.path == "tsconfig.json")
    assert config_record.excluded_reason == "symbolic link"


def test_failed_file_resolves_inside_references_but_keeps_them_failed(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    _write(
        repo / "tsconfig.json",
        '{"compilerOptions": {"baseUrl": ".", "paths": {"@x/*": ["./src/*"]}}}\n',
    )
    _write(repo / "src/target.ts", "export const target = 1;\n")
    _write(
        repo / "src/main.ts",
        'import "@x/target";\nimport "./target";\nimport "react";\nconst = ;\n',
    )

    result = parse_repository(repo)

    assert result.edges == []
    assert [record.reason for record in result.unresolved_references] == [
        "file has a syntax error",
        "file has a syntax error",
    ]
    assert [record.reference for record in result.external_references] == ["react"]
    failed_file = next(record for record in result.files if record.path == "src/main.ts")
    assert failed_file.parse_failure is not None
    assert failed_file.parse_failure.reason == "syntax error"


def test_asset_configuration_failure_is_named(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _write(repo / "tsconfig.json", '{"compilerOptions":\n')
    _write(repo / "src/main.ts", 'import "./style.css";\n')
    _write(repo / "src/style.css", "body { color: red; }\n")

    result = parse_repository(repo)

    assert result.edges == []
    assert len(result.unresolved_references) == 1
    assert result.unresolved_references[0].reason.startswith("configuration file")


def test_line_count_uses_raw_bytes(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    source = repo / "src/main.ts"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_bytes("const a = 1;\u2028const b = 2;\n".encode("utf-8"))

    result = parse_repository(repo)

    record = next(record for record in result.files if record.path == "src/main.ts")
    assert record.line_count == 1
