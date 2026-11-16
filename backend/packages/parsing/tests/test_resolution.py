"""Named failure reasons and the excluded-reference outcome."""

from pathlib import Path

from codecraft_core import EdgeKind, ImportCondition, StarImportStatus
from codecraft_parsing import parse_repository


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def test_a_module_is_not_a_package(tmp_path: Path) -> None:
    _write(tmp_path / "thing.py", "VALUE = 1\n")
    _write(tmp_path / "user.py", "import thing.sub\n")

    result = parse_repository(tmp_path)

    assert [(record.reference, record.reason) for record in result.unresolved_references] == [
        ("thing.sub", "parent module is not a package")
    ]


def test_an_import_of_a_pruned_directory_is_excluded(tmp_path: Path) -> None:
    _write(tmp_path / "node_modules" / "installed.py", "VALUE = 1\n")
    _write(tmp_path / "app.py", "import node_modules\n")

    result = parse_repository(tmp_path)

    assert result.coverage.excluded == 1
    assert result.coverage.failed == 0
    assert [(record.reference, record.reason) for record in result.excluded_references] == [
        ("node_modules", "dependency installation")
    ]


def test_an_import_of_a_nested_pruned_directory_is_excluded(tmp_path: Path) -> None:
    _write(tmp_path / "pkg" / "__init__.py", "")
    _write(tmp_path / "pkg" / "node_modules" / "installed.py", "VALUE = 1\n")
    _write(tmp_path / "pkg" / "user.py", "import pkg.node_modules\n")

    result = parse_repository(tmp_path)

    assert result.coverage.excluded == 1
    assert result.coverage.failed == 0
    assert [(record.reference, record.reason) for record in result.excluded_references] == [
        ("pkg.node_modules", "dependency installation")
    ]


def test_a_name_imported_from_a_nested_pruned_directory_is_excluded(tmp_path: Path) -> None:
    _write(tmp_path / "pkg" / "__init__.py", "")
    _write(tmp_path / "pkg" / "node_modules" / "installed.py", "VALUE = 1\n")
    _write(tmp_path / "pkg" / "user.py", "from pkg import node_modules\n")

    result = parse_repository(tmp_path)

    assert result.coverage.excluded == 1
    assert result.coverage.symbols == 0
    assert [(record.reference, record.reason) for record in result.excluded_references] == [
        ("pkg.node_modules", "dependency installation")
    ]


def test_a_relative_import_one_level_above_the_top_level_fails(tmp_path: Path) -> None:
    _write(tmp_path / "relpkg" / "__init__.py", "")
    _write(tmp_path / "relpkg" / "beyond.py", "from .. import outside\n")
    _write(tmp_path / "outside.py", "")

    result = parse_repository(tmp_path)

    assert [(record.reference, record.reason) for record in result.unresolved_references] == [
        ("..", "relative import climbs above the top-level package")
    ]
    assert result.coverage.resolved == 0
    assert result.edges == []


def test_a_relative_import_in_a_module_at_the_import_root_fails(tmp_path: Path) -> None:
    _write(tmp_path / "loose.py", "from . import thing\n")
    _write(tmp_path / "thing.py", "")

    result = parse_repository(tmp_path)

    assert [(record.reference, record.reason) for record in result.unresolved_references] == [
        (".", "relative import climbs above the top-level package")
    ]
    assert result.edges == []


def test_an_absolute_import_of_the_own_package_draws_an_edge(tmp_path: Path) -> None:
    _write(tmp_path / "pkg" / "__init__.py", "")
    _write(tmp_path / "pkg" / "helper.py", "import pkg\n")

    result = parse_repository(tmp_path)

    assert [(edge.source, edge.target) for edge in result.edges] == [
        ("pkg/helper.py", "pkg/__init__.py")
    ]
    assert result.coverage.resolved == 1


def test_a_relative_dynamic_import_without_a_package_is_unresolved(tmp_path: Path) -> None:
    _write(tmp_path / "pkg" / "__init__.py", "")
    _write(tmp_path / "pkg" / "mod.py", "")
    _write(
        tmp_path / "pkg" / "app.py",
        'import importlib\nimportlib.import_module(".mod")\n',
    )

    result = parse_repository(tmp_path)

    assert [(record.reference, record.reason) for record in result.unresolved_references] == [
        (".mod", "relative dynamic import requires a package argument")
    ]
    assert result.edges == []


def test_a_relative_dunder_import_without_a_package_is_unresolved(tmp_path: Path) -> None:
    _write(tmp_path / "pkg" / "__init__.py", "")
    _write(tmp_path / "pkg" / "mod.py", "")
    _write(tmp_path / "pkg" / "app.py", '__import__(".mod")\n')

    result = parse_repository(tmp_path)

    assert [(record.reference, record.reason) for record in result.unresolved_references] == [
        (".mod", "relative __import__ is not resolved")
    ]
    assert result.edges == []


def test_a_dunder_import_with_a_dot_name_and_level_is_unresolved(tmp_path: Path) -> None:
    _write(tmp_path / "pkg" / "__init__.py", "")
    _write(tmp_path / "pkg" / "mod.py", "")
    _write(tmp_path / "pkg" / "app.py", '__import__(".mod", level=1)\n')

    result = parse_repository(tmp_path)

    assert [(record.reference, record.reason) for record in result.unresolved_references] == [
        (".mod", "relative __import__ is not resolved")
    ]
    assert result.edges == []


def test_a_relative_dynamic_import_resolves_from_the_package_argument(
    tmp_path: Path,
) -> None:
    _write(tmp_path / "pkg" / "__init__.py", "")
    _write(tmp_path / "pkg" / "mod.py", "")
    _write(tmp_path / "other" / "__init__.py", "")
    _write(
        tmp_path / "other" / "app.py",
        'import importlib\nimportlib.import_module(".mod", "pkg")\n',
    )

    result = parse_repository(tmp_path)

    assert [(edge.source, edge.target) for edge in result.edges] == [("other/app.py", "pkg/mod.py")]


def test_a_relative_dynamic_import_from_an_external_package_is_external(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path / "app.py",
        'import importlib\nimportlib.import_module(".mod", "requests")\n',
    )

    result = parse_repository(tmp_path)

    relative = [record for record in result.external_references if record.reference == ".mod"]
    assert [(record.top_level, record.source) for record in relative] == [("requests", "app.py")]
    assert result.unresolved_references == []
    assert result.edges == []
    assert result.coverage.external == 2


def test_a_relative_dynamic_import_from_a_pruned_package_is_excluded(tmp_path: Path) -> None:
    _write(tmp_path / "node_modules" / "installed.py", "")
    _write(
        tmp_path / "app.py",
        'import importlib\nimportlib.import_module(".mod", "node_modules")\n',
    )

    result = parse_repository(tmp_path)

    assert [(record.reference, record.reason) for record in result.excluded_references] == [
        (".mod", "dependency installation")
    ]
    assert result.coverage.excluded == 1
    assert result.coverage.failed == 0


def test_a_keyword_literal_dynamic_import_draws_an_edge(tmp_path: Path) -> None:
    _write(tmp_path / "mod.py", "")
    _write(
        tmp_path / "app.py",
        'import importlib\nimportlib.import_module(name="mod")\n',
    )

    result = parse_repository(tmp_path)

    assert [(edge.source, edge.target) for edge in result.edges] == [("app.py", "mod.py")]
    assert result.unresolved_references == []


def test_a_keyword_name_not_first_is_still_read(tmp_path: Path) -> None:
    _write(tmp_path / "pkg" / "__init__.py", "")
    _write(tmp_path / "pkg" / "mod.py", "")
    _write(
        tmp_path / "pkg" / "app.py",
        'import importlib\nimportlib.import_module(package="pkg", name=".mod")\n',
    )

    result = parse_repository(tmp_path)

    assert [(edge.source, edge.target) for edge in result.edges] == [("pkg/app.py", "pkg/mod.py")]
    assert result.unresolved_references == []


def test_a_non_literal_dynamic_package_is_unresolved(tmp_path: Path) -> None:
    _write(tmp_path / "pkg" / "__init__.py", "")
    _write(tmp_path / "pkg" / "mod.py", "")
    _write(
        tmp_path / "pkg" / "app.py",
        'import importlib\nimportlib.import_module(".mod", package)\n',
    )

    result = parse_repository(tmp_path)

    assert [(record.reference, record.reason) for record in result.unresolved_references] == [
        (".mod", "non-literal dynamic import package")
    ]
    assert result.coverage.external == 1


def test_a_pruned_directory_under_a_src_import_root_is_excluded(tmp_path: Path) -> None:
    _write(
        tmp_path / "pyproject.toml",
        '[tool.setuptools]\npackage-dir = {"" = "src"}\n',
    )
    _write(tmp_path / "src" / "node_modules" / "installed.py", "VALUE = 1\n")
    _write(tmp_path / "src" / "app.py", "import node_modules\n")

    result = parse_repository(tmp_path)

    assert [(record.reference, record.reason) for record in result.excluded_references] == [
        ("node_modules", "dependency installation")
    ]
    assert result.coverage.external == 0


def test_a_stub_file_target_is_excluded(tmp_path: Path) -> None:
    _write(tmp_path / "types.pyi", "value: int\n")
    _write(tmp_path / "app.py", "import types\n")

    result = parse_repository(tmp_path)

    assert [(record.reference, record.reason) for record in result.excluded_references] == [
        ("types", "stub file")
    ]
    assert result.coverage.external == 0


def test_a_lazy_import_edge_is_recorded(tmp_path: Path) -> None:
    _write(tmp_path / "thing.py", "")
    _write(tmp_path / "app.py", "def load():\n    import thing\n")

    result = parse_repository(tmp_path)

    assert [(edge.target, edge.condition) for edge in result.edges] == [
        ("thing.py", ImportCondition.LAZY)
    ]


def test_two_symbols_in_one_from_import_are_recorded(tmp_path: Path) -> None:
    _write(
        tmp_path / "shapes.py",
        "def width() -> int:\n    return 1\n\ndef height() -> int:\n    return 2\n",
    )
    _write(tmp_path / "app.py", "from shapes import width, height\n")

    result = parse_repository(tmp_path)

    assert [(record.module, record.name) for record in result.symbol_references] == [
        ("shapes", "height"),
        ("shapes", "width"),
    ]
    assert result.coverage.references == 3
    assert result.coverage.resolved == 1
    assert result.coverage.symbols == 2


def test_a_star_import_draws_its_edge_and_marks_names_not_enumerated(tmp_path: Path) -> None:
    _write(tmp_path / "shapes.py", "def width() -> int:\n    return 1\n")
    _write(tmp_path / "app.py", "from shapes import *\n")

    result = parse_repository(tmp_path)

    assert [(edge.source, edge.target, edge.kind) for edge in result.edges] == [
        ("app.py", "shapes.py", EdgeKind.IMPORT)
    ]
    assert [
        (record.source, record.module, record.status) for record in result.star_import_references
    ] == [("app.py", "shapes", StarImportStatus.NAMES_NOT_ENUMERATED)]
    assert result.star_import_references[0].line == 1
    assert result.star_import_references[0].column == 1
    assert result.unresolved_references == []
    coverage = result.coverage
    assert coverage.references == 1
    assert coverage.resolved == 0
    assert coverage.star_imports == 1
    assert coverage.references == (
        coverage.resolved
        + coverage.symbols
        + coverage.star_imports
        + coverage.external
        + coverage.excluded
        + coverage.failed
    )


def test_a_star_import_of_an_external_module_has_no_star_record(tmp_path: Path) -> None:
    _write(tmp_path / "app.py", "from os import *\n")

    result = parse_repository(tmp_path)

    assert [(record.reference, record.top_level) for record in result.external_references] == [
        ("os", "os")
    ]
    assert result.star_import_references == []
    assert result.coverage.star_imports == 0
    assert result.coverage.external == 1
    assert result.coverage.references == 1
    assert result.edges == []


def test_a_star_import_of_a_namespace_package_has_a_star_record_and_no_edge(
    tmp_path: Path,
) -> None:
    _write(tmp_path / "plugins" / "tool.py", "")
    _write(tmp_path / "app.py", "from plugins import *\n")

    result = parse_repository(tmp_path)

    assert result.edges == []
    assert [
        (record.source, record.module, record.status) for record in result.star_import_references
    ] == [("app.py", "plugins", StarImportStatus.NAMES_NOT_ENUMERATED)]
    assert result.coverage.references == 1
    assert result.coverage.resolved == 0
    assert result.coverage.star_imports == 1


def test_a_star_import_of_a_missing_module_has_no_star_record(tmp_path: Path) -> None:
    _write(tmp_path / "pkg" / "__init__.py", "")
    _write(tmp_path / "pkg" / "app.py", "from pkg.absent import *\n")

    result = parse_repository(tmp_path)

    assert [(record.reference, record.reason) for record in result.unresolved_references] == [
        ("pkg.absent", "module not found in repository")
    ]
    assert result.star_import_references == []
    assert result.coverage.star_imports == 0
    assert result.coverage.failed == 1


def test_a_star_import_of_an_excluded_file_has_no_star_record(tmp_path: Path) -> None:
    _write(tmp_path / "types.pyi", "value: int\n")
    _write(tmp_path / "app.py", "from types import *\n")

    result = parse_repository(tmp_path)

    assert [(record.reference, record.reason) for record in result.excluded_references] == [
        ("types", "stub file")
    ]
    assert result.star_import_references == []
    assert result.coverage.star_imports == 0
    assert result.coverage.excluded == 1


def test_a_dunder_import_with_level_one_is_relative_to_the_package(tmp_path: Path) -> None:
    _write(tmp_path / "pkg" / "__init__.py", "")
    _write(tmp_path / "pkg" / "mod.py", "")
    _write(tmp_path / "pkg" / "other.py", "")
    _write(
        tmp_path / "pkg" / "app.py",
        '__import__("mod", level=1)\n__import__("other", None, None, (), 1)\n',
    )

    result = parse_repository(tmp_path)

    assert [(edge.source, edge.target, edge.kind) for edge in result.edges] == [
        ("pkg/app.py", "pkg/mod.py", EdgeKind.DYNAMIC_IMPORT),
        ("pkg/app.py", "pkg/other.py", EdgeKind.DYNAMIC_IMPORT),
    ]
    assert result.unresolved_references == []


def test_a_dunder_import_without_a_level_or_with_zero_is_absolute(tmp_path: Path) -> None:
    _write(tmp_path / "mod.py", "")
    _write(tmp_path / "other.py", "")
    _write(
        tmp_path / "app.py",
        '__import__(name="mod")\n__import__("other", level=0)\n',
    )

    result = parse_repository(tmp_path)

    assert [(edge.source, edge.target, edge.kind) for edge in result.edges] == [
        ("app.py", "mod.py", EdgeKind.DYNAMIC_IMPORT),
        ("app.py", "other.py", EdgeKind.DYNAMIC_IMPORT),
    ]
    assert result.unresolved_references == []


def test_a_dunder_import_with_a_non_literal_level_is_unresolved(tmp_path: Path) -> None:
    _write(tmp_path / "mod.py", "")
    _write(tmp_path / "app.py", '__import__("mod", level=level)\n')

    result = parse_repository(tmp_path)

    assert [(record.reference, record.reason) for record in result.unresolved_references] == [
        ('__import__("mod", level=level)', "non-literal dynamic import")
    ]
    assert result.edges == []


def test_a_dunder_import_with_a_negative_level_is_unresolved(tmp_path: Path) -> None:
    _write(tmp_path / "mod.py", "")
    _write(tmp_path / "app.py", '__import__("mod", level=-1)\n')

    result = parse_repository(tmp_path)

    assert [(record.reference, record.reason) for record in result.unresolved_references] == [
        ('__import__("mod", level=-1)', "negative __import__ level")
    ]
    assert result.edges == []


def test_a_dunder_import_with_unary_plus_or_level_two_is_relative(tmp_path: Path) -> None:
    _write(tmp_path / "pkg" / "__init__.py", "")
    _write(tmp_path / "pkg" / "mod.py", "")
    _write(tmp_path / "pkg" / "app.py", '__import__("mod", None, None, (), +1)\n')
    _write(tmp_path / "pkg" / "sub" / "__init__.py", "")
    _write(tmp_path / "pkg" / "sub" / "app.py", '__import__("mod", level=2)\n')

    result = parse_repository(tmp_path)

    assert [(edge.source, edge.target, edge.kind) for edge in result.edges] == [
        ("pkg/app.py", "pkg/mod.py", EdgeKind.DYNAMIC_IMPORT),
        ("pkg/sub/app.py", "pkg/mod.py", EdgeKind.DYNAMIC_IMPORT),
    ]
    assert result.unresolved_references == []
