# Parser output contract

This file is the contract of record for the parser's output. `parser-output.schema.json`
beside it is the machine-readable form. Every language parser emits this shape; storage,
graph arithmetic, the API and the explanation layer read only this shape.

Fan-in, fan-out, blast radius and chains are **not** part of this output. Graph arithmetic
lives in the frontend TypeScript (AGENTS.md rule 4). The parser supplies files and edges.

The top level is language-neutral. A language's own facts live in that language's details
section; Python uses `python` at the repository, file and coverage levels, and Go uses `go`
at the same three levels.

## Top level

| Field | Type | Meaning |
|---|---|---|
| `parser_version` | string | Parser, binding and grammar versions that produced the output. |
| `python` | Python repository details or null | Import root and the rule that chose it. |
| `go` | Go repository details or null | Build context and every in-repository module. |
| `files` | array of file record | Every regular file and symbolic-link record outside a pruned directory, sorted by `path`. |
| `excluded_directories` | array of `{path, reason}` | Pruned directories, sorted by `path`, with a trailing `/`. An unlistable repository root is `.`. |
| `edges` | array of edge | Unique connections, sorted. |
| `symbol_references` | array of symbol record | Imported names that are not modules, recorded per name, sorted. |
| `star_import_references` | array of star import record | Star imports whose names the parser does not enumerate, sorted. |
| `cgo_references` | array of cgo record | Go `import "C"` references, each with the cgo status, sorted. |
| `unresolved_references` | array of reference record | References that failed, each with a named reason, sorted. |
| `external_references` | array of external record | References outside the repository, named by `top_level`, sorted. |
| `excluded_references` | array of reference record | References that landed in an excluded directory, sorted. |
| `coverage` | coverage | Every reference counted into one outcome. |
| `file_coverage` | file coverage | Every file counted into one outcome. |

## Bounds

- The walk reads at most **50,000 files**. A repository with more fails the run with
  `repository exceeds the 50000 file limit`.
- A file larger than **2,000,000 bytes** is excluded with reason `file exceeds size
  limit`. It is read no further than size-limit + 1 bytes, is never parsed in part, and its
  hash and line count stay null.
- The numbers are named constants in `codecraft_parsing.common.walker`.

Every `line` and `column` is a one-based integer of at least 1. Every count (`line_count`,
`namespace_packages`, each coverage count and each value in `failures_by_reason` and
`excluded_by_reason`) is an integer of at least 0. A `content_hash` is exactly `sha256:`
followed by 64 lowercase hex characters. These bounds are the `Position`, `Count` and
`ContentHash` aliases in `codecraft_core.model`; the model and `parser-output.schema.json`
state the same bounds.

## File record

`path` is POSIX and relative to the repository root. `folder` is its POSIX parent, `.` at
the root. `language` is `python`, `go` or null. `line_count` is `len(text.splitlines())` for a
`.py` file that decodes. A `.pyi` stub, every other file, and a `.py` that does not decode
count the raw bytes split into lines.

`content_hash` is `sha256:<hex>`: lowercase hex of the raw bytes. It is null for an
environment file, a symbolic link, a file over the size limit and a file that cannot be
read, none of which keeps a hash; those files also have a null `line_count`.

`is_node` is true when the file is part of the graph. `excluded_reason` is null for a node
and a named reason for an excluded file. `parse_failure` is null or
`{reason, line, column}`; a node with a parse failure keeps its place but contributes no
edges. A file-level failure that prevents edges — a syntax or decode failure, conflicting
package names in one folder, or a module file with an unreadable or malformed directive —
is recorded here. A module file is not a node but still carries its failure. A file whose
decoded text cannot be encoded as UTF-8 is a parse failure with reason
`cannot encode source as UTF-8`. A parse failure with no position, which is a decode or
encode failure, has null `line` and `column`. `adapter_role` is `fallback` for every file,
node or excluded.

A directory that cannot be listed is recorded in `excluded_directories` with reason
`directory cannot be listed`; its contents are never read. A file that cannot be read is
an excluded file with reason `file cannot be read`, with a null hash and null line count.

`python` is the Python details object, or null:

| Field | Type | Meaning |
|---|---|---|
| `module` | string or null | Dotted module name under the import root. |
| `package_kind` | `regular`, `namespace` or null | Null for a module directly in the import root. |
| `is_package` | boolean | True for an `__init__.py`. |

A `.pyi` stub file is excluded with reason `stub file`; a package that contains only stubs
contributes no node, so the gap stays visible rather than being guessed at. A symbolic
link is excluded with reason `symbolic link` and is never read; a symbolic-link directory
is recorded in `excluded_directories` with the same reason. A committed virtual environment
is excluded with reason `virtual environment`; its contents are third-party code and create
neither nodes nor edges.

`go` is the Go details object, or null:

| Field | Type | Meaning |
|---|---|---|
| `package` | string | The package name in the file's package clause. |
| `module_path` | string or null | The in-repository module that contains the file, or null when none does. |
| `build_constraints` | array of `{source, expression}` | Every build constraint written for the file. `source` is `build_line` or `filename`; `expression` is the constraint as written. |
| `is_test` | boolean | True for a file whose name ends in `_test.go`. |
| `build_constraint_exclusion_reason` | string or null | The named reason when the build constraints exclude the file for the target context, otherwise null. It equals the file's `excluded_reason`. |

A Go node carries non-null `go` details; a Python node carries non-null `python` details.
A Python node has a null `go` section and a Go node has a null `python` section; the schema
and the model both enforce this. A Go file excluded by build constraints is not a node but
still carries its `go` details, so the constraints and their reason stay visible.

## Edge

An edge exists only when a reference resolves to a real file or package folder in the
input.

| Field | Type | Meaning |
|---|---|---|
| `source` | string | File path the edge starts from. |
| `target` | string | File path or package folder it points to. |
| `target_kind` | `file` or `package` | Whether `target` names one file or a package folder. |
| `kind` | `import`, `dynamic_import`, `blank_import` or `dot_import` | How the reference was written. |
| `condition` | `type_only`, `optional`, `lazy` or null | Guard the import sits under. |
| `alias` | string or null | The alias written on the import, or null when none is written. |
| `line`, `column` | integer | One-based start of the import statement or dynamic call. |

`condition` is only `type_only`, `optional`, `lazy` or null, and it applies to Python
imports. A guarded import is never a separate kind: an import under `if TYPE_CHECKING`,
inside a `try` block, or inside a function body keeps `kind: import` (or
`dynamic_import`) and records how it is guarded only in `condition`. Consumers read the
kind to know it is an import, and the condition to know when it runs.

Python edges use `kind: import` or `dynamic_import`, `target_kind: file`, and a null
`alias` unless the imported name is aliased. Go edges use `kind: import`, `blank_import` or
`dot_import`, always `target_kind: package`, and `alias` carries a named alias when one is
written. A blank or dot import's form is in `kind`, so its `alias` is null. An alias is
never a kind.

Edges are unique by `(source, target, target_kind, kind, condition, alias)`; when the
same connection is written more than once, the earliest location is kept. Sorted by
`(source, target, target_kind, kind, condition, alias, line, column)`, with null condition
and null alias first.

An explicit import always draws its edge, including an import that names the file's own
package or module. A relative import's base that names the file's own package or an
ancestor is the one exception: it is resolved but draws no edge, because loading the
module already loaded that package chain. The base still counts in coverage.

## Symbol records

A symbol is an imported name that is not a module. The name stays in coverage, not as an
edge, and never as a failure.

| Field | Type | Meaning |
|---|---|---|
| `source` | string | Importing file. |
| `module` | string | Resolved module the name came from. |
| `name` | string | Imported name as written. |
| `status` | string | Exactly `symbol of resolved module, not verified`. |
| `line`, `column` | integer | One-based start of the import statement. |

## Star import records

A star import (`from X import *`) draws its edge to `X` as any import does. The names
it brings in are not written in the source, so the parser does not enumerate them and
creates no symbol records for them. It is one reference: when the base resolves inside
the repository, one star import record is written and the reference is counted in
`star_imports`. It is not also counted in `resolved`, even when the base is a file and
its edge is drawn. A namespace package base is recorded the same way; it draws no edge
because no file exists.

| Field | Type | Meaning |
|---|---|---|
| `source` | string | Importing file. |
| `module` | string | Resolved module the star names came from. |
| `status` | string | Exactly `names not enumerated`. |
| `line`, `column` | integer | One-based start of the import statement. |

A star import of an external module writes only the external record. A star import
whose base fails or lands in an excluded file or directory writes only that outcome.
No names are invented in any case.

## cgo records

The Go import path `C` is the cgo pseudo-package. It is not a package, an edge, an
external reference or a failure. It is one reference with the exact status
`cgo pseudo-package`, counted in `cgo`.

| Field | Type | Meaning |
|---|---|---|
| `source` | string | Importing file. |
| `reference` | string | Exactly `C`. |
| `status` | string | Exactly `cgo pseudo-package`. |
| `line`, `column` | integer | One-based start of the import statement. |

## Reference records

`reference` is the module expression as written, or the call text for a dynamic import
that is not a literal. For a non-literal dynamic import the call text is at most 120
characters; when longer it is truncated to 120 characters followed by `...`, with `line`
and `column` unchanged. `line` and `column` are one-based at the statement or call start.
`column` counts characters, not UTF-8 bytes. `reason` is a named, stable string. External
records add `top_level`, the first dot segment; external is a recorded outcome, not a
failure, so it carries no reason. An excluded reference is one that lands in a pruned
directory or on a file that was excluded; its reason is the directory or file reason. For
a pruned directory that is the walk's own exclusion reason, for example
`dependency installation` for `node_modules`, never a generic substitute. An excluded
imported name is recorded by its resolved dotted path.

For `importlib.import_module`, a literal name that starts with a dot is resolved only when
its package argument is a literal string; without one it is unresolved with reason
`relative dynamic import requires a package argument`. With a literal package argument the
name is measured from that package. When the package's top-level name is outside the
repository the reference is external with that top-level, not a failure; when it lands in
a pruned directory the reference is excluded with that directory's reason. A non-literal
package argument is unresolved with reason `non-literal dynamic import package`.

`__import__` has no package argument, so a dot-leading name is unresolved with reason
`relative __import__ is not resolved`. A positive literal `level` resolves the import
relative to the file's package; a negative literal `level` is unresolved with reason
`negative __import__ level`.

## Go resolution

A Go package is the set of files in one folder with the same package name. An external
test package in the same folder is a separate package. A Go edge always names the package
folder, never one file, because the source does not say which file in the package is used.
`target` is the folder's POSIX path relative to the repository root, `.` at the root, and
`target_kind` is `package`.

`go` at the top level carries `build_context` (`{os, arch}`, the context build constraints
were evaluated against) and `modules`, every module found inside the repository. Each
module records its `module_path`, its `folder`, and the `source` that declared it:
`module_file`, `workspace` or `replace`. `module_file` is used for every folder that holds
a module file, including a nested module that no workspace file names and a folder that a
local replacement also reaches. `replace` is used only for a local replacement target that
has no module file of its own. `workspace` is used for a module named by `go.work` unless a
local replacement also reaches that folder and it has its own module file. A module file
inside a folder the Go tool ignores, or inside `vendor` or `testdata`, is not a repository
module. Every in-repository module is checked, not only the main one. A file belongs to the
nearest module above it, so a nested module's files are never attributed to its parent. A
module file with a failure contributes no module entry, even when its path line was
readable; its path is not used to resolve a package. It names only the imports that
depend on the failed module.

A replacement to a local folder inside the repository makes that folder a module. A
replacement to a version is third-party and its imports are external. A replacement to a
local folder outside the repository fails each import that uses it with reason
`replacement target is outside the repository`; a replacement to a local path that does
not exist fails each import that uses it with reason `replacement target does not exist`.
A replacement to a local folder whose module file declares another module path fails each
import that uses the replaced path with reason
`replacement target declares a different module path`.
Replace directives in `go.mod` and `go.work` are read. The target is never guessed or
created.

A module file with an unreadable or malformed directive carries the failure on its own
file record. An import depends on that module when its path equals the module path or
continues from it after a `/`; each such import is unresolved with the same reason.
Imports outside every module stay external, including imports from files in the module's
folder. A module file with no readable path fails every import from its files, because
internal and external paths cannot be told apart without it. The failure reason is
`malformed module file` for invalid syntax, or the file record's own exclusion reason
when the file could not be read.
The module path is not guessed. `go.mod` and `go.work` are file records with null language,
not nodes, excluded with reason `not a Go file`. Folders beginning `_` or `.` are excluded
with reason `ignored by the Go tool`; `vendor` and `testdata` are excluded as stated below.

A Go file the grammar cannot read keeps its named or generic syntax reason on its file
record and draws no edges. Each readable import path in that file is counted once. When
the path points inside a repository module, it is unresolved with reason
`file has a syntax error`, at the import's own position. When it points outside every
module, it stays external. A path the grammar could not read keeps its own reason and is
never guessed. An import spec that holds more than one path keeps the first path as an
ordinary import and records each later path as a failed reference with reason
`malformed import spec`, at that path's own position. A replacement, module,
trailing-slash or empty-path failure keeps its own reason; `file has a syntax error`
applies when the readable path points inside a repository module, before the target
folder is resolved.

An import path is inside a module only when it equals the module path or continues after a
`/`. With the module `example.com/app`, `example.com/app/pkg` is inside and
`example.com/app-tools/pkg` is external. When the repository has at least one module, an
import outside every in-repository module is external, with the first path segment in
`top_level`; it is not a failure. When the repository has no module file, every import is
unresolved with reason `no module file declares a path`, not external. An import inside a
module whose folder does not exist is unresolved with reason `package folder not found in
repository`. When the folder exists but every file in it is excluded by build constraints,
the reference is excluded with that build-constraint reason, not reported as missing. A
folder that exists but has only test files has no importable package and is unresolved with
reason `package folder has no importable package`. A Go file with no package clause keeps
its node with `package: ""`; it is not importable, and it is not counted in `packages`.
An import whose target folder has only non-test
`package main` files is unresolved with reason `imports a main package`. An import
path ending in `/` is unresolved with reason `import path ends with a slash`. An empty
import path is unresolved with reason `import path is empty`. An import spec without a
readable literal path is unresolved with reason `import path is not a literal string` or
`import spec has no path`, even when the file itself fails to parse.

A single Go import declaration reports the declaration's start. Each spec in a grouped
import reports its own start.

Build constraints come from `//go:build` and `// +build` lines and from filename suffixes.
They are recorded per file as written. A filename suffix is a constraint only when a
non-empty prefix precedes the first underscore: `js.go` and `js_test.go` are plain files,
while `windows_amd64.go` carries only the amd64 suffix. A filename suffix carrying both
GOOS and GOARCH is recorded as two filename constraints, one for each term. The target sets
`linux`, `amd64`, `unix` and `gc` true; `cgo` and `go1.N` release tags are false. A file
that the target context excludes is an excluded file with reason `build constraint excludes
file for <os>/<arch>`; its `go` details repeat that reason and it is never treated as
missing. Test files (`_test.go`) are nodes
with `is_test: true`, and they produce outgoing edges only. Production code never gets an
edge into a test file: a package target resolves only when the folder has at least one
non-test Go file of that package. A blank import (`_ "path"`) is `blank_import`, a dot
import is `dot_import`, and a named alias is recorded in `alias`. An import path exactly
`C` is the cgo pseudo-package: it writes one cgo record and no edge, external reference or
failure.

A folder whose non-test files name more than one package, other than a `_test` package,
is conflicting. Each conflicting non-test file keeps its node. A conflicting file that
already has a syntax error keeps the syntax reason; every other conflicting non-test file
carries a `parse_failure` with reason `conflicting package names in one folder`, `line` and
`column` null. All conflicting files contribute no edges. A readable import in a
conflicting file that points inside the repository is unresolved with the conflict reason
and counted once; one that points outside stays external; `C` keeps its cgo outcome. An
import whose target folder is conflicting is unresolved with the same reason.

`vendor` and `testdata` folders are pruned whole, with reasons `vendored dependency` and
`test data`. They create no file records, no nodes and no edges.

Go coverage counts every import path the parser sees as one reference, including a
readable path in a file that fails to parse. A resolved package is `resolved`; an import
outside every module in a repository that has modules is `external`; an import that lands
in a pruned directory or an excluded file is `excluded`; a named failure is `failed`; the
cgo pseudo-package is `cgo`. Go has no symbol imports or
star imports, so `symbols` and `star_imports` stay 0. The cgo category is its own outcome
and is included in the denominator.

## Coverage

`references` is the denominator: `resolved + symbols + star_imports + cgo + external + excluded + failed`.

`symbols` is the number of symbol records; each record is the evidence for one entry.
For `from X import name`, when `X` resolves inside the repository and `name` names no
module there, `name` is a symbol of `X`. It is not an edge and not a failure.

`star_imports` is the number of star import records; each record is the evidence for one
entry. A star import is one reference: it is counted here and not again in `resolved`,
even when its base is a file and draws an edge. It is not a symbol and not a failure.

`cgo` is the number of cgo records; each record is the evidence for one entry. It is one
reference, counted here and not again in `resolved`, `external` or `failed`.

`python` is the Python coverage object, or null:

| Field | Type | Meaning |
|---|---|---|
| `namespace_packages` | integer | Non-root folders under the import root with no `__init__` file and at least one Python module beneath them. |

`go` is the Go coverage object, or null:

| Field | Type | Meaning |
|---|---|---|
| `packages` | integer | Distinct (folder, package name) pairs among Go nodes, including test packages. A node with no package name is not counted. |

`failures_by_reason` is a sorted object of reason to count. `failure_examples` holds the
first five unresolved records in sorted order; the full list is in
`unresolved_references`.

`file_coverage`: `found = parsed + failed_parse + excluded`. `excluded_by_reason` is a
sorted object of reason to count.

## Ordering

Every list is sorted. Files by `path`; excluded directories by `path`; edges as above;
symbol references by `(source, line, column, module, name)`; star import references by
`(source, line, column, module)`; cgo references by `(source, line, column, reference)`;
unresolved and excluded references by
`(source, line, column, reference)`; external references by
`(source, line, column, reference, top_level)`.

JSON object key order follows the model and is not part of the contract.
