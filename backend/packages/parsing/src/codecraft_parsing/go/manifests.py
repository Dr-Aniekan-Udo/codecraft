"""Read Go module and workspace files as data.

Every folder that holds a module file is a module. No Go command is run: module
files and workspace files are read as text, and every local replacement target
must resolve to a folder inside the repository.
"""

import posixpath
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from codecraft_core.model import GoModule, GoModuleSource

from codecraft_parsing.common.walker import MAX_FILE_BYTES, read_within_limit

MALFORMED_MODULE_REASON = "malformed module file"
UNREADABLE_MODULE_REASON = "module file cannot be read"
OUTSIDE_REPOSITORY_REASON = "replacement target is outside the repository"
MISSING_REPLACEMENT_REASON = "replacement target does not exist"
MISMATCHED_MODULE_PATH_REASON = "replacement target declares a different module path"

_RECOGNISED_DIRECTIVES = frozenset({"module", "go", "require", "replace", "exclude"})
_RECOGNISED_BLOCKS = frozenset({"require", "replace", "exclude"})


@dataclass(frozen=True)
class GoMod:
    module_path: str | None
    replacements: tuple[tuple[str, str], ...]
    failure_reason: str | None


@dataclass(frozen=True)
class GoWork:
    folders: tuple[str, ...]
    replacements: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class ModuleDiscovery:
    """Every module, every failed import route, and every failed module file."""

    modules: tuple[GoModule, ...]
    failures: dict[str, str]
    external_routes: frozenset[str]
    module_failures: dict[str, str]
    folder_failures: dict[str, str]
    folder_failure_paths: dict[str, str | None]
    module_folders: frozenset[str]
    failed_module_folders: frozenset[str]
    replacement_folders: frozenset[str]
    has_module_file: bool


def read_module_discovery(
    root: Path,
    go_mod_paths: Sequence[str],
    file_reasons: Mapping[str, str | None] | None = None,
) -> ModuleDiscovery:
    """Find every module and classify every replacement directive."""
    root_path = root.resolve()
    modules: list[GoModule] = []
    failures: dict[str, str] = {}
    external_routes: set[str] = set()
    module_failures: dict[str, str] = {}
    folder_failures: dict[str, str] = {}
    folder_failure_paths: dict[str, str | None] = {}
    module_folders: set[str] = set()
    failed_module_folders: set[str] = set()
    replacement_folders: set[str] = set()
    replacements: list[tuple[str, str, str]] = []

    reasons = file_reasons or {}
    for path in sorted(go_mod_paths):
        parsed = _read_go_mod(root_path / path, reasons.get(path))
        folder = posixpath.dirname(path) or "."
        module_folders.add(folder)
        if parsed.failure_reason is not None:
            module_failures[path] = parsed.failure_reason
            folder_failures[folder] = parsed.failure_reason
            folder_failure_paths[folder] = parsed.module_path
            failed_module_folders.add(folder)
            if parsed.module_path is not None:
                failures[parsed.module_path] = parsed.failure_reason
            continue
        if parsed.module_path is not None:
            _add_module(
                modules,
                parsed.module_path,
                folder,
                GoModuleSource.MODULE_FILE,
            )
        replacements.extend((folder, old, new) for old, new in parsed.replacements)

    work = _read_go_work(root_path / "go.work")
    _apply_workspace(root_path, modules, work.folders)
    replacements.extend((".", old, new) for old, new in work.replacements)
    for base_folder, old, new in replacements:
        _apply_replacement(
            root_path,
            modules,
            module_folders,
            replacement_folders,
            folder_failures,
            failures,
            external_routes,
            base_folder,
            old,
            new,
        )

    return ModuleDiscovery(
        modules=tuple(sorted(modules, key=lambda module: (module.module_path, module.folder))),
        failures=failures,
        external_routes=frozenset(external_routes),
        module_failures=module_failures,
        folder_failures=folder_failures,
        folder_failure_paths=folder_failure_paths,
        module_folders=frozenset(module_folders),
        failed_module_folders=frozenset(failed_module_folders),
        replacement_folders=frozenset(replacement_folders),
        has_module_file=bool(go_mod_paths),
    )


def _add_module(
    modules: list[GoModule],
    module_path: str,
    folder: str,
    source: GoModuleSource,
) -> None:
    for index, module in enumerate(modules):
        if module.module_path == module_path and module.folder == folder:
            modules[index] = GoModule(
                module_path=module_path,
                folder=folder,
                source=source,
            )
            return
    modules.append(GoModule(module_path=module_path, folder=folder, source=source))


def _apply_workspace(
    root: Path,
    modules: list[GoModule],
    folders: tuple[str, ...],
) -> None:
    for folder in folders:
        resolved = _resolve_folder(root, ".", folder)
        if resolved is None:
            continue
        for index, module in enumerate(modules):
            if module.folder == resolved and module.source == GoModuleSource.MODULE_FILE:
                modules[index] = GoModule(
                    module_path=module.module_path,
                    folder=module.folder,
                    source=GoModuleSource.WORKSPACE,
                )


def _apply_replacement(
    root: Path,
    modules: list[GoModule],
    module_folders: set[str],
    replacement_folders: set[str],
    folder_failures: dict[str, str],
    failures: dict[str, str],
    external_routes: set[str],
    base_folder: str,
    old: str,
    new: str,
) -> None:
    # A later directive, including go.work, replaces the earlier route.
    failures.pop(old, None)
    external_routes.discard(old)
    modules[:] = [
        module
        for module in modules
        if not (module.module_path == old and module.source == GoModuleSource.REPLACE)
    ]

    if not _is_local(new):
        external_routes.add(old)
        return
    folder, inside, exists = _resolve_candidate(root, base_folder, new)
    if not inside:
        failures[old] = OUTSIDE_REPOSITORY_REASON
        return
    if not exists or folder is None:
        failures[old] = MISSING_REPLACEMENT_REASON
        return
    replacement_folders.add(folder)
    if folder in module_folders:
        reason = folder_failures.get(folder)
        if reason is not None:
            failures[old] = reason
            return
        declarations = [module for module in modules if module.folder == folder]
        if declarations and all(module.module_path != old for module in declarations):
            # The folder declares another module path, so it does not own the
            # replaced path. Go rejects this replacement rather than guessing.
            failures[old] = MISMATCHED_MODULE_PATH_REASON
            return
        # A folder with its own module file keeps module_file as its source.
        _set_module_source(modules, folder, GoModuleSource.MODULE_FILE)
        return
    _add_module(modules, old, folder, GoModuleSource.REPLACE)


def _set_module_source(
    modules: list[GoModule],
    folder: str,
    source: GoModuleSource,
) -> None:
    for index, module in enumerate(modules):
        if module.folder == folder:
            modules[index] = GoModule(
                module_path=module.module_path,
                folder=module.folder,
                source=source,
            )
            return


def _read_go_mod(path: Path, unreadable_reason: str | None = None) -> GoMod:
    text = _read_text(path)
    if text is None:
        return GoMod(
            module_path=None,
            replacements=(),
            failure_reason=unreadable_reason or UNREADABLE_MODULE_REASON,
        )
    return parse_go_mod(text)


def parse_go_mod(text: str) -> GoMod:
    """Parse the directives the parser needs; ignore data it does not use.

    Unknown directives such as toolchain, godebug, tool, ignore and retract are
    data and are ignored. A recognised directive with invalid syntax is a
    malformed module file.
    """
    module_path: str | None = None
    replacements: list[tuple[str, str]] = []
    failure: str | None = None
    block: str | None = None

    for raw in text.splitlines():
        line = _strip_comment(raw).strip()
        if not line:
            continue
        if block is not None:
            if line == ")":
                block = None
                continue
            if line.startswith(")"):
                failure = failure or MALFORMED_MODULE_REASON
                block = None
                continue
            if block == "replace":
                replacement = _parse_replace(line)
                if replacement is None:
                    failure = failure or MALFORMED_MODULE_REASON
                else:
                    replacements.append(replacement)
            elif block in {"require", "exclude"} and len(_tokens(line)) != 2:
                failure = failure or MALFORMED_MODULE_REASON
            continue
        if line.endswith("("):
            head = line[:-1].strip()
            parts = _tokens(head)
            first = parts[0] if parts else ""
            if not first or head != first:
                # An opener with anything after the directive name is not a
                # valid block, whether or not the directive is one we use.
                failure = failure or MALFORMED_MODULE_REASON
            elif first in _RECOGNISED_DIRECTIVES and first not in _RECOGNISED_BLOCKS:
                failure = failure or MALFORMED_MODULE_REASON
            block = first
            continue
        parts = _tokens(line)
        directive = parts[0]
        if directive == "module":
            if len(parts) != 2 or module_path is not None:
                failure = failure or MALFORMED_MODULE_REASON
            else:
                value = _unquote(parts[1])
                if not value:
                    failure = failure or MALFORMED_MODULE_REASON
                else:
                    module_path = value
        elif directive == "go":
            if len(parts) != 2 or not _valid_go_version(parts[1]):
                failure = failure or MALFORMED_MODULE_REASON
        elif directive in {"require", "exclude"}:
            if len(parts) != 3:
                failure = failure or MALFORMED_MODULE_REASON
        elif directive == "replace":
            replacement = _parse_replace(line[len("replace") :].strip())
            if replacement is None:
                failure = failure or MALFORMED_MODULE_REASON
            else:
                replacements.append(replacement)
        elif directive not in _RECOGNISED_DIRECTIVES:
            # A directive the parser does not need is data, not a failure.
            continue
        else:
            failure = failure or MALFORMED_MODULE_REASON

    if block in _RECOGNISED_BLOCKS:
        failure = failure or MALFORMED_MODULE_REASON
    if module_path is None:
        failure = failure or MALFORMED_MODULE_REASON
    return GoMod(
        module_path=module_path,
        replacements=tuple(replacements),
        failure_reason=failure,
    )


def _valid_go_version(value: str) -> bool:
    return len(value) > 2 and value.startswith("1.") and value[2].isdigit()


def _read_go_work(path: Path) -> GoWork:
    text = _read_text(path)
    if text is None:
        return GoWork(folders=(), replacements=())

    folders: list[str] = []
    replacements: list[tuple[str, str]] = []
    block: str | None = None
    for raw in text.splitlines():
        line = _strip_comment(raw).strip()
        if not line:
            continue
        if block is not None:
            if line == ")":
                block = None
                continue
            if block == "use":
                folders.extend(_use_paths(line))
            elif block == "replace":
                replacement = _parse_replace(line)
                if replacement is not None:
                    replacements.append(replacement)
            continue
        if line == "use (":
            block = "use"
        elif line == "replace (":
            block = "replace"
        elif line.startswith("use "):
            folders.extend(_use_paths(line[len("use ") :]))
        elif line.startswith("replace "):
            replacement = _parse_replace(line[len("replace ") :].strip())
            if replacement is not None:
                replacements.append(replacement)
    return GoWork(folders=tuple(folders), replacements=tuple(replacements))


def _use_paths(text: str) -> tuple[str, ...]:
    return tuple(value for token in _tokens(text) if (value := _unquote(token)) is not None)


def _tokens(text: str) -> list[str]:
    """Split one manifest line, keeping a quoted path as one argument."""
    tokens: list[str] = []
    index = 0
    while index < len(text):
        while index < len(text) and text[index].isspace():
            index += 1
        if index >= len(text):
            break
        start = index
        quote = text[index] if text[index] in {'"', "`"} else None
        if quote is None:
            while index < len(text) and not text[index].isspace():
                index += 1
        else:
            index += 1
            while index < len(text):
                if quote == '"' and text[index] == "\\":
                    index += 2
                    continue
                if text[index] == quote:
                    index += 1
                    break
                index += 1
        tokens.append(text[start:index])
    return tokens


def _parse_replace(line: str) -> tuple[str, str] | None:
    left, separator, right = line.partition("=>")
    if not separator:
        return None
    left_parts = _tokens(left)
    right_parts = _tokens(right)
    if not left_parts or not right_parts or len(left_parts) > 2 or len(right_parts) > 2:
        return None
    old = _unquote(left_parts[0])
    new = _unquote(right_parts[0])
    if old is None or new is None:
        return None
    return old, new


def _is_local(value: str) -> bool:
    normalised = value.replace("\\", "/")
    return (
        normalised.startswith(".")
        or PurePosixPath(normalised).is_absolute()
        or (len(normalised) >= 2 and normalised[1] == ":")
    )


def _resolve_candidate(
    root: Path,
    base_folder: str,
    value: str,
) -> tuple[str | None, bool, bool]:
    """Return (relative folder, inside repository, folder exists)."""
    base = root if base_folder == "." else root / base_folder
    candidate = base / value.replace("\\", "/")
    try:
        resolved = candidate.resolve()
    except OSError:
        return None, False, False
    if not resolved.is_relative_to(root):
        return None, False, False
    if not resolved.is_dir():
        return None, True, False
    relative = resolved.relative_to(root).as_posix()
    return ("." if relative == "." else relative), True, True


def _resolve_folder(root: Path, base_folder: str, value: str) -> str | None:
    folder, inside, exists = _resolve_candidate(root, base_folder, value)
    return folder if inside and exists else None


def _read_text(path: Path) -> str | None:
    try:
        if path.is_symlink():
            return None
        data = read_within_limit(path, MAX_FILE_BYTES)
        if data is None:
            return None
        return data.decode("utf-8")
    except OSError, UnicodeDecodeError:
        return None


def _strip_comment(line: str) -> str:
    quote: str | None = None
    index = 0
    while index < len(line):
        character = line[index]
        if quote is not None:
            if character == quote:
                quote = None
        elif character in {'"', "`"}:
            quote = character
        elif character == "/" and index + 1 < len(line) and line[index + 1] == "/":
            return line[:index]
        index += 1
    return line


def _unquote(value: str) -> str | None:
    if value.startswith(('"', "`")):
        if len(value) >= 2 and value[-1] == value[0]:
            return value[1:-1]
        return None
    return value
