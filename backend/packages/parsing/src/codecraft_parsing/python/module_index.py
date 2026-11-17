"""Index the modules and packages the repository actually contains.

The index is built from walked paths only. Asking the file system whether a
module exists would answer with case-insensitive results on some platforms and
would see files the walk deliberately left out, which is how a graph gains
edges to files that are not part of the analysis.
"""

import posixpath
from collections.abc import Sequence
from dataclasses import dataclass

from codecraft_core.model import ExcludedDirectory, FileRecord


@dataclass(frozen=True)
class FileMatch:
    path: str
    module_name: str


@dataclass(frozen=True)
class NamespaceMatch:
    module_name: str


@dataclass(frozen=True)
class ExcludedMatch:
    reason: str


@dataclass(frozen=True)
class Missing:
    pass


@dataclass(frozen=True)
class MissingParent:
    pass


type Match = FileMatch | NamespaceMatch | ExcludedMatch | Missing | MissingParent


@dataclass(frozen=True)
class ModuleIndex:
    """Every module and package name under the import root, and how to resolve one."""

    module_files: dict[str, str]
    package_dirs: dict[str, str]
    regular_packages: frozenset[str]
    namespace_packages: frozenset[str]
    namespace_package_count: int
    excluded_files: dict[str, str]
    top_level_names: frozenset[str]
    pruned_directories: dict[str, str]

    def resolve(self, parts: tuple[str, ...]) -> Match:
        if not parts:
            return NamespaceMatch("")
        prefix = ""
        for part in parts[:-1]:
            prefix = f"{prefix}.{part}" if prefix else part
            if prefix not in self.package_dirs:
                return MissingParent()
            if prefix in self.module_files and prefix not in self.regular_packages:
                # A loose module of that name shadows a namespace folder of the
                # same name. A regular package (one with an __init__ file) still
                # wins and continues as before.
                return MissingParent()
        name = ".".join(parts)
        path = self.module_files.get(name)
        if path is not None:
            return FileMatch(path=path, module_name=name)
        reason = self.excluded_files.get(name)
        if reason is not None:
            return ExcludedMatch(reason)
        if name in self.package_dirs:
            return NamespaceMatch(name)
        return Missing()


def build_module_index(
    files: Sequence[FileRecord],
    directories: Sequence[str],
    excluded_directories: Sequence[ExcludedDirectory],
    import_root: str,
) -> ModuleIndex:
    file_paths = {record.path for record in files}

    # The import root is the repository namespace itself, named the empty string.
    package_dirs: dict[str, str] = {"": import_root}
    for directory in directories:
        relative = _relative_to_import_root(directory, import_root)
        if relative is None:
            continue
        package_dirs[_package_name(relative)] = directory

    regular_packages = frozenset(
        name for name, path in package_dirs.items() if _has_init(path, file_paths)
    )

    module_files: dict[str, str] = {}
    excluded_files: dict[str, str] = {}
    for record in files:
        details = record.python
        if not record.is_node or details is None or details.module is None:
            if not record.is_node and record.excluded_reason is not None:
                module = _excluded_module_name(record.path, import_root)
                if module is not None:
                    excluded_files[module] = record.excluded_reason
            continue
        if details.is_package:
            # An __init__ file is the package itself and wins over a loose module
            # of the same name, because that is what importing the name loads.
            module_files[details.module] = record.path
        else:
            module_files.setdefault(details.module, record.path)

    excluded_top_level = frozenset(name.split(".", 1)[0] for name in excluded_files)
    top_level_names = (
        frozenset(name.split(".", 1)[0] for name in (*module_files, *package_dirs) if name)
        | excluded_top_level
    )

    namespace_packages = frozenset(package_dirs) - regular_packages
    # The import root is a namespace itself, but it is not a named package. A
    # folder with no Python file beneath it is not a package this repository
    # contains either; counting it would overstate what the walk found.
    namespace_package_count = sum(
        1
        for name in namespace_packages
        if name and _contains_module(package_dirs[name], module_files)
    )

    pruned: dict[str, str] = {}
    for entry in excluded_directories:
        relative = _relative_to_import_root(entry.path.rstrip("/"), import_root)
        if relative is not None:
            pruned[relative] = entry.reason

    return ModuleIndex(
        module_files=module_files,
        package_dirs=package_dirs,
        regular_packages=regular_packages,
        namespace_packages=namespace_packages,
        namespace_package_count=namespace_package_count,
        excluded_files=excluded_files,
        top_level_names=top_level_names,
        pruned_directories=pruned,
    )


def _package_name(relative: str) -> str:
    return relative.replace("/", ".")


def _relative_to_import_root(path: str, import_root: str) -> str | None:
    if import_root == ".":
        return path
    if path.startswith(import_root + "/"):
        return path[len(import_root) + 1 :]
    return None


def _excluded_module_name(path: str, import_root: str) -> str | None:
    relative = _relative_to_import_root(path, import_root)
    if relative is None:
        return None
    if relative.endswith(".pyi"):
        stem = relative[: -len(".pyi")]
    elif relative.endswith(".py"):
        stem = relative[: -len(".py")]
    else:
        return None
    if stem == "__init__" or stem.endswith("/__init__"):
        stem = posixpath.dirname(stem)
    return stem.replace("/", ".") if stem else None


def _has_init(path: str, file_paths: set[str]) -> bool:
    return _join(path, "__init__.py") in file_paths


def _join(folder: str, name: str) -> str:
    return f"{folder}/{name}" if folder and folder != "." else name


def _contains_module(directory: str, module_files: dict[str, str]) -> bool:
    prefix = f"{directory}/"
    return any(path.startswith(prefix) for path in module_files.values())
