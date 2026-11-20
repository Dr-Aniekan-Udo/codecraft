"""Turn a repository directory into the shared representation for Python.

Every reference seen is counted exactly once: resolved (with an edge when it
lands on a file), a symbol of a resolved module, external, excluded, or failed
with a named reason. Nothing here guesses a target: a reference that does not
resolve is recorded. An explicit import always draws its edge; only a relative
import's own or ancestor package base is already loaded and draws none.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

import tree_sitter_python
from codecraft_core.model import (
    Edge,
    ExternalReference,
    FileRecord,
    Language,
    ParseFailure,
    PythonCoverageDetails,
    PythonFileDetails,
    PythonRepositoryDetails,
    ReferenceRecord,
    RepositoryParse,
    StarImportRecord,
    StarImportStatus,
    SymbolRecord,
    SymbolStatus,
    TargetKind,
)
from tree_sitter import Language as TreeLanguage
from tree_sitter import Node, Parser

from codecraft_parsing.common.output import build_repository_parse
from codecraft_parsing.common.walker import (
    FileClassification,
    walk_repository,
)
from codecraft_parsing.python.files import build_python_files
from codecraft_parsing.python.import_root import detect_import_root
from codecraft_parsing.python.imports import RawImport, SourceText, read_imports
from codecraft_parsing.python.module_index import (
    ExcludedMatch,
    FileMatch,
    Missing,
    MissingParent,
    ModuleIndex,
    NamespaceMatch,
    build_module_index,
)
from codecraft_parsing.python.version import PARSER_VERSION

_RELATIVE_OUTSIDE_ROOT = "relative import in a file outside the import root"
_RELATIVE_ABOVE_TOP = "relative import climbs above the top-level package"
_PARENT_NOT_PACKAGE = "parent module is not a package"
_MODULE_NOT_FOUND = "module not found in repository"


def parse_python_repository(root: Path) -> RepositoryParse:
    """Parse a Python repository. Reads text only; never runs or imports it."""
    root_path = Path(root)
    if not root_path.is_dir():
        raise NotADirectoryError(str(root_path))
    root_path = root_path.resolve()

    import_root, import_root_rule = detect_import_root(root_path)
    walked = walk_repository(root_path, _classify_python_file)
    files, sources = build_python_files(walked, import_root)
    index = build_module_index(files, walked.directories, walked.excluded_directories, import_root)
    records: dict[str, FileRecord] = {record.path: record for record in files}

    parser = Parser(TreeLanguage(tree_sitter_python.language()))
    outcome = _Outcome(chains={record.path: _package_chain(record) for record in files})
    parse_failures: dict[str, ParseFailure] = {}

    for record in files:
        text = sources.get(record.path)
        if text is None:
            # Not a node, or a node whose source could not be decoded. The second
            # case already carries its parse failure from the file builder.
            continue
        try:
            encoded = text.encode("utf-8")
        except UnicodeEncodeError:
            # The decoder accepted the file's declared encoding but the result
            # is not representable in UTF-8, so the grammar cannot read it.
            parse_failures[record.path] = ParseFailure(
                reason="cannot encode source as UTF-8", line=None, column=None
            )
            continue
        source = SourceText.from_text(text)
        tree = parser.parse(encoded)
        failure = _first_syntax_problem(tree.root_node, source)
        if failure is not None:
            # A file that does not parse contributes no edges, but keeps its node
            # and its module so the gap stays visible on the map.
            parse_failures[record.path] = failure
            continue
        for raw_import in read_imports(tree, source):
            _resolve(raw_import, record, index, records, outcome)

    files = [
        record.model_copy(
            update={"parse_failure": parse_failures.get(record.path, record.parse_failure)}
        )
        for record in files
    ]

    return build_repository_parse(
        parser_version=PARSER_VERSION,
        language_details={
            "python": PythonRepositoryDetails(
                import_root=import_root,
                import_root_rule=import_root_rule,
            )
        },
        language_coverage_details={
            "python": PythonCoverageDetails(namespace_packages=index.namespace_package_count)
        },
        files=files,
        excluded_directories=walked.excluded_directories,
        edges=outcome.edges,
        symbol_references=outcome.symbols,
        star_import_references=outcome.stars,
        cgo_references=[],
        unresolved=outcome.unresolved,
        external=outcome.external,
        excluded=outcome.excluded,
        resolved=outcome.resolved,
    )


def _classify_python_file(name: str) -> FileClassification:
    if name.endswith(".pyi"):
        return FileClassification(False, Language.PYTHON, "stub file")
    if name.endswith(".py"):
        return FileClassification(True, Language.PYTHON, None)
    return FileClassification(False, None, "not a Python file")


@dataclass
class _Outcome:
    """The running totals while every file is resolved."""

    edges: list[Edge] = field(default_factory=list[Edge])
    symbols: list[SymbolRecord] = field(default_factory=list[SymbolRecord])
    stars: list[StarImportRecord] = field(default_factory=list[StarImportRecord])
    unresolved: list[ReferenceRecord] = field(default_factory=list[ReferenceRecord])
    external: list[ExternalReference] = field(default_factory=list[ExternalReference])
    excluded: list[ReferenceRecord] = field(default_factory=list[ReferenceRecord])
    resolved: int = 0
    chains: dict[str, frozenset[str]] = field(default_factory=dict[str, frozenset[str]])


def _resolve(
    raw: RawImport,
    source: FileRecord,
    index: ModuleIndex,
    records: Mapping[str, FileRecord],
    outcome: _Outcome,
) -> None:
    if raw.failure_reason is not None:
        outcome.unresolved.append(
            ReferenceRecord(
                source=source.path,
                reference=raw.reference,
                reason=raw.failure_reason,
                line=raw.line,
                column=raw.column,
            )
        )
        return
    if raw.is_relative:
        _resolve_relative(raw, source, index, records, outcome)
    else:
        _resolve_absolute(raw, source, index, records, outcome)


def _resolve_relative(
    raw: RawImport,
    source: FileRecord,
    index: ModuleIndex,
    records: Mapping[str, FileRecord],
    outcome: _Outcome,
) -> None:
    if raw.anchor is not None:
        pruned_reason = _pruned_reason(raw.anchor, index)
        if pruned_reason is not None:
            _exclude(outcome, source, raw, reason=pruned_reason)
            return
        if raw.anchor[0] not in index.top_level_names:
            # The package argument names a package outside the repository; the
            # reference is external, named by that package, not a failure.
            # importlib measures the relative name from it.
            outcome.external.append(
                ExternalReference(
                    source=source.path,
                    reference=raw.reference,
                    top_level=raw.anchor[0],
                    line=raw.line,
                    column=raw.column,
                )
            )
            return
        package_parts = raw.anchor
    else:
        details = _python_details(source)
        if details is None or details.module is None:
            _fail(outcome, source, raw, _RELATIVE_OUTSIDE_ROOT)
            return
        package_parts = _package_parts(details.module, details.is_package)
    if raw.levels_up >= len(package_parts):
        _fail(outcome, source, raw, _RELATIVE_ABOVE_TOP)
        return
    target = package_parts[: len(package_parts) - raw.levels_up] + raw.parts
    if _resolve_base(raw, target, source, index, records, outcome):
        _record_star(raw, target, source, outcome)
        _resolve_names(raw, target, source, index, records, outcome)


def _resolve_absolute(
    raw: RawImport,
    source: FileRecord,
    index: ModuleIndex,
    records: Mapping[str, FileRecord],
    outcome: _Outcome,
) -> None:
    if raw.parts and raw.parts[0] not in index.top_level_names:
        pruned_reason = _pruned_reason(raw.parts, index)
        if pruned_reason is not None:
            _exclude(outcome, source, raw, reason=pruned_reason)
        else:
            # A name the repository does not define is external, never a failure:
            # the standard library and installed packages are not our concern.
            outcome.external.append(
                ExternalReference(
                    source=source.path,
                    reference=raw.reference,
                    top_level=raw.parts[0],
                    line=raw.line,
                    column=raw.column,
                )
            )
        return
    if _resolve_base(raw, raw.parts, source, index, records, outcome):
        _record_star(raw, raw.parts, source, outcome)
        _resolve_names(raw, raw.parts, source, index, records, outcome)


def _resolve_base(
    raw: RawImport,
    target: tuple[str, ...],
    source: FileRecord,
    index: ModuleIndex,
    records: Mapping[str, FileRecord],
    outcome: _Outcome,
) -> bool:
    """Resolve the base module of a reference and report whether names may follow."""
    match index.resolve(target):
        case FileMatch() as file_match:
            _resolved_file(file_match, raw, source, records, outcome)
            return True
        case NamespaceMatch():
            # A star import's base is not also a resolved reference; its single
            # coverage entry is the star record added by _record_star.
            if not raw.is_star:
                outcome.resolved += 1
            return True
        case ExcludedMatch(reason):
            _exclude(outcome, source, raw, reason=reason)
            return False
        case MissingParent():
            pruned_reason = _pruned_reason(target, index)
            if pruned_reason is not None:
                _exclude(outcome, source, raw, reason=pruned_reason)
            else:
                excluded_reason = _excluded_target_reason(target, index)
                if excluded_reason is not None:
                    _exclude(outcome, source, raw, reason=excluded_reason)
                else:
                    _fail(outcome, source, raw, _PARENT_NOT_PACKAGE)
            return False
        case Missing():
            pruned_reason = _pruned_reason(target, index)
            if pruned_reason is not None:
                _exclude(outcome, source, raw, reason=pruned_reason)
            else:
                excluded_reason = _excluded_target_reason(target, index)
                if excluded_reason is not None:
                    _exclude(outcome, source, raw, reason=excluded_reason)
                else:
                    _fail(outcome, source, raw, _MODULE_NOT_FOUND)
            return False


def _record_star(
    raw: RawImport,
    target: tuple[str, ...],
    source: FileRecord,
    outcome: _Outcome,
) -> None:
    if not raw.is_star:
        return
    # A star import is one reference, counted in star_imports, not also resolved
    # even when its base draws an edge. No names are written in the source, so
    # there is nothing per name to record.
    outcome.stars.append(
        StarImportRecord(
            source=source.path,
            module=".".join(target),
            status=StarImportStatus.NAMES_NOT_ENUMERATED,
            line=raw.line,
            column=raw.column,
        )
    )


def _resolve_names(
    raw: RawImport,
    target: tuple[str, ...],
    source: FileRecord,
    index: ModuleIndex,
    records: Mapping[str, FileRecord],
    outcome: _Outcome,
) -> None:
    for name in raw.names:
        reference = ".".join((*target, name))
        match index.resolve((*target, name)):
            case FileMatch() as file_match:
                _resolved_file(file_match, raw, source, records, outcome)
            case NamespaceMatch():
                outcome.resolved += 1
            case ExcludedMatch(reason):
                _exclude(outcome, source, raw, reference, reason=reason)
            case Missing() | MissingParent():
                pruned_reason = _pruned_reason((*target, name), index)
                if pruned_reason is not None:
                    _exclude(outcome, source, raw, reference, reason=pruned_reason)
                else:
                    # A name that is not a module is a symbol of the base module.
                    # It is not an edge; it is recorded per name so the map can
                    # show exactly what was not verified.
                    outcome.symbols.append(
                        SymbolRecord(
                            source=source.path,
                            module=".".join(target),
                            name=name,
                            status=SymbolStatus.UNVERIFIED,
                            line=raw.line,
                            column=raw.column,
                        )
                    )


def _resolved_file(
    match: FileMatch,
    raw: RawImport,
    source: FileRecord,
    records: Mapping[str, FileRecord],
    outcome: _Outcome,
) -> None:
    if not raw.is_star:
        # A star import's base moves its one reference to star_imports instead;
        # _record_star writes that record and its edge is still drawn below.
        outcome.resolved += 1
    if _suppressed(match, raw, source, records, outcome):
        return
    outcome.edges.append(
        Edge(
            source=source.path,
            target=match.path,
            target_kind=TargetKind.FILE,
            kind=raw.kind,
            condition=raw.condition,
            line=raw.line,
            column=raw.column,
        )
    )


def _suppressed(
    match: FileMatch,
    raw: RawImport,
    source: FileRecord,
    records: Mapping[str, FileRecord],
    outcome: _Outcome,
) -> bool:
    if not raw.is_relative:
        # An explicit import always draws its edge, even when it names the file's
        # own package. Only a relative import's base is implicit: loading the
        # module already loaded the package chain, so no new connection is drawn.
        return False
    target = records.get(match.path)
    target_details = None if target is None else target.python
    if target_details is None or not target_details.is_package:
        return False
    return match.module_name in outcome.chains.get(source.path, frozenset())


def _python_details(source: FileRecord) -> PythonFileDetails | None:
    return source.python


def _package_parts(module: str, is_package: bool) -> tuple[str, ...]:
    parts = tuple(module.split("."))
    return parts if is_package else parts[:-1]


def _package_chain(source: FileRecord) -> frozenset[str]:
    details = source.python
    if details is None or details.module is None:
        return frozenset()
    parts = details.module.split(".")
    if not details.is_package:
        parts = parts[:-1]
    return frozenset(".".join(parts[: index + 1]) for index in range(len(parts)))


def _fail(outcome: _Outcome, source: FileRecord, raw: RawImport, reason: str) -> None:
    outcome.unresolved.append(
        ReferenceRecord(
            source=source.path,
            reference=raw.reference,
            reason=reason,
            line=raw.line,
            column=raw.column,
        )
    )


def _exclude(
    outcome: _Outcome,
    source: FileRecord,
    raw: RawImport,
    reference: str | None = None,
    *,
    reason: str,
) -> None:
    outcome.excluded.append(
        ReferenceRecord(
            source=source.path,
            reference=raw.reference if reference is None else reference,
            reason=reason,
            line=raw.line,
            column=raw.column,
        )
    )


def _pruned_reason(parts: tuple[str, ...], index: ModuleIndex) -> str | None:
    candidate = "/".join(parts)
    for directory, reason in sorted(
        index.pruned_directories.items(), key=lambda item: len(item[0]), reverse=True
    ):
        if candidate == directory or candidate.startswith(f"{directory}/"):
            return reason
    return None


def _excluded_target_reason(parts: tuple[str, ...], index: ModuleIndex) -> str | None:
    for length in range(len(parts), 0, -1):
        reason = index.excluded_files.get(".".join(parts[:length]))
        if reason is not None:
            return reason
    return None


def _first_syntax_problem(root: Node, source: SourceText) -> ParseFailure | None:
    if not root.has_error:
        return None
    stack: list[Node] = [root]
    while stack:
        node = stack.pop()
        if node.is_error or node.is_missing:
            line, column = source.position(node)
            reason = "syntax error" if node.is_error else f'syntax error: missing "{node.type}"'
            return ParseFailure(reason=reason, line=line, column=column)
        stack.extend(reversed(node.children))
    return None
