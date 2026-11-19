"""Turn a repository directory into the shared representation for Go.

Edges point at package folders, never at one file. Every import path is one
reference and is counted exactly once: a resolved package, a cgo pseudo-package,
an external path, an excluded package, or a named failure. Nothing here guesses
a target.
"""

import posixpath
from dataclasses import dataclass, field
from pathlib import Path

import tree_sitter_go
from codecraft_core.model import (
    CgoReference,
    CgoStatus,
    Edge,
    ExcludedDirectory,
    ExternalReference,
    FileRecord,
    GoBuildContext,
    GoCoverageDetails,
    GoModule,
    GoRepositoryDetails,
    ParseFailure,
    ReferenceRecord,
    RepositoryParse,
    TargetKind,
)
from tree_sitter import Language as TreeLanguage
from tree_sitter import Parser

from codecraft_parsing.common.output import build_repository_parse
from codecraft_parsing.common.walker import walk_repository
from codecraft_parsing.go.constraints import TARGET_ARCH, TARGET_OS
from codecraft_parsing.go.files import (
    CONFLICTING_PACKAGE_REASON,
    build_go_files,
    classify_go_file,
    go_directory_reason,
    package_count,
)
from codecraft_parsing.go.manifests import ModuleDiscovery, read_module_discovery
from codecraft_parsing.go.source import RawGoImport
from codecraft_parsing.go.version import PARSER_VERSION

_FOLDER_NOT_FOUND_REASON = "package folder not found in repository"
_NO_IMPORTABLE_PACKAGE_REASON = "package folder has no importable package"
_NO_MODULE_FILE_REASON = "no module file declares a path"
_MAIN_PACKAGE_REASON = "imports a main package"
_OTHER_MODULE_REASON = "package folder belongs to another module"
_TRAILING_SLASH_REASON = "import path ends with a slash"
_EMPTY_IMPORT_PATH_REASON = "import path is empty"
_CGO_IMPORT_PATH = "C"

type PackageMatch = (
    PackageAvailable
    | PackageMain
    | PackageConflict
    | PackageExcluded
    | PackageMissing
    | PackageNoImportable
)


@dataclass(frozen=True)
class PackageAvailable:
    pass


@dataclass(frozen=True)
class PackageMain:
    pass


@dataclass(frozen=True)
class PackageConflict:
    pass


@dataclass(frozen=True)
class PackageExcluded:
    reason: str


@dataclass(frozen=True)
class PackageMissing:
    pass


@dataclass(frozen=True)
class PackageNoImportable:
    pass


@dataclass(frozen=True)
class PackageIndex:
    """Resolve one package folder from the walked files, never from the disk."""

    directories: frozenset[str]
    excluded_directories: tuple[ExcludedDirectory, ...]
    records: dict[str, list[FileRecord]]

    def resolve(self, folder: str) -> PackageMatch:
        if folder not in self.directories:
            reason = self._excluded_reason(folder)
            return PackageExcluded(reason) if reason is not None else PackageMissing()
        records = self.records.get(folder, [])
        non_test = [
            record
            for record in records
            if record.is_node and record.go is not None and not record.go.is_test
        ]
        if not non_test:
            if any(record.is_node and record.go is not None for record in records):
                return PackageNoImportable()
            for record in records:
                if (
                    record.go is not None
                    and record.go.build_constraint_exclusion_reason is not None
                ):
                    return PackageExcluded(record.go.build_constraint_exclusion_reason)
            return PackageNoImportable()
        if any(_is_conflicting(record) for record in non_test):
            return PackageConflict()
        names = {
            record.go.package for record in non_test if record.go is not None and record.go.package
        }
        if not names:
            return PackageNoImportable()
        if names == {"main"}:
            return PackageMain()
        if len(names) > 1:
            return PackageConflict()
        return PackageAvailable()

    def _excluded_reason(self, folder: str) -> str | None:
        for entry in sorted(
            self.excluded_directories,
            key=lambda item: len(item.path),
            reverse=True,
        ):
            path = entry.path.rstrip("/")
            if folder == path or folder.startswith(f"{path}/"):
                return entry.reason
        return None


@dataclass
class _ResolutionOutcome:
    edges: list[Edge] = field(default_factory=list[Edge])
    cgo: list[CgoReference] = field(default_factory=list[CgoReference])
    unresolved: list[ReferenceRecord] = field(default_factory=list[ReferenceRecord])
    external: list[ExternalReference] = field(default_factory=list[ExternalReference])
    excluded: list[ReferenceRecord] = field(default_factory=list[ReferenceRecord])
    resolved: int = 0


def parse_go_repository(root: Path) -> RepositoryParse:
    """Parse a Go repository. Reads text only; never runs or builds it."""
    root_path = Path(root)
    if not root_path.is_dir():
        raise NotADirectoryError(str(root_path))
    root_path = root_path.resolve()

    walked = walk_repository(root_path, classify_go_file, go_directory_reason)
    go_mod_paths = [file.path for file in walked.files if posixpath.basename(file.path) == "go.mod"]
    discovery = read_module_discovery(
        root_path,
        go_mod_paths,
        {
            file.path: file.excluded_reason
            for file in walked.files
            if posixpath.basename(file.path) == "go.mod"
        },
    )
    parser = Parser(TreeLanguage(tree_sitter_go.language()))
    built = build_go_files(walked, discovery, parser)
    index = PackageIndex(
        directories=frozenset({".", *walked.directories}),
        excluded_directories=tuple(walked.excluded_directories),
        records=_records_by_folder(built.files),
    )

    outcome = _ResolutionOutcome()
    for record in built.files:
        if not record.is_node:
            continue
        for raw in built.imports.get(record.path, ()):
            _resolve(raw, record, discovery, index, outcome)

    return build_repository_parse(
        parser_version=PARSER_VERSION,
        language_details={
            "go": GoRepositoryDetails(
                build_context=GoBuildContext(os=TARGET_OS, arch=TARGET_ARCH),
                modules=discovery.modules,
            )
        },
        language_coverage_details={"go": GoCoverageDetails(packages=package_count(built.files))},
        files=built.files,
        excluded_directories=walked.excluded_directories,
        edges=outcome.edges,
        symbol_references=[],
        star_import_references=[],
        cgo_references=outcome.cgo,
        unresolved=outcome.unresolved,
        external=outcome.external,
        excluded=outcome.excluded,
        resolved=outcome.resolved,
    )


def _resolve(
    raw: RawGoImport,
    source: FileRecord,
    discovery: ModuleDiscovery,
    index: PackageIndex,
    outcome: _ResolutionOutcome,
) -> None:
    if raw.failure_reason is not None:
        _fail(outcome, source, raw, raw.failure_reason)
        return

    if raw.reference == _CGO_IMPORT_PATH:
        outcome.cgo.append(
            CgoReference(
                source=source.path,
                reference=raw.reference,
                status=CgoStatus.CGO_PSEUDO_PACKAGE,
                line=raw.line,
                column=raw.column,
            )
        )
        return

    module_failure = _failed_module_reason(source.path, discovery)
    if module_failure is not None:
        _fail(outcome, source, raw, module_failure)
        return

    winning_failure = _winning_failure_before_invalid(raw.reference, discovery)
    if winning_failure is not None:
        _fail(outcome, source, raw, winning_failure)
        return

    if not discovery.has_module_file:
        _fail(outcome, source, raw, _NO_MODULE_FILE_REASON)
        return

    if raw.reference.endswith("/"):
        _fail(outcome, source, raw, _TRAILING_SLASH_REASON)
        return

    if not raw.reference:
        _fail(outcome, source, raw, _EMPTY_IMPORT_PATH_REASON)
        return

    module = _module_for(raw.reference, discovery.modules, discovery.replacement_targets)
    failure_route = _route_match(raw.reference, discovery.failures)
    external_route = _longest_route(raw.reference, discovery.external_routes)
    route_kind: str | None = None
    route_reason: str | None = None
    route_length = -1
    if failure_route is not None:
        route_kind = "failure"
        route_reason = failure_route[1]
        route_length = len(failure_route[0])
    if external_route is not None and len(external_route) > route_length:
        route_kind = "external"
        route_reason = None
        route_length = len(external_route)

    if module is not None and len(module.module_path) > route_length:
        pass
    elif route_kind == "failure":
        _fail(outcome, source, raw, route_reason or "replacement target does not exist")
        return
    elif route_kind == "external":
        _external(outcome, source, raw)
        return
    elif module is None:
        # An outside path stays external; whether the importing file parses
        # does not change whether its package is external.
        _external(outcome, source, raw)
        return

    if raw.file_failure_reason is not None:
        _fail(outcome, source, raw, raw.file_failure_reason)
        return

    target = _target_folder(module, raw.reference)
    owner = _module_at_folder(target, discovery.modules)
    failed_folder = _failed_folder_at(target, discovery)
    if failed_folder is not None and (
        owner is None or _folder_depth(owner.folder) <= _folder_depth(failed_folder)
    ):
        _fail(outcome, source, raw, discovery.folder_failures[failed_folder])
        return
    if owner is not None and owner.module_path != module.module_path:
        _fail(outcome, source, raw, _OTHER_MODULE_REASON)
        return
    match index.resolve(target):
        case PackageAvailable():
            outcome.resolved += 1
            outcome.edges.append(
                Edge(
                    source=source.path,
                    target=target,
                    target_kind=TargetKind.PACKAGE,
                    kind=raw.kind,
                    condition=None,
                    alias=raw.alias,
                    line=raw.line,
                    column=raw.column,
                )
            )
        case PackageMain():
            _fail(outcome, source, raw, _MAIN_PACKAGE_REASON)
        case PackageConflict():
            _fail(outcome, source, raw, CONFLICTING_PACKAGE_REASON)
        case PackageExcluded(reason):
            outcome.excluded.append(
                ReferenceRecord(
                    source=source.path,
                    reference=raw.reference,
                    reason=reason,
                    line=raw.line,
                    column=raw.column,
                )
            )
        case PackageMissing():
            _fail(outcome, source, raw, _FOLDER_NOT_FOUND_REASON)
        case PackageNoImportable():
            _fail(outcome, source, raw, _NO_IMPORTABLE_PACKAGE_REASON)


def _external(outcome: _ResolutionOutcome, source: FileRecord, raw: RawGoImport) -> None:
    outcome.external.append(
        ExternalReference(
            source=source.path,
            reference=raw.reference,
            top_level=raw.reference.split("/", 1)[0],
            line=raw.line,
            column=raw.column,
        )
    )


def _fail(outcome: _ResolutionOutcome, source: FileRecord, raw: RawGoImport, reason: str) -> None:
    outcome.unresolved.append(
        ReferenceRecord(
            source=source.path,
            reference=raw.reference,
            reason=reason,
            line=raw.line,
            column=raw.column,
        )
    )


def _route_match(path: str, routes: dict[str, str]) -> tuple[str, str] | None:
    matches = [
        (prefix, reason)
        for prefix, reason in routes.items()
        if path == prefix or path.startswith(f"{prefix}/")
    ]
    return max(matches, key=lambda item: len(item[0])) if matches else None


def _longest_route(path: str, routes: frozenset[str]) -> str | None:
    matches = [prefix for prefix in routes if path == prefix or path.startswith(f"{prefix}/")]
    return max(matches, key=len) if matches else None


def _winning_failure_before_invalid(
    path: str,
    discovery: ModuleDiscovery,
) -> str | None:
    failure = _route_match(path, discovery.failures)
    if failure is None:
        return None
    external = _longest_route(path, discovery.external_routes)
    if external is not None and len(external) > len(failure[0]):
        return None
    module = _module_for(path, discovery.modules, discovery.replacement_targets)
    if module is not None and len(module.module_path) > len(failure[0]):
        return None
    return failure[1]


def _failed_module_reason(
    path: str,
    discovery: ModuleDiscovery,
) -> str | None:
    folders = set(discovery.module_folders) | {module.folder for module in discovery.modules}
    candidates = [folder for folder in folders if folder == "." or path.startswith(f"{folder}/")]
    if not candidates:
        return None
    nearest = max(candidates, key=lambda folder: (len(folder), folder))
    reason = discovery.folder_failures.get(nearest)
    if reason is None:
        return None
    module_path = discovery.folder_failure_paths.get(nearest)
    if module_path is None:
        return reason
    # A readable path is compared with healthy modules by specificity later.
    return None


def _module_for(
    path: str,
    modules: tuple[GoModule, ...],
    replacement_targets: dict[str, str],
) -> GoModule | None:
    matches = [
        module
        for module in modules
        if path == module.module_path or path.startswith(f"{module.module_path}/")
    ]
    if not matches:
        return None
    return max(
        matches,
        key=lambda module: (
            len(module.module_path),
            replacement_targets.get(module.module_path) == module.folder,
            module.module_path,
        ),
    )


def _folder_depth(folder: str) -> int:
    return 0 if folder == "." else folder.count("/") + 1


def _failed_folder_at(folder: str, discovery: ModuleDiscovery) -> str | None:
    matches = [
        failed
        for failed in discovery.failed_module_folders
        if failed == "." or folder == failed or folder.startswith(f"{failed}/")
    ]
    return max(matches, key=len) if matches else None


def _module_at_folder(folder: str, modules: tuple[GoModule, ...]) -> GoModule | None:
    matches = [
        module
        for module in modules
        if module.folder == "." or folder == module.folder or folder.startswith(f"{module.folder}/")
    ]
    if not matches:
        return None
    return max(matches, key=lambda module: (len(module.folder), module.module_path))


def _target_folder(module: GoModule, path: str) -> str:
    remainder = "" if path == module.module_path else path[len(module.module_path) + 1 :]
    if not remainder:
        return module.folder
    if module.folder == ".":
        return remainder
    return f"{module.folder}/{remainder}"


def _records_by_folder(files: list[FileRecord]) -> dict[str, list[FileRecord]]:
    records: dict[str, list[FileRecord]] = {}
    for record in files:
        if record.go is not None:
            records.setdefault(record.folder, []).append(record)
    return records


def _is_conflicting(record: FileRecord) -> bool:
    failure: ParseFailure | None = record.parse_failure
    return failure is not None and failure.reason == CONFLICTING_PACKAGE_REASON


__all__ = ["parse_go_repository"]
