# CodeCraft JS resolver protocol

**Protocol version:** 1.

This document is the contract between the Python TypeScript/JavaScript parser and
the Node helper in this folder. The helper answers one question only: for a
literal reference written in a source file, which file does the TypeScript
compiler resolve it to? It does not decide edge kinds, node selection or graph
structure.

## Transport

- The Python parser starts one helper process per repository.
- The parser writes one UTF-8 JSON request to stdin, then closes stdin.
- The helper writes one UTF-8 JSON response to stdout and exits.
- Nothing else is written to stdout. Diagnostics go to stderr.
- Exit code `0`: a response was written. Exit code `1`: the request was refused.
  Exit code `2`: an internal helper failure.
- The helper uses only the `typescript` package and the filesystem. It never uses
  the network, never installs anything, and never imports, evaluates or runs code
  from the analysed repository.
- All references for one repository travel in one request. The helper does not
  keep state between requests.

## Request

```json
{
  "protocol_version": 1,
  "repository_root": "/absolute/path/to/repository",
  "max_file_bytes": 2000000,
  "references": [
    {
      "id": "r000001",
      "source": "src/app.ts",
      "specifier": "./lib",
      "kind": "module"
    }
  ]
}
```

| Field | Type | Meaning |
|---|---|---|
| `protocol_version` | integer | Exactly `1`. Any other value is refused. |
| `repository_root` | string | Absolute path to the repository directory. |
| `max_file_bytes` | integer | Positive byte limit applied to every configuration file the helper reads. |
| `references` | array | Every reference in the batch. May be empty. |
| `references[].id` | string | Unique within the request. Non-empty. |
| `references[].source` | string | Repository-relative POSIX path of the importing file. |
| `references[].specifier` | string | The module text exactly as written in the source, without quotes. Non-empty. |
| `references[].kind` | string | `module` for compiler resolution, `asset` for exact-path asset resolution. |

`source` may not be absolute, may not contain `.` or `..` segments, and must name
a file inside `repository_root`. The helper rejects a request that breaks these
rules. `kind` describes only how to resolve; it is not an edge kind and does not
carry type-only, re-export or dynamic-import meaning. The parser keeps those
semantics.

Each reference has exactly one `id`. The helper returns exactly one result for
each `id`, in the same order as the request, with no extra results.

## Response

```json
{
  "protocol_version": 1,
  "typescript_version": "6.0.3",
  "config_files": ["tsconfig.json"],
  "results": [
    {
      "id": "r000001",
      "resolved_path": "src/lib.ts",
      "resolution_path": "extension",
      "reason": null
    }
  ]
}
```

| Field | Type | Meaning |
|---|---|---|
| `protocol_version` | integer | Exactly `1`. |
| `typescript_version` | string | The version of the installed `typescript` package that produced the results. |
| `config_files` | array of strings | Every nearest configuration file selected for a source file, repository-relative and sorted. Extended files are not listed separately. |
| `results` | array | One result per request reference, in request order. |
| `results[].id` | string | The request's `id`, unchanged. |
| `results[].resolved_path` | string or null | Repository-relative POSIX path of the resolved file, or null. |
| `results[].resolution_path` | string or null | How it resolved, from the list below, or null. |
| `results[].reason` | string or null | A named reason, or null when resolved. |

For every result, exactly one of `resolved_path` and `reason` is non-null. When
`resolved_path` is non-null, `resolution_path` is non-null. When `reason` is
non-null, `resolved_path` and `resolution_path` are null.

`resolved_path` is relative to `repository_root`, uses `/` separators, has no
leading `./`, and contains no `.` or `..` segment. A compiler answer outside
`repository_root` is not returned as a path: it is null with the named reason
`resolved path is outside the repository`.

A resolved path may point inside a dependency folder such as `node_modules`. The
helper returns the compiler's answer; the parser decides whether that file is a
node or an excluded dependency.

## Resolution path values

The helper records the one path the compiler took. When more than one label could
apply, the first match in this order wins:

1. `path_alias`: a `compilerOptions.paths` pattern from the nearest configuration
   or its `extends` chain matched the specifier. A path alias wins even when it
   shadows a workspace package name.
2. `workspace_package`: the specifier names a package found by the repository's
   workspace declaration, and its entry file was selected. This is a fallback
   used when the compiler could not resolve the specifier without a dependency
   folder.
3. `package_entry_point`: a package's `package.json` entry (`exports`, `main` or
   `types`), including a dependency package, selected the target.
4. `index_file`: directory resolution selected an index file.
5. `extension`: the compiler added a file suffix to a specifier that did not
   already name the resolved file.
6. `relative`: a relative specifier named an existing file directly, with no
   alias, package entry, index or added extension step.
7. `asset`: exact-path asset resolution, used only after compiler and configured
   alias resolution failed for a literal asset extension.

For `kind: "asset"`, the result is still `asset` only when both the compiler and a
configured alias failed; otherwise the compiler or alias label is used.

## Configuration discovery

For each reference's source file, the helper:

1. Starts at the source file's folder and walks up to `repository_root`,
   inclusive.
2. Uses the nearest `tsconfig.json`. If none exists on that path, uses the
   nearest `jsconfig.json`. It never looks above `repository_root`.
3. Parses the file as JSON with comments and trailing commas allowed.
4. Resolves the `extends` chain with the TypeScript compiler and caches the
   resulting compiler options by configuration path.

With no configuration file, the compiler defaults are used. Every configuration
file read is limited to `max_file_bytes` bytes. A file that cannot be read, is
over the limit, or has invalid syntax produces a named reason for the references
that depend on it.

## Workspace packages

Before resolving references, the helper reads the repository's workspace
declaration as data. It accepts `workspaces` as an array or as an object with a
`packages` array in the root `package.json`, and `packages` in
`pnpm-workspace.yaml`. Patterns are expanded with the filesystem. For every
matched folder, the helper reads `package.json` and records its `name`,
`exports`, `types`, `typings`, `main` and `module`. No package manager is run.

- A configuration file's `extends` that names a workspace package resolves to a
  file inside that package, including a subpath such as
  `@scope/config/tsconfig.json`. A workspace package is never looked up in
  `node_modules`.
- A workspace path that contains `..` or leaves the repository is refused with
  `workspace path outside the repository`.
- If a package declares `exports`, an undeclared subpath is refused with
  `workspace package subpath is not exported`; there is no physical fallback.
- A symbolic-link configuration or workspace file is not read. Its skip is
  recorded by the file record with reason `symbolic link`.
- An import of a workspace package resolves to its entry file, including an
  `exports` subpath. `exports` is used first, then `types` or `typings`, then
  `main` or `module`. The parser then reads the entry file's own contents.
- A matched workspace package with no entry file is unresolved with
  `workspace package entry not found`.
- A matched package-name `extends` with no file is unresolved with
  `workspace configuration file not found`.
- A bare specifier that names no workspace package is resolved by the compiler.
  If it lands in a dependency folder, it stays external, not excluded.

A reference resolved by this map gets `resolution_path: "workspace_package"`. The
map is a fallback: the compiler is tried first, and a path alias that shadows a
workspace package name wins.

## Asset resolution

For `kind: "asset"`, the compiler and configured aliases come first. The helper
resolves with `ts.resolveModuleName` and the nearest configuration. If that
returns a file, its label is `path_alias` or the compiler's own path. If it does
not, a `compilerOptions.paths` substitution is checked before the exact path.

Only then does the helper join the source folder and the literal specifier and
check for a regular file at that exact path. A `?query` or `#fragment` suffix
is removed before path resolution; the parser records the reference as written.
This fallback does no extension probing, index lookup or package resolution. A
file found inside `repository_root` gets `resolution_path: "asset"`. A missing
file gets `reason: "asset path matches no file"`.

## Named reasons

A reason is one of these exact strings. It is never free-form text.

| Reason | Meaning |
|---|---|
| `module not found` | The compiler resolved nothing, and no configured path alias matched. |
| `path alias matches no configured path` | The nearest configuration declares `paths`, the specifier uses one of its alias prefixes, but no configured path yields a real file. |
| `workspace package entry not found` | The specifier names a workspace package, but its `exports`, `types`, `typings`, `main` or `module` entry does not exist. |
| `workspace package subpath is not exported` | The package declares `exports` and the requested subpath is not declared. |
| `workspace configuration file not found` | A configuration `extends` names a workspace package, but the named file does not exist. |
| `workspace path outside the repository` | A workspace package or configuration path contains `..` or leaves the repository. |
| `symbolic link` | A symbolic-link configuration or workspace file was skipped. |
| `asset path matches no file` | An asset reference has no regular file at its exact path. |
| `resolved path is outside the repository` | The compiler returned a path outside `repository_root`. |
| `configuration file cannot be read` | A configuration file selected for the source could not be read. |
| `configuration file exceeds size limit` | A configuration file is larger than `max_file_bytes`. |
| `configuration file has invalid syntax` | A configuration file is not valid JSON with comments and trailing commas. |

Only `path alias matches no configured path` marks a bare-looking specifier as a
failed alias. The parser treats any other null result for a bare specifier as an
external package.

## Refusals

An unknown `protocol_version` is refused before any reference is resolved. The
helper writes one error response, nothing else to stdout, and exits `1`:

```json
{
  "protocol_version": 1,
  "error": {
    "code": "unsupported_protocol_version",
    "message": "request protocol version 2 is not supported; this helper speaks version 1"
  }
}
```

A malformed request uses the same shape with code `invalid_request` and exits
`1`. An internal failure uses code `resolver_error` and exits `2`. An error
response has no `results` key.

The Python parser reports these as named failures, never silence:

| Helper outcome | Parser failure |
|---|---|
| Helper file or Node executable missing | `js resolver is missing` |
| Non-zero exit, including a refusal | `js resolver failed` |
| Empty stdout | `js resolver returned an invalid response` |
| Stdout is not a valid response document | `js resolver returned an invalid response` |
| Error code `unsupported_protocol_version` | `js resolver rejected the protocol version` |

The parser keeps the helper's stderr text only as supporting detail; the failure
name is one of the strings above.
