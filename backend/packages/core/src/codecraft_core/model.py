"""The representation every language parser emits.

Storage, graph arithmetic, the API and the explanation layer read only this module.
It must stay free of internal imports so that every other package may depend on it.

The top level is language-neutral. A language's own facts live in its own details
section, so adding Go or TypeScript does not add fields to every file record.
"""

from enum import StrEnum
from typing import Annotated, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

# Bounds the schema states as minimum 1, minimum 0 and a SHA-256 pattern. They
# live here as aliases so no record can carry a position or count that the
# contract document would call impossible.
type Position = Annotated[int, Field(ge=1)]
type Count = Annotated[int, Field(ge=0)]
type ContentHash = Annotated[str, Field(pattern=r"^sha256:[0-9a-f]{64}$")]


def _omit_when_none(value: object) -> bool:
    """Leave language-specific fields out of output that does not use them.

    Python and Go output is fixed. A new optional section must not appear as a
    null there, so its field is omitted rather than serialized.
    """

    return value is None


def _omit_when_zero(value: object) -> bool:
    """Leave a count out of output where its language does not use it."""

    return value == 0


class Language(StrEnum):
    PYTHON = "python"
    GO = "go"
    TYPESCRIPT = "typescript"
    JAVASCRIPT = "javascript"


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
    BLANK_IMPORT = "blank_import"
    DOT_IMPORT = "dot_import"
    RE_EXPORT = "re_export"
    TYPE_ONLY_IMPORT = "type_only_import"
    ASSET_IMPORT = "asset_import"


class TargetKind(StrEnum):
    """What an edge's target names.

    Python edges point at one file. Go edges point at a package folder, which
    is the set of files in that folder with the same package name.
    """

    FILE = "file"
    PACKAGE = "package"


class ResolutionPath(StrEnum):
    """How the TypeScript compiler reached a resolved file.

    One label is recorded per resolved edge, using the precedence stated in the
    output contract. Python and Go edges carry no resolution path.
    """

    PATH_ALIAS = "path_alias"
    WORKSPACE_PACKAGE = "workspace_package"
    PACKAGE_ENTRY_POINT = "package_entry_point"
    INDEX_FILE = "index_file"
    EXTENSION = "extension"
    RELATIVE = "relative"
    ASSET = "asset"


class TypeScriptFileKind(StrEnum):
    """Whether a TypeScript or JavaScript file is source or a declaration."""

    SOURCE = "source"
    DECLARATION = "declaration"


class GoConstraintSource(StrEnum):
    """Where a build constraint was written."""

    BUILD_LINE = "build_line"
    FILENAME = "filename"


class GoModuleSource(StrEnum):
    """Where an in-repository module's path was declared."""

    MODULE_FILE = "module_file"
    WORKSPACE = "workspace"
    REPLACE = "replace"


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


class CgoStatus(StrEnum):
    """The mark the cgo pseudo-package carries.

    ``import "C"`` is not a Go package, an edge or a failure. It is its own
    recorded outcome so it can be counted without pretending it resolved.
    """

    CGO_PSEUDO_PACKAGE = "cgo pseudo-package"


class ParseFailure(BaseModel):
    """Why a node's imports are absent.

    The position is one-based. It is present for a syntax error and absent when
    the source could not be decoded at all.
    """

    model_config = ConfigDict(frozen=True)

    reason: str
    line: Position | None
    column: Position | None


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


class TypeScriptFileDetails(BaseModel):
    """The TypeScript or JavaScript facts for one file record.

    The section is named once for both languages. ``kind`` separates a source
    file from a declaration file; the file record's ``language`` distinguishes
    TypeScript from JavaScript.
    """

    model_config = ConfigDict(frozen=True)

    kind: TypeScriptFileKind


class GoBuildConstraint(BaseModel):
    """One build constraint as written, and which form it was written in."""

    model_config = ConfigDict(frozen=True)

    source: GoConstraintSource
    expression: str


class GoFileDetails(BaseModel):
    """The Go facts for one file record.

    ``package`` is the package clause. ``module_path`` is the in-repository
    module that contains the file, or null when no module does.
    ``build_constraints`` records both build-constraint lines and filename
    suffixes as written. ``build_constraint_exclusion_reason`` is the same
    named reason as the file's ``excluded_reason`` when the constraints
    excluded it, and null otherwise.
    """

    model_config = ConfigDict(frozen=True)

    package: str
    module_path: str | None
    build_constraints: tuple[GoBuildConstraint, ...]
    is_test: bool
    build_constraint_exclusion_reason: str | None


class GoBuildContext(BaseModel):
    """The platform build constraints were evaluated against."""

    model_config = ConfigDict(frozen=True)

    os: str
    arch: str


class GoModule(BaseModel):
    """One module inside the repository and the folder that holds it."""

    model_config = ConfigDict(frozen=True)

    module_path: str
    folder: str
    source: GoModuleSource


class GoRepositoryDetails(BaseModel):
    """The Go facts about the repository as a whole."""

    model_config = ConfigDict(frozen=True)

    build_context: GoBuildContext
    modules: tuple[GoModule, ...]


class GoCoverageDetails(BaseModel):
    """The Go part of the coverage report.

    ``packages`` counts distinct (folder, package name) pairs among Go nodes,
    including test packages, because an external test package in the same
    folder is a separate package. A node with no package clause has no
    package name and is not counted.
    """

    model_config = ConfigDict(frozen=True)

    packages: Count


class TypeScriptCoverageDetails(BaseModel):
    """The TypeScript and JavaScript part of the coverage report.

    Re-exports are also ordinary references in the denominator. These two
    figures are a subset view: how many were found, and how many resolved.
    """

    model_config = ConfigDict(frozen=True)

    re_exports: Count
    re_exports_resolved: Count


class FileRecord(BaseModel):
    model_config = ConfigDict(frozen=True)

    path: str
    folder: str
    language: Language | None
    line_count: Count | None
    content_hash: ContentHash | None
    is_node: bool
    excluded_reason: str | None
    parse_failure: ParseFailure | None
    adapter_role: AdapterRole
    python: PythonFileDetails | None
    go: GoFileDetails | None = None
    typescript: TypeScriptFileDetails | None = Field(default=None, exclude_if=_omit_when_none)

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
        if self.go is not None and self.language != Language.GO:
            raise ValueError("go details belong only to a Go file")
        if self.typescript is not None and self.language not in (
            Language.TYPESCRIPT,
            Language.JAVASCRIPT,
        ):
            raise ValueError("typescript details belong only to a TypeScript or JavaScript file")
        if self.is_node:
            if self.language == Language.PYTHON:
                if self.python is None:
                    raise ValueError("a Python node carries its Python details")
                if self.go is not None or self.typescript is not None:
                    raise ValueError("a Python node carries no other language details")
            elif self.language == Language.GO:
                if self.go is None:
                    raise ValueError("a Go node carries its Go details")
                if self.python is not None or self.typescript is not None:
                    raise ValueError("a Go node carries no other language details")
            elif self.language in (Language.TYPESCRIPT, Language.JAVASCRIPT):
                if self.typescript is None:
                    raise ValueError("a TypeScript or JavaScript node carries its details")
                if self.python is not None or self.go is not None:
                    raise ValueError("a TypeScript or JavaScript node carries no other details")
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
    target_kind: TargetKind
    kind: EdgeKind
    condition: ImportCondition | None
    alias: str | None = None
    resolution_path: ResolutionPath | None = Field(default=None, exclude_if=_omit_when_none)
    line: Position
    column: Position


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
    line: Position
    column: Position


class StarImportRecord(BaseModel):
    """A star import whose imported names the parser does not enumerate.

    ``module`` is the resolved module the star names came from. No names are
    invented; the record is the evidence for one entry in coverage.
    """

    model_config = ConfigDict(frozen=True)

    source: str
    module: str
    status: StarImportStatus
    line: Position
    column: Position


class CgoReference(BaseModel):
    """One ``import "C"`` reference, recorded with its cgo status."""

    model_config = ConfigDict(frozen=True)

    source: str
    reference: str
    status: CgoStatus
    line: Position
    column: Position


class ReferenceRecord(BaseModel):
    """A reference that did not become an edge, with the named reason why."""

    model_config = ConfigDict(frozen=True)

    source: str
    reference: str
    reason: str
    line: Position
    column: Position


class ExternalReference(BaseModel):
    """A reference that points outside the repository, named by its top-level module.

    External is a recorded outcome, not a failure, so it carries no reason.
    """

    model_config = ConfigDict(frozen=True)

    source: str
    reference: str
    top_level: str
    line: Position
    column: Position


class PythonCoverageDetails(BaseModel):
    """The Python part of the coverage report."""

    model_config = ConfigDict(frozen=True)

    namespace_packages: Count


class Coverage(BaseModel):
    """Every reference seen, counted into exactly one outcome.

    A name imported from a resolved module that is not itself a module is a
    symbol, not an edge: it stays in the denominator as a symbol of a resolved
    module, not verified. The per-name evidence lives in ``symbol_references``.
    A star import is not a symbol; its evidence lives in
    ``star_import_references`` and is counted in ``star_imports``.
    Failures keep examples as well as a count.

    A language's coverage details default to null, so one parser supplies only
    its own section. Unknown sections are rejected rather than dropped.
    """

    model_config = ConfigDict(extra="forbid")

    references: Count
    resolved: Count
    symbols: Count
    star_imports: Count
    cgo: Count
    external: Count
    excluded: Count
    failed: Count
    python: PythonCoverageDetails | None = None
    go: GoCoverageDetails | None = None
    typescript: TypeScriptCoverageDetails | None = Field(default=None, exclude_if=_omit_when_none)
    failures_by_reason: dict[str, Count]
    failure_examples: list[ReferenceRecord]

    @model_validator(mode="after")
    def _outcomes_cover_every_reference(self) -> Self:
        outcomes = (
            self.resolved
            + self.symbols
            + self.star_imports
            + self.cgo
            + self.external
            + self.excluded
            + self.failed
        )
        if outcomes != self.references:
            raise ValueError(f"coverage outcomes {outcomes} do not add up to {self.references}")
        return self


class FileCoverage(BaseModel):
    """Every file counted into exactly one outcome.

    An asset file is a node, but it is not parsed as source. It is counted in
    ``assets`` and excluded from ``parsed``. The field is omitted when zero, so
    Python and Go output does not change.
    """

    found: Count
    parsed: Count
    failed_parse: Count
    excluded: Count
    assets: Count = Field(default=0, exclude_if=_omit_when_zero)
    excluded_by_reason: dict[str, Count]

    @model_validator(mode="after")
    def _files_add_up(self) -> Self:
        accounted = self.parsed + self.failed_parse + self.excluded + self.assets
        if accounted != self.found:
            raise ValueError(f"file outcomes {accounted} do not add up to {self.found}")
        return self


class PythonRepositoryDetails(BaseModel):
    """The Python facts about the repository as a whole."""

    model_config = ConfigDict(frozen=True)

    import_root: str
    import_root_rule: str


class TypeScriptRepositoryDetails(BaseModel):
    """The TypeScript and JavaScript facts about the repository as a whole.

    The section is named once for the pair. ``config_files`` lists every nearest
    configuration file the resolver used, repository-relative and sorted.
    """

    model_config = ConfigDict(frozen=True)

    config_files: tuple[str, ...]


class RepositoryParse(BaseModel):
    """The full output for one repository, as every later phase reads it.

    A language's repository details default to null, so one parser supplies
    only its own section. Unknown sections are rejected rather than dropped.
    """

    model_config = ConfigDict(extra="forbid")

    parser_version: str
    python: PythonRepositoryDetails | None = None
    go: GoRepositoryDetails | None = None
    typescript: TypeScriptRepositoryDetails | None = Field(default=None, exclude_if=_omit_when_none)
    files: list[FileRecord]
    excluded_directories: list[ExcludedDirectory]
    edges: list[Edge]
    symbol_references: list[SymbolRecord]
    star_import_references: list[StarImportRecord]
    cgo_references: list[CgoReference]
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

    @model_validator(mode="after")
    def _cgo_references_have_evidence(self) -> Self:
        if len(self.cgo_references) != self.coverage.cgo:
            raise ValueError(
                f"{len(self.cgo_references)} cgo records do not add up to {self.coverage.cgo}"
            )
        return self
