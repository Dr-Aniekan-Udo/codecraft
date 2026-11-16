"""The representation every language parser emits.

Storage, graph arithmetic, the API and the explanation layer read only this module.
It must stay free of internal imports so that every other package may depend on it.

The top level is language-neutral. A language's own facts live in its own details
section, so adding Go or TypeScript does not add fields to every file record.
"""

from enum import StrEnum
from typing import Self

from pydantic import BaseModel, ConfigDict, model_validator


class Language(StrEnum):
    PYTHON = "python"


class PackageKind(StrEnum):
    """How a module's package is found on disk.

    A regular package has an ``__init__`` file. A namespace package is a folder
    without one, which Python still imports when it sits inside the import root.
    """

    REGULAR = "regular"
    NAMESPACE = "namespace"


class EdgeKind(StrEnum):
    IMPORT = "import"
    DYNAMIC_IMPORT = "dynamic_import"


class ImportCondition(StrEnum):
    """The guard an import sits under.

    The names follow the language rules in the design: an import under a
    type-checking guard is type-only, inside a function it is lazy, and inside an
    optional-dependency guard it is optional.
    """

    TYPE_ONLY = "type_only"
    LAZY = "lazy"
    OPTIONAL = "optional"


class AdapterRole(StrEnum):
    FALLBACK = "fallback"


class SymbolStatus(StrEnum):
    UNVERIFIED = "symbol of resolved module, not verified"


class StarImportStatus(StrEnum):
    """The mark a star import carries.

    A star import brings in names the source does not write, so there is no
    per-name evidence to record. This is deliberately not a ``SymbolStatus``:
    a star import is not a symbol, it is an import whose names are not listed.
    """

    NAMES_NOT_ENUMERATED = "names not enumerated"


class ParseFailure(BaseModel):
    """Why a node's imports are absent.

    The position is one-based. It is present for a syntax error and absent when
    the source could not be decoded at all.
    """

    model_config = ConfigDict(frozen=True)

    reason: str
    line: int | None
    column: int | None


class PythonFileDetails(BaseModel):
    """The Python facts for one file record.

    ``module`` is the dotted name under the import root. ``package_kind`` is
    null for a module directly in the import root. ``is_package`` is true for an
    ``__init__.py``.
    """

    model_config = ConfigDict(frozen=True)

    module: str | None
    package_kind: PackageKind | None
    is_package: bool


class FileRecord(BaseModel):
    model_config = ConfigDict(frozen=True)

    path: str
    folder: str
    language: Language | None
    line_count: int | None
    content_hash: str | None
    is_node: bool
    excluded_reason: str | None
    parse_failure: ParseFailure | None
    adapter_role: AdapterRole
    python: PythonFileDetails | None

    @model_validator(mode="after")
    def _node_and_exclusion_agree(self) -> Self:
        # A node carries no exclusion reason; an excluded file must carry one.
        if self.is_node == (self.excluded_reason is not None):
            raise ValueError("a file is either a node or excluded, and says which")
        return self

    @model_validator(mode="after")
    def _details_match_language(self) -> Self:
        if self.python is not None and self.language != Language.PYTHON:
            raise ValueError("python details belong only to a Python file")
        if self.is_node and self.language == Language.PYTHON and self.python is None:
            raise ValueError("a Python node carries its Python details")
        return self


class ExcludedDirectory(BaseModel):
    """A folder left out whole, so its contents are never read."""

    model_config = ConfigDict(frozen=True)

    path: str
    reason: str


class Edge(BaseModel):
    model_config = ConfigDict(frozen=True)

    source: str
    target: str
    kind: EdgeKind
    condition: ImportCondition | None
    line: int
    column: int


class SymbolRecord(BaseModel):
    """An imported name that is not a module, recorded per name.

    ``source`` is the importing file, ``module`` is the resolved module the name
    came from. The status is the contract's exact phrase.
    """

    model_config = ConfigDict(frozen=True)

    source: str
    module: str
    name: str
    status: SymbolStatus
    line: int
    column: int


class StarImportRecord(BaseModel):
    """A star import whose imported names the parser does not enumerate.

    ``module`` is the resolved module the star names came from. No names are
    invented; the record is the evidence for one entry in coverage.
    """

    model_config = ConfigDict(frozen=True)

    source: str
    module: str
    status: StarImportStatus
    line: int
    column: int


class ReferenceRecord(BaseModel):
    """A reference that did not become an edge, with the named reason why."""

    model_config = ConfigDict(frozen=True)

    source: str
    reference: str
    reason: str
    line: int
    column: int


class ExternalReference(BaseModel):
    """A reference that points outside the repository, named by its top-level module.

    External is a recorded outcome, not a failure, so it carries no reason.
    """

    model_config = ConfigDict(frozen=True)

    source: str
    reference: str
    top_level: str
    line: int
    column: int


class PythonCoverageDetails(BaseModel):
    """The Python part of the coverage report."""

    model_config = ConfigDict(frozen=True)

    namespace_packages: int


class Coverage(BaseModel):
    """Every reference seen, counted into exactly one outcome.

    A name imported from a resolved module that is not itself a module is a
    symbol, not an edge: it stays in the denominator as a symbol of a resolved
    module, not verified. The per-name evidence lives in ``symbol_references``.
    A star import is not a symbol; its evidence lives in
    ``star_import_references`` and is counted in ``star_imports``.
    Failures keep examples as well as a count.
    """

    references: int
    resolved: int
    symbols: int
    star_imports: int
    external: int
    excluded: int
    failed: int
    python: PythonCoverageDetails | None
    failures_by_reason: dict[str, int]
    failure_examples: list[ReferenceRecord]

    @model_validator(mode="after")
    def _outcomes_cover_every_reference(self) -> Self:
        outcomes = (
            self.resolved
            + self.symbols
            + self.star_imports
            + self.external
            + self.excluded
            + self.failed
        )
        if outcomes != self.references:
            raise ValueError(f"coverage outcomes {outcomes} do not add up to {self.references}")
        return self


class FileCoverage(BaseModel):
    found: int
    parsed: int
    failed_parse: int
    excluded: int
    excluded_by_reason: dict[str, int]

    @model_validator(mode="after")
    def _files_add_up(self) -> Self:
        accounted = self.parsed + self.failed_parse + self.excluded
        if accounted != self.found:
            raise ValueError(f"file outcomes {accounted} do not add up to {self.found}")
        return self


class PythonRepositoryDetails(BaseModel):
    """The Python facts about the repository as a whole."""

    model_config = ConfigDict(frozen=True)

    import_root: str
    import_root_rule: str


class RepositoryParse(BaseModel):
    """The full output for one repository, as every later phase reads it."""

    parser_version: str
    python: PythonRepositoryDetails | None
    files: list[FileRecord]
    excluded_directories: list[ExcludedDirectory]
    edges: list[Edge]
    symbol_references: list[SymbolRecord]
    star_import_references: list[StarImportRecord]
    unresolved_references: list[ReferenceRecord]
    external_references: list[ExternalReference]
    excluded_references: list[ReferenceRecord]
    coverage: Coverage
    file_coverage: FileCoverage

    @model_validator(mode="after")
    def _symbols_have_evidence(self) -> Self:
        if len(self.symbol_references) != self.coverage.symbols:
            raise ValueError(
                f"{len(self.symbol_references)} symbol records do not add up to "
                f"{self.coverage.symbols}"
            )
        return self

    @model_validator(mode="after")
    def _star_imports_have_evidence(self) -> Self:
        if len(self.star_import_references) != self.coverage.star_imports:
            raise ValueError(
                f"{len(self.star_import_references)} star import records do not add up to "
                f"{self.coverage.star_imports}"
            )
        return self
