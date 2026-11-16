"""Import root selection: configuration first, then a src layout, then the root."""

from pathlib import Path

import pytest
from codecraft_core import PythonRepositoryDetails, RepositoryParse
from codecraft_parsing import parse_repository


def _details(result: RepositoryParse) -> PythonRepositoryDetails:
    assert result.python is not None
    return result.python


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def test_repository_root_is_the_fallback(tmp_path: Path) -> None:
    _write(tmp_path / "pkg" / "__init__.py", "")
    result = parse_repository(tmp_path)
    assert _details(result).import_root == "."
    assert _details(result).import_root_rule == "repository root"


def test_src_layout_is_detected_without_configuration(tmp_path: Path) -> None:
    _write(tmp_path / "src" / "pkg" / "__init__.py", "")
    result = parse_repository(tmp_path)
    assert _details(result).import_root == "src"
    assert _details(result).import_root_rule == "src layout"


def test_a_src_folder_with_only_an_environment_is_not_a_src_layout(tmp_path: Path) -> None:
    _write(tmp_path / "src" / ".venv" / "pyvenv.cfg", "home = /usr/bin\n")
    _write(
        tmp_path / "src" / ".venv" / "lib" / "python3.14" / "site-packages" / "installed.py",
        "",
    )
    result = parse_repository(tmp_path)
    assert _details(result).import_root == "."
    assert _details(result).import_root_rule == "repository root"


def test_an_oversized_python_file_does_not_choose_src_layout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("codecraft_parsing.python.import_root.MAX_FILE_BYTES", 16)
    _write(tmp_path / "src" / "large.py", "value = 1\n" * 20)
    result = parse_repository(tmp_path)
    assert _details(result).import_root == "."
    assert _details(result).import_root_rule == "repository root"


def test_a_symlinked_python_file_does_not_choose_src_layout(tmp_path: Path) -> None:
    _write(tmp_path / "real.py", "")
    source = tmp_path / "src"
    source.mkdir()
    try:
        (source / "linked.py").symlink_to(tmp_path / "real.py")
    except OSError:
        pytest.skip("symbolic links are not available")
    result = parse_repository(tmp_path)
    assert _details(result).import_root == "."
    assert _details(result).import_root_rule == "repository root"


def test_setuptools_package_dir_names_the_root(tmp_path: Path) -> None:
    _write(
        tmp_path / "pyproject.toml",
        '[tool.setuptools]\npackage-dir = {"" = "lib"}\n',
    )
    _write(tmp_path / "lib" / "pkg" / "__init__.py", "")
    result = parse_repository(tmp_path)
    assert _details(result).import_root == "lib"
    assert _details(result).import_root_rule == "setuptools package-dir"


def test_setuptools_find_where_names_the_root(tmp_path: Path) -> None:
    _write(
        tmp_path / "pyproject.toml",
        '[tool.setuptools.packages.find]\nwhere = ["src"]\n',
    )
    _write(tmp_path / "src" / "pkg" / "__init__.py", "")
    result = parse_repository(tmp_path)
    assert _details(result).import_root == "src"
    assert _details(result).import_root_rule == "setuptools packages.find"


def test_hatch_packages_use_the_parent_directory(tmp_path: Path) -> None:
    _write(
        tmp_path / "pyproject.toml",
        '[tool.hatch.build.targets.wheel]\npackages = ["src/pkg"]\n',
    )
    _write(tmp_path / "src" / "pkg" / "__init__.py", "")
    result = parse_repository(tmp_path)
    assert _details(result).import_root == "src"
    assert _details(result).import_root_rule == "hatch packages"


def test_a_windows_style_hatch_package_is_normalised(tmp_path: Path) -> None:
    _write(
        tmp_path / "pyproject.toml",
        '[tool.hatch.build.targets.wheel]\npackages = ["lib\\\\src\\\\pkg"]\n',
    )
    _write(tmp_path / "lib" / "src" / "pkg" / "__init__.py", "")
    result = parse_repository(tmp_path)
    assert _details(result).import_root == "lib/src"
    assert _details(result).import_root_rule == "hatch packages"


def test_poetry_from_names_the_root(tmp_path: Path) -> None:
    _write(
        tmp_path / "pyproject.toml",
        '[tool.poetry]\npackages = [{ include = "pkg", from = "lib" }]\n',
    )
    _write(tmp_path / "lib" / "pkg" / "__init__.py", "")
    result = parse_repository(tmp_path)
    assert _details(result).import_root == "lib"
    assert _details(result).import_root_rule == "poetry packages"


def test_setup_cfg_package_dir_names_the_root(tmp_path: Path) -> None:
    _write(tmp_path / "setup.cfg", "[options]\npackage_dir =\n    =lib\n")
    _write(tmp_path / "lib" / "pkg" / "__init__.py", "")
    result = parse_repository(tmp_path)
    assert _details(result).import_root == "lib"
    assert _details(result).import_root_rule == "setup.cfg package_dir"


def test_a_configured_path_outside_the_root_is_ignored(tmp_path: Path) -> None:
    _write(
        tmp_path / "pyproject.toml",
        '[tool.setuptools]\npackage-dir = {"" = "../outside"}\n',
    )
    _write(tmp_path / "pkg" / "__init__.py", "")
    result = parse_repository(tmp_path)
    assert _details(result).import_root == "."
    assert _details(result).import_root_rule == "repository root"


def test_a_source_folder_named_only_in_setup_py_is_not_detected(tmp_path: Path) -> None:
    _write(
        tmp_path / "setup.py",
        'from setuptools import setup\n\nsetup(package_dir={"": "lib"})\n',
    )
    _write(tmp_path / "lib" / "pkg" / "__init__.py", "")
    result = parse_repository(tmp_path)
    assert _details(result).import_root == "."
    assert _details(result).import_root_rule == "repository root"


def test_an_oversized_pyproject_is_treated_as_absent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("codecraft_parsing.python.import_root.MAX_FILE_BYTES", 16)
    _write(
        tmp_path / "pyproject.toml",
        '[tool.setuptools]\npackage-dir = {"" = "lib"}\n',
    )
    _write(tmp_path / "lib" / "pkg" / "__init__.py", "")
    result = parse_repository(tmp_path)
    assert _details(result).import_root == "."
    assert _details(result).import_root_rule == "repository root"


def test_a_symlinked_pyproject_is_treated_as_absent(tmp_path: Path) -> None:
    target = tmp_path / "real-pyproject.toml"
    _write(target, '[tool.setuptools]\npackage-dir = {"" = "lib"}\n')
    try:
        (tmp_path / "pyproject.toml").symlink_to(target)
    except OSError:
        pytest.skip("symbolic links are not available")
    _write(tmp_path / "lib" / "pkg" / "__init__.py", "")
    result = parse_repository(tmp_path)
    assert _details(result).import_root == "."
    assert _details(result).import_root_rule == "repository root"


def test_a_windows_style_configured_path_is_normalised(tmp_path: Path) -> None:
    _write(tmp_path / "setup.cfg", "[options]\npackage_dir =\n    =lib\\src\n")
    _write(tmp_path / "lib" / "src" / "pkg" / "__init__.py", "")
    result = parse_repository(tmp_path)
    assert _details(result).import_root == "lib/src"
    assert _details(result).import_root_rule == "setup.cfg package_dir"
