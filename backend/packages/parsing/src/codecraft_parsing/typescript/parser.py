"""Turn a repository directory into the shared representation for TypeScript.

The compiler's resolver decides every module target. This parser reads syntax,
asks the helper once for the whole repository, and records each reference's
outcome exactly once.
"""

from dataclasses import dataclass, field
from pathlib import Path

import tree_sitter_javascript
import tree_sitter_typescript
from codecraft_core.model import (
    Edge,
    EdgeKind,
    ExternalReference,
    FileRecord,
    ParseFailure,
    ReferenceRecord,
    RepositoryParse,
    ResolutionPath,
    TargetKind,
    TypeScriptCoverageDetails,
    TypeScriptRepositoryDetails,
)
from tree_sitter import Language as TreeLanguage
from tree_sitter import Parser

from codecraft_parsing.common.output import build_repository_parse
from codecraft_parsing.common.walker import FileClassification, walk_repository
from codecraft_parsing.typescript.files import (
    build_typescript_files,
    classify_typescript_file,
    file_language,
)
from codecraft_parsing.typescript.imports import (
    RawReference,
    SourceText,
    first_syntax_problem,
    has_asset_extension,
    read_references,
)
from codecraft_parsing.typescript.resolver import (
    Resolution,
    ResolutionRequest,
    ResolverFailure,
    ResolverResponse,
    resolve_references,
)
from codecraft_parsing.typescript.version import parser_version

_NOT_SOURCE = "not a TypeScript or JavaScript file"
_SYNTAX_REASON = "file has a syntax error"
_DEPENDENCY_DIRECTORY = "node_modules"


def parse_typescript_repository(
    root: Path,
    *,
    max_file_count: int,
    max_file_bytes: int,
) -> RepositoryParse:
    """Parse a TypeScript or JavaScript repository. Reads text only."""
    root_path = Path(root)
    if not root_path.is_dir():
        raise NotADirectoryError(str(root_path))
    root_path = root_path.resolve()

    walked = walk_repository(
        root_path,
        _classify_typescript_file,
        max_file_count=max_file_count,
        max_file_bytes=max_file_bytes,
    )
    files, sources = build_typescript_files(walked)
    records: dict[str, FileRecord] = {record.path: record for record in files}
    parsers = _parsers()

    raw_by_file: dict[str, list[RawReference]] = {}
    failures: dict[str, ParseFailure] = {}
    for record in files:
        text = sources.get(record.path)
        if text is None:
            continue
        source = SourceText.from_text(text)
        try:
            encoded = text.encode("utf-8")
        except UnicodeEncodeError:
            failures[record.path] = ParseFailure(
                reason="cannot encode source as UTF-8", line=None, column=None
            )
            continue
        tree = parsers[_parser_key(record.path)].parse(encoded)
        raw_by_file[record.path] = read_references(tree, source)
        failure = first_syntax_problem(tree.root_node, source)
        if failure is not None:
            failures[record.path] = failure

    identified = _identify(raw_by_file)
    requests = tuple(
        ResolutionRequest(
            id=item.id,
            source=item.source,
            specifier=item.raw.reference,
            kind="asset" if item.raw.asset else "module",
        )
        for item in identified
        if item.raw.failure_reason is None
    )

    resolver_response: ResolverResponse | None = None
    resolver_failure: str | None = None
    try:
        resolver_response = resolve_references(root_path, requests, max_file_bytes=max_file_bytes)
    except ResolverFailure as error:
        resolver_failure = error.reason

    outcome = _Outcome()
    for item in identified:
        raw = item.raw
        if raw.is_re_export:
            outcome.re_exports_found += 1
        if raw.failure_reason is not None:
            outcome.unresolved.append(_reference_record(item, raw.failure_reason))
            continue
        if item.source in failures:
            _failed_file_reference(
                item,
                resolver_response,
                outcome,
                failures[item.source],
            )
            continue
        if resolver_response is None:
            outcome.unresolved.append(
                _reference_record(item, resolver_failure or "js resolver failed")
            )
            continue
        result = resolver_response.results.get(item.id)
        if result is None:
            outcome.unresolved.append(
                _reference_record(item, "js resolver returned an invalid response")
            )
            continue
        _apply_resolution(item, result, records, outcome)

    files = [
        record.model_copy(update={"parse_failure": failures.get(record.path, record.parse_failure)})
        for record in sorted(records.values(), key=lambda item: item.path)
    ]
    typescript_version = (
        resolver_response.typescript_version if resolver_response is not None else "unknown"
    )
    config_files = resolver_response.config_files if resolver_response is not None else ()

    return build_repository_parse(
        parser_version=parser_version(typescript_version),
        language_details={"typescript": TypeScriptRepositoryDetails(config_files=config_files)},
        language_coverage_details={
            "typescript": TypeScriptCoverageDetails(
                re_exports=outcome.re_exports_found,
                re_exports_resolved=outcome.re_exports_resolved,
            )
        },
        files=files,
        excluded_directories=walked.excluded_directories,
        edges=outcome.edges,
        symbol_references=[],
        star_import_references=[],
        cgo_references=[],
        unresolved=outcome.unresolved,
        external=outcome.external,
        excluded=outcome.excluded,
        resolved=outcome.resolved,
    )


def _classify_typescript_file(name: str) -> FileClassification:
    if classify_typescript_file(name):
        return FileClassification(True, file_language(name), None)
    return FileClassification(False, None, _NOT_SOURCE)


def _parser_key(path: str) -> str:
    if path.endswith(".tsx"):
        return "tsx"
    if path.endswith((".ts", ".mts", ".cts")):
        return "ts"
    return "js"


def _parsers() -> dict[str, Parser]:
    return {
        "ts": Parser(TreeLanguage(tree_sitter_typescript.language_typescript())),
        "tsx": Parser(TreeLanguage(tree_sitter_typescript.language_tsx())),
        "js": Parser(TreeLanguage(tree_sitter_javascript.language())),
    }


@dataclass(frozen=True)
class _IdentifiedReference:
    id: str
    source: str
    raw: RawReference


@dataclass
class _Outcome:
    edges: list[Edge] = field(default_factory=list[Edge])
    unresolved: list[ReferenceRecord] = field(default_factory=list[ReferenceRecord])
    external: list[ExternalReference] = field(default_factory=list[ExternalReference])
    excluded: list[ReferenceRecord] = field(default_factory=list[ReferenceRecord])
    resolved: int = 0
    re_exports_found: int = 0
    re_exports_resolved: int = 0


def _identify(raw_by_file: dict[str, list[RawReference]]) -> list[_IdentifiedReference]:
    identified: list[_IdentifiedReference] = []
    counter = 0
    for path in sorted(raw_by_file):
        for raw in raw_by_file[path]:
            counter += 1
            identified.append(_IdentifiedReference(id=f"r{counter:06d}", source=path, raw=raw))
    return identified


def _apply_resolution(
    item: _IdentifiedReference,
    result: Resolution,
    records: dict[str, FileRecord],
    outcome: _Outcome,
) -> None:
    raw = item.raw
    if result.reason is not None:
        if raw.asset:
            outcome.unresolved.append(_reference_record(item, result.reason))
        elif _is_bare(raw.reference) and result.reason in {
            "module not found",
            "resolved path is outside the repository",
        }:
            outcome.external.append(_external_record(item))
        else:
            outcome.unresolved.append(_reference_record(item, result.reason))
        return

    path = result.resolved_path
    if path is None:
        outcome.unresolved.append(_reference_record(item, "module not found"))
        return
    if _is_dependency_path(path):
        if _is_bare(raw.reference):
            outcome.external.append(_external_record(item))
        else:
            outcome.excluded.append(_reference_record(item, "dependency installation"))
        return

    target = records.get(path)
    if raw.asset:
        asset = _promote_asset(path, records)
        if asset is None:
            if target is not None and target.excluded_reason is not None:
                outcome.excluded.append(_reference_record(item, target.excluded_reason))
            else:
                outcome.unresolved.append(_reference_record(item, "asset path matches no file"))
            return
        if raw.is_re_export:
            _add_edge(
                item,
                asset,
                result,
                outcome,
                kind=EdgeKind.RE_EXPORT,
                resolution=ResolutionPath.ASSET,
            )
        else:
            _add_edge(item, asset, result, outcome, kind=EdgeKind.ASSET_IMPORT)
        return

    if target is None:
        outcome.unresolved.append(_reference_record(item, "module not found"))
        return
    if not target.is_node:
        if has_asset_extension(path) and target.excluded_reason == _NOT_SOURCE:
            asset = _promote_asset(path, records)
            if asset is not None:
                _add_edge(item, asset, result, outcome, kind=EdgeKind.ASSET_IMPORT)
                return
        reason = target.excluded_reason or "module not found"
        outcome.excluded.append(_reference_record(item, reason))
        return
    if has_asset_extension(path):
        _add_edge(item, target, result, outcome, kind=EdgeKind.ASSET_IMPORT)
        return
    _add_edge(item, target, result, outcome, kind=raw.kind)


def _add_edge(
    item: _IdentifiedReference,
    target: FileRecord,
    result: Resolution,
    outcome: _Outcome,
    *,
    kind: EdgeKind,
    resolution: ResolutionPath | None = None,
) -> None:
    resolution_path = resolution if resolution is not None else result.resolution_path
    if resolution_path is None:
        outcome.unresolved.append(
            _reference_record(item, "js resolver returned an invalid response")
        )
        return
    raw = item.raw
    outcome.edges.append(
        Edge(
            source=item.source,
            target=target.path,
            target_kind=TargetKind.FILE,
            kind=kind,
            condition=raw.condition,
            resolution_path=resolution_path,
            line=raw.line,
            column=raw.column,
        )
    )
    outcome.resolved += 1
    if kind is EdgeKind.RE_EXPORT:
        outcome.re_exports_resolved += 1


def _failed_file_reference(
    item: _IdentifiedReference,
    resolver_response: ResolverResponse | None,
    outcome: _Outcome,
    failure: ParseFailure,
) -> None:
    reason = _SYNTAX_REASON if failure.reason == "syntax error" else failure.reason
    result = resolver_response.results.get(item.id) if resolver_response is not None else None
    if result is None:
        if _is_bare(item.raw.reference):
            outcome.external.append(_external_record(item))
        else:
            outcome.unresolved.append(_reference_record(item, reason))
        return
    if result.resolved_path is not None:
        if _is_bare(item.raw.reference) and _is_dependency_path(result.resolved_path):
            outcome.external.append(_external_record(item))
        else:
            outcome.unresolved.append(_reference_record(item, reason))
        return
    if _is_bare(item.raw.reference) and result.reason in {
        "module not found",
        "resolved path is outside the repository",
    }:
        outcome.external.append(_external_record(item))
    else:
        outcome.unresolved.append(_reference_record(item, reason))


def _promote_asset(path: str, records: dict[str, FileRecord]) -> FileRecord | None:
    record = records.get(path)
    if record is None:
        return None
    if record.is_node:
        return record
    if record.excluded_reason != _NOT_SOURCE:
        return None
    promoted = record.model_copy(
        update={
            "is_node": True,
            "excluded_reason": None,
            "language": None,
            "parse_failure": None,
            "typescript": None,
        }
    )
    records[path] = promoted
    return promoted


def _reference_record(item: _IdentifiedReference, reason: str) -> ReferenceRecord:
    return ReferenceRecord(
        source=item.source,
        reference=item.raw.reference,
        reason=reason,
        line=item.raw.line,
        column=item.raw.column,
    )


def _external_record(item: _IdentifiedReference) -> ExternalReference:
    return ExternalReference(
        source=item.source,
        reference=item.raw.reference,
        top_level=_package_name(item.raw.reference),
        line=item.raw.line,
        column=item.raw.column,
    )


def _is_bare(reference: str) -> bool:
    return not reference.startswith((".", "/"))


def _package_name(reference: str) -> str:
    parts = reference.split("/")
    if reference.startswith("@") and len(parts) >= 2:
        return f"{parts[0]}/{parts[1]}"
    return parts[0]


def _is_dependency_path(path: str) -> bool:
    return _DEPENDENCY_DIRECTORY in path.split("/")
