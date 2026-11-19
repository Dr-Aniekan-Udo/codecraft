"""Turn shared walked files into Go file records and package facts."""

import posixpath
from dataclasses import dataclass
from pathlib import Path

from codecraft_core.model import (
    AdapterRole,
    FileRecord,
    GoFileDetails,
    GoModuleSource,
    Language,
    ParseFailure,
)
from tree_sitter import Parser

from codecraft_parsing.common.walker import FileClassification, WalkedFile, WalkResult
from codecraft_parsing.go.constraints import read_build_constraints
from codecraft_parsing.go.manifests import ModuleDiscovery
from codecraft_parsing.go.source import RawGoImport, parse_go_file

_NOT_GO = "not a Go file"
CONFLICTING_PACKAGE_REASON = "conflicting package names in one folder"


@dataclass(frozen=True)
class BuiltGoFiles:
    """File records plus the imports each parsed node contributes."""

    files: list[FileRecord]
    imports: dict[str, tuple[RawGoImport, ...]]


def classify_go_file(name: str) -> FileClassification:
    if name.endswith(".go"):
        if name.startswith(("_", ".")):
            return FileClassification(False, None, "ignored by the Go tool")
        return FileClassification(True, Language.GO, None)
    return FileClassification(False, None, _NOT_GO)


def go_directory_reason(name: str, path: Path) -> str | None:
    if name == "vendor":
        return "vendored dependency"
    if name == "testdata":
        return "test data"
    if name.startswith(("_", ".")):
        return "ignored by the Go tool"
    return None


def build_go_files(
    walked: WalkResult,
    discovery: ModuleDiscovery,
    parser: Parser,
) -> BuiltGoFiles:
    files: list[FileRecord] = []
    imports: dict[str, tuple[RawGoImport, ...]] = {}

    for walked_file in walked.files:
        if not walked_file.is_node:
            files.append(_excluded_record(walked_file, discovery))
            continue
        data = walked_file.data
        if data is None:
            raise ValueError(f"node {walked_file.path} has no bytes")
        parsed = parse_go_file(data, parser)
        text = parsed.text
        constraints = read_build_constraints(walked_file.path, text or "")
        is_test = posixpath.basename(walked_file.path).endswith("_test.go")
        details = GoFileDetails(
            package=parsed.package,
            module_path=_module_path(walked_file.path, discovery),
            build_constraints=constraints.constraints,
            is_test=is_test,
            build_constraint_exclusion_reason=constraints.exclusion_reason,
        )
        files.append(
            FileRecord(
                path=walked_file.path,
                folder=walked_file.folder,
                language=Language.GO,
                line_count=len(data.splitlines()),
                content_hash=walked_file.content_hash,
                is_node=not constraints.excluded,
                excluded_reason=constraints.exclusion_reason,
                parse_failure=parsed.failure if not constraints.excluded else None,
                adapter_role=AdapterRole.FALLBACK,
                python=None,
                go=details,
            )
        )
        if not constraints.excluded:
            imports[walked_file.path] = parsed.imports

    _apply_conflicting_packages(files, imports)
    return BuiltGoFiles(files=files, imports=imports)


def package_count(files: list[FileRecord]) -> int:
    """Count distinct (folder, package name) pairs among Go nodes.

    A file with no package clause has no package name, so it is not a
    package and is not counted. It stays a node because the gap is visible.
    """
    pairs = {
        (record.folder, record.go.package)
        for record in files
        if record.is_node and record.go is not None and record.go.package
    }
    return len(pairs)


def _apply_conflicting_packages(
    files: list[FileRecord],
    imports: dict[str, tuple[RawGoImport, ...]],
) -> None:
    by_folder: dict[str, list[int]] = {}
    for index, record in enumerate(files):
        if record.is_node and record.go is not None and not record.go.is_test:
            by_folder.setdefault(record.folder, []).append(index)

    conflicting: set[int] = set()
    for indexes in by_folder.values():
        parsed: list[tuple[int, GoFileDetails]] = []
        for index in indexes:
            record = files[index]
            if record.go is not None:
                parsed.append((index, record.go))
        names = {details.package for _, details in parsed if details.package}
        if len(names) > 1:
            conflicting.update(index for index, _ in parsed if files[index].parse_failure is None)

    for index in conflicting:
        record = files[index]
        files[index] = record.model_copy(
            update={
                "parse_failure": ParseFailure(
                    reason=CONFLICTING_PACKAGE_REASON,
                    line=None,
                    column=None,
                )
            }
        )
        if record.path in imports:
            imports[record.path] = tuple(
                _as_failed_import(item, CONFLICTING_PACKAGE_REASON) for item in imports[record.path]
            )


def _as_failed_import(item: RawGoImport, reason: str) -> RawGoImport:
    if item.reference == "C":
        # The cgo pseudo-package has its own outcome, never a package failure.
        return item
    return RawGoImport(
        reference=item.reference,
        kind=item.kind,
        alias=item.alias,
        line=item.line,
        column=item.column,
        failure_reason=item.failure_reason,
        file_failure_reason=item.file_failure_reason or reason,
    )


def _module_path(path: str, discovery: ModuleDiscovery) -> str | None:
    folders = set(discovery.module_folders) | {module.folder for module in discovery.modules}
    candidates = [folder for folder in folders if folder == "." or path.startswith(f"{folder}/")]
    if not candidates:
        return None
    nearest = max(candidates, key=lambda folder: (len(folder), folder))
    if nearest in discovery.failed_module_folders:
        # A malformed module is still the nearest module boundary. Its path is
        # unknown, so the parent's path must not be used instead.
        return None
    entries = sorted(
        (module for module in discovery.modules if module.folder == nearest),
        key=lambda module: (module.source == GoModuleSource.REPLACE, module.module_path),
    )
    if not entries:
        return None
    return entries[0].module_path


def _excluded_record(walked: WalkedFile, discovery: ModuleDiscovery) -> FileRecord:
    failure: ParseFailure | None = None
    if posixpath.basename(walked.path) == "go.mod":
        reason = discovery.module_failures.get(walked.path)
        if reason is not None:
            failure = ParseFailure(reason=reason, line=None, column=None)
    return FileRecord(
        path=walked.path,
        folder=walked.folder,
        language=walked.language,
        line_count=walked.line_count,
        content_hash=walked.content_hash,
        is_node=False,
        excluded_reason=walked.excluded_reason,
        parse_failure=failure,
        adapter_role=AdapterRole.FALLBACK,
        python=None,
        go=None,
    )
