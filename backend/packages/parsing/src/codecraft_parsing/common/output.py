"""Assemble the shared representation from any language parser's results."""

from collections import Counter
from collections.abc import Iterable, Sequence

from codecraft_core.model import (
    Coverage,
    Edge,
    EdgeKind,
    ExcludedDirectory,
    ExternalReference,
    FileCoverage,
    FileRecord,
    ImportCondition,
    PythonCoverageDetails,
    PythonRepositoryDetails,
    ReferenceRecord,
    RepositoryParse,
    StarImportRecord,
    SymbolRecord,
)


def build_repository_parse(
    *,
    parser_version: str,
    python: PythonRepositoryDetails | None,
    python_coverage: PythonCoverageDetails | None,
    files: Sequence[FileRecord],
    excluded_directories: Sequence[ExcludedDirectory],
    edges: Sequence[Edge],
    symbol_references: Sequence[SymbolRecord],
    star_import_references: Sequence[StarImportRecord],
    unresolved: Sequence[ReferenceRecord],
    external: Sequence[ExternalReference],
    excluded: Sequence[ReferenceRecord],
    resolved: int,
) -> RepositoryParse:
    """Deduplicate, sort and count the output once for every language."""
    ordered_files = sorted(files, key=lambda record: record.path)
    ordered_edges = _final_edges(edges)
    ordered_symbols = sorted(symbol_references, key=_symbol_key)
    ordered_stars = sorted(star_import_references, key=_star_key)
    ordered_unresolved = sorted(unresolved, key=_reference_key)
    ordered_external = sorted(external, key=_external_key)
    ordered_excluded = sorted(excluded, key=_reference_key)

    coverage = Coverage(
        references=(
            resolved
            + len(ordered_symbols)
            + len(ordered_stars)
            + len(ordered_external)
            + len(ordered_excluded)
            + len(ordered_unresolved)
        ),
        resolved=resolved,
        symbols=len(ordered_symbols),
        star_imports=len(ordered_stars),
        external=len(ordered_external),
        excluded=len(ordered_excluded),
        failed=len(ordered_unresolved),
        python=python_coverage,
        failures_by_reason=_sorted_counts(record.reason for record in ordered_unresolved),
        failure_examples=ordered_unresolved[:5],
    )

    return RepositoryParse(
        parser_version=parser_version,
        python=python,
        files=ordered_files,
        excluded_directories=sorted(excluded_directories, key=lambda entry: entry.path),
        edges=ordered_edges,
        symbol_references=ordered_symbols,
        star_import_references=ordered_stars,
        unresolved_references=ordered_unresolved,
        external_references=ordered_external,
        excluded_references=ordered_excluded,
        coverage=coverage,
        file_coverage=_file_coverage(ordered_files),
    )


def _final_edges(candidates: Sequence[Edge]) -> list[Edge]:
    ordered = sorted(candidates, key=_edge_key)
    seen: set[tuple[str, str, EdgeKind, ImportCondition | None]] = set()
    edges: list[Edge] = []
    for edge in ordered:
        key = (edge.source, edge.target, edge.kind, edge.condition)
        if key in seen:
            continue
        seen.add(key)
        edges.append(edge)
    return edges


def _edge_key(edge: Edge) -> tuple[str, str, str, str, int, int]:
    condition = "" if edge.condition is None else edge.condition.value
    return (edge.source, edge.target, edge.kind.value, condition, edge.line, edge.column)


def _reference_key(record: ReferenceRecord) -> tuple[str, int, int, str]:
    return (record.source, record.line, record.column, record.reference)


def _external_key(record: ExternalReference) -> tuple[str, int, int, str, str]:
    return (record.source, record.line, record.column, record.reference, record.top_level)


def _symbol_key(record: SymbolRecord) -> tuple[str, int, int, str, str]:
    return (record.source, record.line, record.column, record.module, record.name)


def _star_key(record: StarImportRecord) -> tuple[str, int, int, str]:
    return (record.source, record.line, record.column, record.module)


def _file_coverage(files: Sequence[FileRecord]) -> FileCoverage:
    nodes = [record for record in files if record.is_node]
    return FileCoverage(
        found=len(files),
        parsed=sum(1 for record in nodes if record.parse_failure is None),
        failed_parse=sum(1 for record in nodes if record.parse_failure is not None),
        excluded=len(files) - len(nodes),
        excluded_by_reason=_sorted_counts(
            record.excluded_reason for record in files if record.excluded_reason is not None
        ),
    )


def _sorted_counts(values: Iterable[str]) -> dict[str, int]:
    return dict(sorted(Counter(values).items()))
