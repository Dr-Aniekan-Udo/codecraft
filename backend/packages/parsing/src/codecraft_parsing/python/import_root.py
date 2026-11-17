"""Find the directory that module names are measured from.

The import root comes from the repository's own configuration first, so a
package installed from ``src/`` is named ``pkg`` rather than ``src.pkg``. When
no configuration names one, a conventional layout is recognised. Anything that
does not point at a real directory inside the repository is ignored, because a
stale setting must not move every module name in the output.
"""

import configparser
import os
import tomllib
from collections.abc import Mapping, Sequence
from pathlib import Path, PurePosixPath
from typing import cast

from codecraft_parsing.common.walker import (
    MAX_FILE_BYTES,
    MAX_FILE_COUNT,
    directory_exclusion_reason,
    read_within_limit,
)


def detect_import_root(root: Path) -> tuple[str, str]:
    """Return the import root, as a POSIX path, and the rule that chose it.

    ``.`` means the repository root.
    """
    for candidate, rule in _configured_candidates(root):
        normalised = _existing_relative_directory(root, candidate)
        if normalised is not None:
            return normalised, rule
    if directory_exclusion_reason("src", root / "src") is None and _has_python_file(root / "src"):
        return "src", "src layout"
    return ".", "repository root"


def _configured_candidates(root: Path) -> list[tuple[str, str]]:
    return _pyproject_candidates(root) + _setup_cfg_candidates(root)


def _existing_relative_directory(root: Path, candidate: str) -> str | None:
    # Configuration may be written with Windows separators; the output and the
    # walk both speak POSIX paths, so compare in one form.
    candidate = candidate.replace("\\", "/")
    if not candidate:
        return None
    if Path(candidate).is_absolute() or PurePosixPath(candidate).is_absolute():
        return None
    parts = PurePosixPath(candidate).parts
    if ".." in parts or ".." in Path(candidate).parts:
        return None
    directory = root.joinpath(*parts)
    if not directory.is_dir():
        return None
    resolved_root = root.resolve()
    try:
        resolved = directory.resolve()
    except OSError:
        return None
    # A configuration path must not escape the repository, and a symlink
    # component is not accepted even when it points back inside: the walk
    # excludes symlinks, so an import root through one would name a namespace
    # the analysis never reads.
    if not resolved.is_relative_to(resolved_root):
        return None
    current = root
    for part in parts:
        current = current / part
        if current.is_symlink():
            return None
        if directory_exclusion_reason(part, current) is not None:
            return None
    normalised = PurePosixPath(candidate).as_posix()
    return normalised if normalised else "."


def _read_config_text(path: Path) -> str | None:
    """Read a configuration file only when it is safe to treat as data."""
    try:
        if path.is_symlink():
            return None
        data = read_within_limit(path, MAX_FILE_BYTES)
        if data is None:
            return None
        return data.decode("utf-8")
    except OSError, UnicodeDecodeError:
        return None


def _pyproject_candidates(root: Path) -> list[tuple[str, str]]:
    path = root / "pyproject.toml"
    text = _read_config_text(path)
    if text is None:
        return []
    try:
        document: Mapping[str, object] = tomllib.loads(text)
    except tomllib.TOMLDecodeError:
        return []

    candidates: list[tuple[str, str]] = []
    tool = _table(document.get("tool"))
    if tool is None:
        return candidates

    setuptools = _table(tool.get("setuptools"))
    if setuptools is not None:
        package_dir = _string(_table(setuptools.get("package-dir")), "")
        if package_dir is not None:
            candidates.append((package_dir, "setuptools package-dir"))

        find = _table(_table(setuptools.get("packages")), "find")
        where = _first_string(_sequence(find, "where"))
        if where is not None:
            candidates.append((where, "setuptools packages.find"))

    hatch = _table(_table(_table(_table(tool.get("hatch"), "build"), "targets"), "wheel"))
    hatch_package = _first_string(_sequence(hatch, "packages"))
    if hatch_package is not None:
        hatch_parent = PurePosixPath(hatch_package.replace("\\", "/")).parent
        candidates.append((hatch_parent.as_posix(), "hatch packages"))

    poetry = _table(tool.get("poetry"))
    poetry_entry = _sequence(poetry, "packages")
    if poetry_entry:
        entry = poetry_entry[0]
        from_value = _string(entry, "from")
        if from_value is None and isinstance(entry, str):
            from_value = "."
        candidates.append((from_value or ".", "poetry packages"))

    return candidates


def _setup_cfg_candidates(root: Path) -> list[tuple[str, str]]:
    path = root / "setup.cfg"
    text = _read_config_text(path)
    if text is None:
        return []
    parser = configparser.ConfigParser(interpolation=None)
    try:
        parser.read_string(text)
    except configparser.Error:
        return []

    raw = parser.get("options", "package_dir", fallback=None)
    if raw is None:
        return []
    for line in raw.splitlines():
        key, separator, value = line.partition("=")
        if separator and not key.strip():
            return [(value.strip(), "setup.cfg package_dir")]
    return []


def _has_python_file(directory: Path) -> bool:
    # A symlinked src directory is excluded by the walk, so it cannot choose the
    # layout here either.
    if directory.is_symlink() or not directory.is_dir():
        return False
    seen = 0
    found = False
    incomplete = False

    def _unreadable(_error: OSError) -> None:
        nonlocal incomplete
        # A listing that failed leaves a gap; a Python file elsewhere is only
        # partial evidence, so this traversal must not choose the src layout.
        incomplete = True

    for current, dirnames, filenames in os.walk(
        directory, topdown=True, onerror=_unreadable, followlinks=False
    ):
        current_path = Path(current)
        kept: list[str] = []
        for name in sorted(dirnames):
            candidate = current_path / name
            if candidate.is_symlink() or directory_exclusion_reason(name, candidate) is not None:
                continue
            kept.append(name)
        dirnames[:] = kept
        for name in filenames:
            seen += 1
            if seen > MAX_FILE_COUNT:
                return False
            if not name.endswith(".py"):
                continue
            candidate = current_path / name
            if candidate.is_symlink():
                continue
            try:
                if candidate.stat().st_size > MAX_FILE_BYTES:
                    continue
            except OSError:
                continue
            found = True
    return found and not incomplete


def _table(value: object, key: str | None = None) -> Mapping[str, object] | None:
    """Read a TOML table, optionally the table stored under ``key``."""
    if key is not None:
        parent = _table(value)
        if parent is None:
            return None
        value = parent.get(key)
    if isinstance(value, Mapping):
        # tomllib's stubs type every value loosely; the cast names the shape read.
        return cast("Mapping[str, object]", value)
    return None


def _sequence(value: object, key: str | None = None) -> Sequence[object]:
    """Read a TOML array, optionally the array stored under ``key``."""
    if key is not None:
        parent = _table(value)
        if parent is None:
            return ()
        value = parent.get(key)
    if isinstance(value, list):
        return cast("list[object]", value)
    return ()


def _string(value: object, key: str | None = None) -> str | None:
    """Read a TOML string, optionally the string stored under ``key``."""
    if key is not None:
        table = _table(value)
        if table is None:
            return None
        value = table.get(key)
    return value if isinstance(value, str) else None


def _first_string(values: Sequence[object]) -> str | None:
    if not values:
        return None
    first = values[0]
    return first if isinstance(first, str) else None
