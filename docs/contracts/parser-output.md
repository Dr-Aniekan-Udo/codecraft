# Parser output contract

This file is the contract of record for the parser's output. `parser-output.schema.json`
beside it is the machine-readable form. Every language parser emits this shape; storage,
graph arithmetic, the API and the explanation layer read only this shape.

Fan-in, fan-out, blast radius and chains are **not** part of this output. Graph arithmetic
lives in the frontend TypeScript (AGENTS.md rule 4). The parser supplies files and edges.

The top level is language-neutral. A language's own facts live in that language's details
section; Python uses `python` at the repository, file and coverage levels.

## Top level

| Field | Type | Meaning |
|---|---|---|
| `parser_version` | string | Parser, binding and grammar versions that produced the output. |
| `python` | Python repository details or null | Import root and the rule that chose it. |
| `files` | array of file record | Every regular file and symbolic-link record outside a pruned directory, sorted by `path`. |
| `excluded_directories` | array of `{path, reason}` | Pruned directories, sorted by `path`, with a trailing `/`. An unlistable repository root is `.`. |
| `edges` | array of edge | Unique connections, sorted. |
| `symbol_references` | array of symbol record | Imported names that are not modules, recorded per name, sorted. |
| `star_import_references` | array of star import record | Star imports whose names the parser does not enumerate, sorted. |
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
the root. `language` is `python` or null. `line_count` is `len(text.splitlines())` for a
`.py` file that decodes. A `.pyi` stub, every other file, and a `.py` that does not decode
count the raw bytes split into lines.

`content_hash` is `sha256:<hex>`: lowercase hex of the raw bytes. It is null for an
environment file, a symbolic link, a file over the size limit and a file that cannot be
read, none of which keeps a hash; those files also have a null `line_count`.

`is_node` is true when the file is part of the graph. `excluded_reason` is null for a node
and a named reason for an excluded file. `parse_failure` is null or
`{reason, line, column}`; a node with a parse failure keeps its place but contributes no
edges. A file whose decoded text cannot be encoded as UTF-8 is a parse failure with reason
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

## Edge

An edge exists only when a reference resolves to a real file in the input.

| Field | Type | Meaning |
|---|---|---|
| `source` | string | File path the edge starts from. |
| `target` | string | File path it points to. |
| `kind` | `import` or `dynamic_import` | How the reference was written. |
| `condition` | `type_only`, `optional`, `lazy` or null | Guard the import sits under. |
| `line`, `column` | integer | One-based start of the import statement or dynamic call. |

`kind` is only `import` or `dynamic_import`, and `condition` is only `type_only`,
`optional`, `lazy` or null. A guarded import is never a separate kind: an import under
`if TYPE_CHECKING`, inside a `try` block, or inside a function body keeps `kind: import`
(or `dynamic_import`) and records how it is guarded only in `condition`. Consumers read
the kind to know it is an import, and the condition to know when it runs.

Edges are unique by `(source, target, kind, condition)`; when the same connection is
written more than once, the earliest location is kept. Sorted by
`(source, target, kind, condition, line, column)`, with null condition first.

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

## Coverage

`references` is the denominator: `resolved + symbols + star_imports + external + excluded + failed`.

`symbols` is the number of symbol records; each record is the evidence for one entry.
For `from X import name`, when `X` resolves inside the repository and `name` names no
module there, `name` is a symbol of `X`. It is not an edge and not a failure.

`star_imports` is the number of star import records; each record is the evidence for one
entry. A star import is one reference: it is counted here and not again in `resolved`,
even when its base is a file and draws an edge. It is not a symbol and not a failure.

`python` is the Python coverage object, or null:

| Field | Type | Meaning |
|---|---|---|
| `namespace_packages` | integer | Non-root folders under the import root with no `__init__` file and at least one Python module beneath them. |

`failures_by_reason` is a sorted object of reason to count. `failure_examples` holds the
first five unresolved records in sorted order; the full list is in
`unresolved_references`.

`file_coverage`: `found = parsed + failed_parse + excluded`. `excluded_by_reason` is a
sorted object of reason to count.

## Ordering

Every list is sorted. Files by `path`; excluded directories by `path`; edges as above;
symbol references by `(source, line, column, module, name)`; star import references by
`(source, line, column, module)`; unresolved and excluded references by
`(source, line, column, reference)`; external references by
`(source, line, column, reference, top_level)`.

JSON object key order follows the model and is not part of the contract.
