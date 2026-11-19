"""Go resolution outcomes that are not covered by the fixed expected fixtures."""

from pathlib import Path

import pytest
from codecraft_parsing import parse_repository


def _repo(tmp_path: Path, files: dict[str, str]) -> Path:
    for relative, text in files.items():
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return tmp_path


def test_a_replacement_target_without_a_module_file_uses_replace(tmp_path: Path) -> None:
    repo = _repo(
        tmp_path,
        {
            "go.mod": (
                "module example.com/app\n\ngo 1.22\n\nreplace example.com/target => ./target\n"
            ),
            "main.go": 'package main\n\nimport "example.com/target"\n',
            "target/target.go": "package target\n",
        },
    )
    model = parse_repository(repo, "go")
    assert model.go is not None

    target = next(
        module for module in model.go.modules if module.module_path == "example.com/target"
    )
    assert target.folder == "target"
    assert target.source.value == "replace"
    assert [(edge.source, edge.target) for edge in model.edges] == [("main.go", "target")]


def test_a_quoted_workspace_use_path_is_read(tmp_path: Path) -> None:
    repo = _repo(
        tmp_path,
        {
            "go.work": 'go 1.22\n\nuse "./app"\n',
            "app/go.mod": "module example.com/app\n\ngo 1.22\n",
            "app/main.go": "package main\n",
        },
    )
    model = parse_repository(repo, "go")

    assert model.go is not None
    module = next(module for module in model.go.modules if module.folder == "app")
    assert module.source.value == "workspace"


def test_a_missing_go_work_replacement_target_fails_the_import(tmp_path: Path) -> None:
    repo = _repo(
        tmp_path,
        {
            "go.work": "go 1.22\n\nuse ./app\n\nreplace example.com/target => ./missing\n",
            "app/go.mod": "module example.com/app\n\ngo 1.22\n",
            "app/main.go": 'package main\n\nimport "example.com/target/pkg"\n',
        },
    )
    model = parse_repository(repo, "go")

    assert [(record.reference, record.reason) for record in model.unresolved_references] == [
        ("example.com/target/pkg", "replacement target does not exist")
    ]


def test_a_go_work_replacement_outside_the_repository_is_classified(tmp_path: Path) -> None:
    repo = _repo(
        tmp_path,
        {
            "go.work": "go 1.22\n\nuse ./app\n\nreplace example.com/target => ../outside\n",
            "app/go.mod": "module example.com/app\n\ngo 1.22\n",
            "app/main.go": 'package main\n\nimport "example.com/target/pkg"\n',
        },
    )
    model = parse_repository(repo, "go")

    assert [(record.reference, record.reason) for record in model.unresolved_references] == [
        ("example.com/target/pkg", "replacement target is outside the repository")
    ]


def test_a_replacement_target_with_another_module_path_fails_the_import(
    tmp_path: Path,
) -> None:
    repo = _repo(
        tmp_path,
        {
            "go.mod": (
                "module example.com/app\n\ngo 1.22\n\nreplace example.com/target => ./target\n"
            ),
            "main.go": 'package main\n\nimport "example.com/target"\n',
            "target/go.mod": "module example.com/other\n\ngo 1.22\n",
            "target/target.go": "package target\n",
        },
    )
    model = parse_repository(repo, "go")

    assert [(record.reference, record.reason) for record in model.unresolved_references] == [
        ("example.com/target", "replacement target declares a different module path")
    ]
    assert model.external_references == []


def test_a_missing_replacement_target_fails_the_import(tmp_path: Path) -> None:
    repo = _repo(
        tmp_path,
        {
            "go.mod": (
                "module example.com/app\n\ngo 1.22\n\nreplace example.com/target => ./missing\n"
            ),
            "main.go": 'package main\n\nimport "example.com/target/pkg"\n',
        },
    )
    model = parse_repository(repo, "go")

    assert [(record.reference, record.reason) for record in model.unresolved_references] == [
        ("example.com/target/pkg", "replacement target does not exist")
    ]


def test_a_module_file_without_a_readable_path_fails_imports_in_it(tmp_path: Path) -> None:
    repo = _repo(
        tmp_path,
        {
            "go.mod": "go 1.22\nrequire (\n    example.com/dep v1.2.3\n",
            "main.go": 'package main\n\nimport "example.com/app/pkg"\n',
            "pkg/pkg.go": "package pkg\n",
        },
    )
    model = parse_repository(repo, "go")

    assert [(record.reference, record.reason) for record in model.unresolved_references] == [
        ("example.com/app/pkg", "malformed module file")
    ]
    module_file = next(record for record in model.files if record.path == "go.mod")
    assert module_file.parse_failure is not None
    assert module_file.parse_failure.reason == "malformed module file"


def test_an_unreadable_module_file_uses_its_own_exclusion_reason(tmp_path: Path) -> None:
    repo = _repo(
        tmp_path,
        {
            "module.mod": "module example.com/app\n\ngo 1.22\n",
            "main.go": 'package main\n\nimport "example.com/app/pkg"\n',
        },
    )
    try:
        (repo / "go.mod").symlink_to(repo / "module.mod")
    except OSError:
        pytest.skip("symbolic links are unavailable")

    model = parse_repository(repo, "go")

    module_file = next(record for record in model.files if record.path == "go.mod")
    assert module_file.parse_failure is not None
    assert module_file.parse_failure.reason == "symbolic link"
    assert [(record.reference, record.reason) for record in model.unresolved_references] == [
        ("example.com/app/pkg", "symbolic link")
    ]


def test_readable_imports_after_a_damaged_function_are_recorded(tmp_path: Path) -> None:
    repo = _repo(
        tmp_path,
        {
            "go.mod": "module example.com/app\n\ngo 1.22\n",
            "main.go": (
                "package main\n\nfunc broken() {\n\n"
                'import (\n    "fmt"\n    "example.com/app/pkg"\n)\n'
            ),
            "pkg/pkg.go": "package pkg\n",
        },
    )
    model = parse_repository(repo, "go")

    main_file = next(record for record in model.files if record.path == "main.go")
    assert main_file.parse_failure is not None
    assert main_file.parse_failure.reason == "syntax error"
    assert [
        (record.reference, record.reason, record.line, record.column)
        for record in model.unresolved_references
    ] == [("example.com/app/pkg", "file has a syntax error", 7, 5)]
    assert [
        (record.reference, record.line, record.column) for record in model.external_references
    ] == [("fmt", 6, 5)]
    assert model.edges == []
    assert model.coverage.references == 2


def test_error_import_recovery_keeps_a_valid_import_declaration(tmp_path: Path) -> None:
    repo = _repo(
        tmp_path,
        {
            "go.mod": "module example.com/app\n\ngo 1.22\n",
            "main.go": (
                'package main\n\nimport "fmt"\n\nfunc broken() {\n\n'
                'import (\n    "example.com/app/pkg"\n)\n'
            ),
            "pkg/pkg.go": "package pkg\n",
        },
    )
    model = parse_repository(repo, "go")

    assert [
        (record.reference, record.reason, record.line, record.column)
        for record in model.unresolved_references
    ] == [("example.com/app/pkg", "file has a syntax error", 8, 5)]
    assert [
        (record.reference, record.line, record.column) for record in model.external_references
    ] == [("fmt", 3, 1)]
    assert model.edges == []


@pytest.mark.parametrize(
    ("imports", "external", "malformed"),
    [
        (
            'import "fmt" _ "example.com/app/pkg"\n',
            [("fmt", 3, 1)],
            [("example.com/app/pkg", 3, 16)],
        ),
        (
            'import "fmt" x "example.com/app/pkg"\n',
            [("fmt", 3, 1)],
            [("example.com/app/pkg", 3, 16)],
        ),
        (
            'import (\n    "fmt" "example.com/app/pkg"\n)\n',
            [("fmt", 4, 5)],
            [("example.com/app/pkg", 4, 11)],
        ),
        (
            'import (\n    "a" "b" "c"\n)\n',
            [("a", 4, 5)],
            [("b", 4, 9), ("c", 4, 13)],
        ),
        (
            'import ("a" "b" "c")\n',
            [("a", 3, 9)],
            [("b", 3, 13), ("c", 3, 17)],
        ),
        (
            'import ("fmt" "example.com/app/pkg")\n',
            [("fmt", 3, 9)],
            [("example.com/app/pkg", 3, 15)],
        ),
    ],
)
def test_malformed_import_specs_keep_the_first_path_ordinary(
    tmp_path: Path,
    imports: str,
    external: list[tuple[str, int, int]],
    malformed: list[tuple[str, int, int]],
) -> None:
    repo = _repo(
        tmp_path,
        {
            "go.mod": "module example.com/app\n\ngo 1.22\n",
            "main.go": f"package main\n\n{imports}",
        },
    )
    model = parse_repository(repo, "go")

    assert [
        (record.reference, record.line, record.column) for record in model.external_references
    ] == external
    assert [
        (record.reference, record.reason, record.line, record.column)
        for record in model.unresolved_references
    ] == [
        (reference, "malformed import spec", line, column) for reference, line, column in malformed
    ]
    assert model.edges == []
    assert model.coverage.references == len(external) + len(malformed)


def test_comment_text_is_not_an_import_path(tmp_path: Path) -> None:
    repo = _repo(
        tmp_path,
        {
            "go.mod": "module example.com/app\n\ngo 1.22\n",
            "main.go": 'package main\n\nimport "fmt" // "not-a-path"\n',
        },
    )
    model = parse_repository(repo, "go")

    assert [
        (record.reference, record.line, record.column) for record in model.external_references
    ] == [("fmt", 3, 1)]
    assert model.unresolved_references == []
    assert model.coverage.references == 1


def test_comment_text_after_an_unterminated_path_is_not_a_path(tmp_path: Path) -> None:
    repo = _repo(
        tmp_path,
        {
            "go.mod": "module example.com/app\n\ngo 1.22\n",
            "main.go": 'package main\n\nimport (\n    "a\n    // "x" "y"\n)\n',
        },
    )
    model = parse_repository(repo, "go")

    assert [record.reference for record in model.unresolved_references] == ["a"]
    assert model.external_references == []


def test_a_missing_path_on_the_group_opener_line_is_recorded(tmp_path: Path) -> None:
    repo = _repo(
        tmp_path,
        {
            "go.mod": "module example.com/app\n\ngo 1.22\n",
            "main.go": 'package main\n\nimport ( _\n    "a" "b"\n)\n',
        },
    )
    model = parse_repository(repo, "go")

    assert [
        (record.reference, record.reason, record.line, record.column)
        for record in model.unresolved_references
    ] == [
        ("(missing import path)", "import spec has no path", 3, 10),
        ("b", "malformed import spec", 4, 9),
    ]
    assert [
        (record.reference, record.line, record.column) for record in model.external_references
    ] == [("a", 4, 5)]


def test_a_missing_path_before_a_semicolon_is_recorded(tmp_path: Path) -> None:
    repo = _repo(
        tmp_path,
        {
            "go.mod": "module example.com/app\n\ngo 1.22\n",
            "main.go": 'package main\n\nimport (\n    _; "a" "b"\n)\n',
        },
    )
    model = parse_repository(repo, "go")

    assert [
        (record.reference, record.reason, record.line, record.column)
        for record in model.unresolved_references
    ] == [
        ("(missing import path)", "import spec has no path", 4, 5),
        ("b", "malformed import spec", 4, 12),
    ]
    assert [
        (record.reference, record.line, record.column) for record in model.external_references
    ] == [("a", 4, 8)]


def test_a_missing_path_spec_survives_a_malformed_line(tmp_path: Path) -> None:
    repo = _repo(
        tmp_path,
        {
            "go.mod": "module example.com/app\n\ngo 1.22\n",
            "main.go": 'package main\n\nimport (\n    _\n    "a" "b"\n)\n',
        },
    )
    model = parse_repository(repo, "go")

    assert [
        (record.reference, record.reason, record.line, record.column)
        for record in model.unresolved_references
    ] == [
        ("(missing import path)", "import spec has no path", 4, 5),
        ("b", "malformed import spec", 5, 9),
    ]
    assert [
        (record.reference, record.line, record.column) for record in model.external_references
    ] == [("a", 5, 5)]
    assert model.coverage.references == 3


def test_a_missing_import_path_is_recorded_when_the_file_fails(tmp_path: Path) -> None:
    repo = _repo(
        tmp_path,
        {
            "go.mod": "module example.com/app\n\ngo 1.22\n",
            "main.go": "package main\n\nimport (\n    _\n)\n",
        },
    )
    model = parse_repository(repo, "go")

    main_file = next(record for record in model.files if record.path == "main.go")
    assert main_file.parse_failure is not None
    assert main_file.parse_failure.reason == "syntax error"
    assert [(record.reference, record.reason) for record in model.unresolved_references] == [
        ("(missing import path)", "import spec has no path")
    ]
    assert model.edges == []


def test_a_broken_import_statement_is_recorded_when_no_spec_is_built(
    tmp_path: Path,
) -> None:
    repo = _repo(
        tmp_path,
        {
            "go.mod": "module example.com/app\n\ngo 1.22\n",
            "main.go": "package main\n\nimport foo\n",
        },
    )
    model = parse_repository(repo, "go")

    assert [(record.reference, record.reason) for record in model.unresolved_references] == [
        ("(missing import path)", "import spec has no path")
    ]
    assert model.edges == []


def test_a_malformed_import_with_no_error_node_is_still_a_parse_failure(
    tmp_path: Path,
) -> None:
    repo = _repo(
        tmp_path,
        {
            "go.mod": "module example.com/app\n\ngo 1.22\n",
            "main.go": 'package main\n\nimport "a" "b"\n',
        },
    )
    model = parse_repository(repo, "go")

    main_file = next(record for record in model.files if record.path == "main.go")
    assert main_file.parse_failure is not None
    assert main_file.parse_failure.reason == "syntax error"
    assert model.edges == []


def test_a_malformed_module_with_a_path_does_not_fail_external_imports(
    tmp_path: Path,
) -> None:
    repo = _repo(
        tmp_path,
        {
            "go.mod": "module example.com/app\nrequire (\n    example.com/dep v1.2.3\n",
            "main.go": 'package main\n\nimport "fmt"\nimport "example.com/app/pkg"\n',
            "pkg/pkg.go": "package pkg\n",
        },
    )
    model = parse_repository(repo, "go")

    assert [(record.reference, record.reason) for record in model.unresolved_references] == [
        ("example.com/app/pkg", "malformed module file")
    ]
    assert [record.reference for record in model.external_references] == ["fmt"]


def test_a_valid_nested_module_is_not_failed_by_a_malformed_parent(tmp_path: Path) -> None:
    repo = _repo(
        tmp_path,
        {
            "go.mod": "require (\n    example.com/dep v1.2.3\n",
            "nested/go.mod": "module example.com/nested\n\ngo 1.22\n",
            "nested/nested.go": 'package nested\n\nimport "fmt"\n',
        },
    )
    model = parse_repository(repo, "go")

    nested = next(record for record in model.files if record.path == "nested/nested.go")
    assert nested.go is not None
    assert nested.go.module_path == "example.com/nested"
    assert [record.reference for record in model.external_references] == ["fmt"]
    assert model.unresolved_references == []


def test_a_folder_with_no_package_name_is_not_importable(tmp_path: Path) -> None:
    repo = _repo(
        tmp_path,
        {
            "go.mod": "module example.com/app\n\ngo 1.22\n",
            "main.go": 'package main\n\nimport "example.com/app/empty"\n',
            "empty/empty.go": "var x = 1\n",
        },
    )
    model = parse_repository(repo, "go")

    assert [(record.reference, record.reason) for record in model.unresolved_references] == [
        ("example.com/app/empty", "package folder has no importable package")
    ]
    assert model.edges == []


def test_a_conflicting_file_records_its_readable_imports(tmp_path: Path) -> None:
    repo = _repo(
        tmp_path,
        {
            "go.mod": "module example.com/app\n\ngo 1.22\n",
            "main.go": 'package main\n\nimport "example.com/app/pkg"\n',
            "pkg/a.go": 'package alpha\n\nimport "fmt"\n',
            "pkg/b.go": "package beta\n",
        },
    )
    model = parse_repository(repo, "go")

    assert [
        (record.source, record.reference, record.reason) for record in model.unresolved_references
    ] == [
        ("main.go", "example.com/app/pkg", "conflicting package names in one folder"),
    ]
    assert [(record.source, record.reference) for record in model.external_references] == [
        ("pkg/a.go", "fmt")
    ]
    assert model.edges == []
    assert model.coverage.references == 2


def test_a_cgo_import_in_a_conflicting_file_keeps_its_cgo_outcome(
    tmp_path: Path,
) -> None:
    repo = _repo(
        tmp_path,
        {
            "go.mod": "module example.com/app\n\ngo 1.22\n",
            "pkg/a.go": 'package alpha\n\nimport (\n    "C"\n    "fmt"\n)\n',
            "pkg/b.go": "package beta\n",
        },
    )
    model = parse_repository(repo, "go")

    assert [(record.reference, record.status.value) for record in model.cgo_references] == [
        ("C", "cgo pseudo-package")
    ]
    assert model.unresolved_references == []
    assert [(record.reference, record.top_level) for record in model.external_references] == [
        ("fmt", "fmt")
    ]
    assert model.coverage.references == 2


def test_a_parse_failed_file_still_counts_for_a_package_conflict(tmp_path: Path) -> None:
    repo = _repo(
        tmp_path,
        {
            "go.mod": "module example.com/app\n\ngo 1.22\n",
            "main.go": 'package main\n\nimport "example.com/app/pkg"\n',
            "pkg/a.go": "package alpha\n",
            "pkg/b.go": "package beta\n\nfunc broken() {\n",
        },
    )
    model = parse_repository(repo, "go")

    assert [(record.reference, record.reason) for record in model.unresolved_references] == [
        ("example.com/app/pkg", "conflicting package names in one folder")
    ]
    failures = {
        record.path: record.parse_failure.reason
        for record in model.files
        if record.parse_failure is not None
    }
    assert failures == {
        "pkg/a.go": "conflicting package names in one folder",
        "pkg/b.go": "syntax error",
    }


def test_a_one_character_nested_module_is_chosen_deterministically(tmp_path: Path) -> None:
    repo = _repo(
        tmp_path,
        {
            "go.mod": "module example.com/root\n\ngo 1.22\n",
            "a/go.mod": "module example.com/a\n\ngo 1.22\n",
            "a/a.go": "package a\n",
        },
    )
    model = parse_repository(repo, "go")

    nested = next(record for record in model.files if record.path == "a/a.go")
    assert nested.go is not None
    assert nested.go.module_path == "example.com/a"


def test_a_folder_with_only_tests_is_not_importable(tmp_path: Path) -> None:
    repo = _repo(
        tmp_path,
        {
            "go.mod": "module example.com/app\n\ngo 1.22\n",
            "main.go": 'package main\n\nimport "example.com/app/pkg"\n',
            "pkg/pkg_test.go": "package pkg_test\n",
        },
    )
    model = parse_repository(repo, "go")

    assert [(record.reference, record.reason) for record in model.unresolved_references] == [
        ("example.com/app/pkg", "package folder has no importable package")
    ]


def test_a_folder_with_only_build_excluded_files_is_excluded(tmp_path: Path) -> None:
    repo = _repo(
        tmp_path,
        {
            "go.mod": "module example.com/app\n\ngo 1.22\n",
            "main.go": 'package main\n\nimport "example.com/app/pkg"\n',
            "pkg/pkg_windows.go": "//go:build windows\n\npackage pkg\n",
        },
    )
    model = parse_repository(repo, "go")

    assert [(record.reference, record.reason) for record in model.excluded_references] == [
        ("example.com/app/pkg", "build constraint excludes file for linux/amd64")
    ]
    assert model.edges == []


def test_go_filename_constraints_need_a_prefix_and_use_the_first_underscore(
    tmp_path: Path,
) -> None:
    repo = _repo(
        tmp_path,
        {
            "go.mod": "module example.com/app\n\ngo 1.22\n",
            "js.go": "package app\n",
            "js_test.go": "package app\n",
            "linux.go": "package app\n",
            "windows_amd64.go": "package app\n",
            "foo_js.go": "package app\n",
            "foo_windows_amd64.go": "package app\n",
            "foo_linux_amd64.go": "package app\n",
            "docker_host_windows.go": "package app\n",
            "foo_bar_linux.go": "package app\n",
        },
    )
    model = parse_repository(repo, "go")
    records = {record.path: record for record in model.files}

    for path in (
        "js.go",
        "js_test.go",
        "linux.go",
        "windows_amd64.go",
        "foo_linux_amd64.go",
        "foo_bar_linux.go",
    ):
        assert records[path].is_node, path
    assert records["foo_bar_linux.go"].go is not None
    assert [
        (item.source.value, item.expression)
        for item in records["foo_bar_linux.go"].go.build_constraints
    ] == [("filename", "linux")]
    assert records["windows_amd64.go"].go is not None
    assert [
        (item.source.value, item.expression)
        for item in records["windows_amd64.go"].go.build_constraints
    ] == [("filename", "amd64")]
    assert records["foo_js.go"].excluded_reason == "build constraint excludes file for linux/amd64"
    assert (
        records["foo_windows_amd64.go"].excluded_reason
        == "build constraint excludes file for linux/amd64"
    )
    assert (
        records["docker_host_windows.go"].excluded_reason
        == "build constraint excludes file for linux/amd64"
    )


def test_a_new_call_with_a_type_constructor_gets_the_named_reason(tmp_path: Path) -> None:
    repo = _repo(
        tmp_path,
        {
            "go.mod": "module example.com/app\n\ngo 1.22\n",
            "main.go": "package main\n\nvar x = new(int64(9))\n",
        },
    )
    model = parse_repository(repo, "go")

    failure = next(record.parse_failure for record in model.files if record.path == "main.go")
    assert failure is not None
    assert failure.reason == "Go 1.26 new with expression argument, not read by the current grammar"


def test_a_new_call_with_a_type_conversion_argument_gets_the_named_reason(
    tmp_path: Path,
) -> None:
    repo = _repo(
        tmp_path,
        {
            "go.mod": "module example.com/app\n\ngo 1.22\n",
            "main.go": "package main\n\nvar x = new(T(x))\n",
        },
    )
    model = parse_repository(repo, "go")

    failure = next(record.parse_failure for record in model.files if record.path == "main.go")
    assert failure is not None
    assert failure.reason == "Go 1.26 new with expression argument, not read by the current grammar"


def test_a_malformed_type_argument_keeps_the_generic_reason(tmp_path: Path) -> None:
    repo = _repo(
        tmp_path,
        {
            "go.mod": "module example.com/app\n\ngo 1.22\n",
            "main.go": "package main\n\nvar x = new(map[string)\n",
        },
    )
    model = parse_repository(repo, "go")

    failure = next(record.parse_failure for record in model.files if record.path == "main.go")
    assert failure is not None
    assert failure.reason == "syntax error"


def test_go_line_count_uses_raw_bytes(tmp_path: Path) -> None:
    repo = _repo(
        tmp_path,
        {
            "go.mod": "module example.com/app\n\ngo 1.22\n",
            "main.go": 'package main\n\nvar x = "a\u2028b"\n',
        },
    )
    model = parse_repository(repo, "go")

    main_file = next(record for record in model.files if record.path == "main.go")
    assert main_file.line_count == 3


def test_an_import_path_ending_in_a_slash_is_unresolved(tmp_path: Path) -> None:
    repo = _repo(
        tmp_path,
        {
            "go.mod": "module example.com/app\n\ngo 1.22\n",
            "main.go": 'package main\n\nimport "example.com/app/pkg/"\n',
            "pkg/pkg.go": "package pkg\n",
        },
    )
    model = parse_repository(repo, "go")

    assert [(record.reference, record.reason) for record in model.unresolved_references] == [
        ("example.com/app/pkg/", "import path ends with a slash")
    ]


def test_build_constraint_scanning_stops_at_the_real_package_clause(
    tmp_path: Path,
) -> None:
    repo = _repo(
        tmp_path,
        {
            "go.mod": "module example.com/app\n\ngo 1.22\n",
            "main.go": "//go:build linux\n\npackage app\n\n//go:build windows\n",
        },
    )
    model = parse_repository(repo, "go")

    main_file = next(record for record in model.files if record.path == "main.go")
    assert main_file.go is not None
    assert [(item.source.value, item.expression) for item in main_file.go.build_constraints] == [
        ("build_line", "linux")
    ]


def test_an_unknown_block_opener_with_extra_text_is_malformed(tmp_path: Path) -> None:
    repo = _repo(
        tmp_path,
        {
            "go.mod": "module example.com/app\nfrobnicate extra (\n)\n",
            "main.go": "package main\n",
        },
    )
    model = parse_repository(repo, "go")

    go_mod = next(record for record in model.files if record.path == "go.mod")
    assert go_mod.parse_failure is not None
    assert go_mod.parse_failure.reason == "malformed module file"


def test_an_unknown_block_opener_without_extra_text_is_data(tmp_path: Path) -> None:
    repo = _repo(
        tmp_path,
        {
            "go.mod": "module example.com/app\ngodebug (\n    default=go1.22\n)\n",
            "main.go": "package main\n",
        },
    )
    model = parse_repository(repo, "go")

    go_mod = next(record for record in model.files if record.path == "go.mod")
    assert go_mod.parse_failure is None


def test_an_empty_import_path_is_unresolved(tmp_path: Path) -> None:
    repo = _repo(
        tmp_path,
        {
            "go.mod": "module example.com/app\n\ngo 1.22\n",
            "main.go": 'package main\n\nimport ""\n',
        },
    )
    model = parse_repository(repo, "go")

    assert [(record.reference, record.reason) for record in model.unresolved_references] == [
        ("", "import path is empty")
    ]
    assert model.external_references == []


def test_a_recognised_block_with_extra_text_is_malformed(tmp_path: Path) -> None:
    repo = _repo(
        tmp_path,
        {
            "go.mod": "module example.com/app\nrequire example.com/dep v1.2.3 (\n",
            "main.go": "package main\n",
        },
    )
    model = parse_repository(repo, "go")

    go_mod = next(record for record in model.files if record.path == "go.mod")
    assert go_mod.parse_failure is not None
    assert go_mod.parse_failure.reason == "malformed module file"


@pytest.mark.parametrize(
    "go_mod",
    [
        "module example.com/app\nrequire example.com/dep v1.2.3 extra\n",
        "module example.com/app\nexclude example.com/dep v1.2.3 extra\n",
        "module example.com/app\nrequire (\n    example.com/dep v1.2.3 extra\n)\n",
    ],
)
def test_a_require_or_exclude_with_extra_tokens_is_malformed(tmp_path: Path, go_mod: str) -> None:
    repo = _repo(tmp_path, {"go.mod": go_mod, "main.go": "package main\n"})
    model = parse_repository(repo, "go")

    module_file = next(record for record in model.files if record.path == "go.mod")
    assert module_file.parse_failure is not None
    assert module_file.parse_failure.reason == "malformed module file"


def test_a_replace_with_too_many_tokens_is_malformed(tmp_path: Path) -> None:
    repo = _repo(
        tmp_path,
        {
            "go.mod": (
                "module example.com/app\nreplace example.com/a => example.com/b v1.0.0 extra\n"
            ),
            "main.go": "package main\n",
        },
    )
    model = parse_repository(repo, "go")

    go_mod = next(record for record in model.files if record.path == "go.mod")
    assert go_mod.parse_failure is not None
    assert go_mod.parse_failure.reason == "malformed module file"


def test_a_malformed_quoted_module_path_is_a_module_failure(tmp_path: Path) -> None:
    repo = _repo(
        tmp_path,
        {
            "go.mod": 'module "example.com/app\n\ngo 1.22\n',
            "main.go": "package main\n",
        },
    )
    model = parse_repository(repo, "go")
    assert model.go is not None

    module_file = next(record for record in model.files if record.path == "go.mod")
    assert module_file.parse_failure is not None
    assert module_file.parse_failure.reason == "malformed module file"
    assert model.go.modules == ()
