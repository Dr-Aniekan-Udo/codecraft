# Parser baseline: pinned real repositories

This record holds the measured figures for each pinned real repository. Each later run of the parser on a pinned repository is compared with the figures here. A difference is either a parser change, which must be explained, or a fault, which must be fixed. Figures are updated only when a change is deliberate and reviewed.

The pinned commit ID identifies the snapshot, so no separate date is needed to find it. The date is recorded for reference only.

## Python, Part 3a

### Flask

- Commit: `22d924701a6ae2e4cd01e9a15bbaf3946094af65`
- Date: 19 February 2026
- Release: 3.1.3
- Import root: `src` (src layout)

| Measure | Figure |
|---|---|
| Files found | 235 |
| Files parsed | 83 |
| Files failed to parse | 0 |
| Files excluded | 152 (151 not a Python file, 1 environment file) |
| Excluded directories | 1 (version control metadata) |
| Edges | 166 |
| References | 966 |
| References resolved inside the repository | 309 |
| Symbols | 273 |
| Star-import references | 0 |
| External references | 373 |
| Excluded references | 0 |
| Failed references | 11 (2 non-literal dynamic imports, 9 relative imports outside the import root) |
| Namespace packages | 1 |

Check: 235 = 83 parsed + 152 excluded. 966 = 309 + 273 + 0 + 373 + 0 + 11.

### Ludwig

- Commit: `d0298809f87b12272f97388bb901f1776c37c84b`
- Date: 27 October 2026
- Release: v0.17.10
- Import root: `.` (repository root, from its build metadata)

| Measure | Figure |
|---|---|
| Files found | 1681 |
| Files parsed | 806 |
| Files failed to parse | 0 |
| Files excluded | 875 (874 not a Python file, 1 over the size limit) |
| Excluded directories | 1 (version control metadata) |
| Edges | 3493 |
| References | 12749 |
| References resolved inside the repository | 3731 |
| Symbols | 6072 |
| Star-import references | 0 |
| External references | 2942 |
| Excluded references | 0 |
| Failed references | 4 (non-literal dynamic imports) |
| Namespace packages | 71 |

Check: 1681 = 806 parsed + 875 excluded. 12749 = 3731 + 6072 + 0 + 2942 + 0 + 4.

## Status

These figures were measured after the star-import status was implemented. Neither repository contains a star import, so the star-import count is 0 and every other figure is unchanged from the earlier measurement. The figures stay valid until a parser change moves one of them. Any such change must be explained against this record before it is accepted.

## Go, Part 3b

Measured with `--language go`, on the three pinned repositories. The etcd clone was made with symbolic links enabled. The last measurement pass produced the figures below, and each pass since has matched them.

The gh-aw snapshot was measured from a clone with its version-control folder present, which gives 120 excluded directories. A pinned tarball, which has no version-control folder, gives 119; the difference is that one directory.

| Measure | etcd v3.7.3 | gh-aw v1.2.2 | lazydocker v0.25.2 |
|---|---|---|---|
| Commit | 0a173d0410a96d01091b484daae81365bbcde57e | 399a445fe2d8926c616b54b1b82a16b5b2be4445 | 7e7aadc2071d58031bf2daafca1fbd4093efc23f |
| Files found | 1468 | 8718 | 127 |
| Parsed | 1033 | 3961 | 83 |
| Failed to parse | 32 | 13 | 0 |
| Excluded | 403 | 4744 | 44 |
| Excluded directories | 7 | 120 | 6 |
| Edges | 1916 | 4769 | 116 |
| References | 7001 | 22890 | 423 |
| Resolved | 1916 | 4769 | 116 |
| External | 4906 | 18109 | 307 |
| Failed references | 179 | 12 | 0 |
| Symbols, star, cgo, excluded references | 0 | 0 | 0 |
| Packages | 189 | 290 | 16 |
| Modules | 13 | 1 | 1 |
| Schema errors | 0 | 0 | 0 |

Reading the figures:

- **Excluded** is the sum of build-constraint exclusions, files that are not Go, and files over the size limit. For etcd: 33, 359 and 11 symbolic links.
- **Failed to parse** counts files the grammar cannot read. Their readable imports appear as failed references, or as external references if they point outside the repository. For etcd the 32 failed files all carry the named `new` reason, and for gh-aw 12 carry it and one carries the generic syntax reason.
- **References** equals resolved plus external plus failed references, with no other category in use. Every reference sits in exactly one category.
- **Go release tags** are false, and no file was excluded by one in these repositories.

Any later change to these figures must be explained against this section. A change caused by a new Go parser rule is expected only where a pinned repository contains the construct the rule covers. The pinned repositories do contain readable imports in failed files, and those are counted as failed references, as the figures show. They contain no conflicting package and no malformed module file.

## TypeScript and JavaScript, Part 3c

Measured with `--language typescript`. Cal.diy was cloned with `core.symlinks=true`, so its symbolic links are read as links and never as files. The parse limits were 50,000 files and 2,000,000 bytes per file, from `PARSE_MAX_FILES` and `PARSE_MAX_FILE_BYTES`. Node was 22.14.0.

### Cal.diy

- Commit: `1c193cca8682b33b9866c792186033f7ef886682`
- Date: 1 March 2026
- Release: v6.2.0

| Measure | Figure |
|---|---|
| Files found | 10,337 |
| Files parsed | 7,354 |
| Files failed to parse | 42 |
| Files excluded | 2,834 (2,799 not a TypeScript or JavaScript file, 22 over the size limit, 10 environment files, 2 symbolic links, 1 generated file) |
| Asset files | 107 |
| Excluded directories | 5 (4 symbolic links, 1 version control metadata) |
| Edges | 30,590 |
| References | 42,532 |
| References resolved inside the repository | 31,230 |
| External references | 8,757 |
| Excluded references | 1 |
| Failed references | 2,544 (2,227 workspace package entry not found, 294 file has a syntax error, 18 module not found, 1 asset path matches no file, 1 non-literal dynamic import, 3 workspace package subpath is not exported) |
| Re-exports found | 1,239 |
| Re-exports resolved | 1,218 |
| Configuration files used | 30 |
| Schema errors | 0 |

Check: 10,337 = 7,354 parsed + 42 failed + 2,834 excluded + 107 assets. 42,532 = 31,230 resolved + 8,757 external + 1 excluded + 2,544 failed.

### freeCodeCamp

- Commit: `062c1053bdfdecb846753cbf31fb39d0674a7e1e`
- Date: 17 November 2026
- Release: none. The repository publishes no releases, so the commit is the pin.

| Measure | Figure |
|---|---|
| Files found | 19,851 |
| Files parsed | 1,164 |
| Files failed to parse | 15 |
| Files excluded | 18,557 (18,553 not a TypeScript or JavaScript file, 4 over the size limit) |
| Asset files | 115 |
| Excluded directories | 1 (version control metadata) |
| Edges | 2,567 |
| References | 5,425 |
| References resolved inside the repository | 2,572 |
| External references | 2,458 |
| Excluded references | 0 |
| Failed references | 395 (269 workspace package entry not found, 51 file has a syntax error, 61 asset path matches no file, 10 module not found, 4 non-literal dynamic imports) |
| Re-exports found | 94 |
| Re-exports resolved | 90 |
| Configuration files used | 11 |
| Schema errors | 0 |

Check: 19,851 = 1,164 parsed + 15 failed + 18,557 excluded + 115 assets. 5,425 = 2,572 resolved + 2,458 external + 0 excluded + 395 failed.

Reading the figures:

- **Files found** is parsed, failed, excluded and asset files together. An asset file is a node that is not parsed as source.
- **Excluded** for Cal.diy is 2,799 files that are not TypeScript or JavaScript, 22 over the size limit, 10 environment files, 2 symbolic links and 1 generated file. For freeCodeCamp it is 18,553 files that are not TypeScript or JavaScript and 4 over the size limit.
- **Failed to parse** counts files the grammar cannot read. Each carries a reason and a position. A readable import in one of those files that points inside the repository is a failed reference with reason `file has a syntax error`; one that points outside stays external. That rule accounts for 294 Cal.diy and 51 freeCodeCamp failed references.
- **Generated file** counts a file whose marker matched. Cal.diy has one, excluded with `generated file: @generated`; a reference to it is an excluded reference with that reason.
- **Workspace package entry not found** counts imports of a workspace package whose entry or subpath is generated or built and is absent from a fresh clone. For Cal.diy the example is `@calcom/prisma/enums`; for freeCodeCamp it is `@freecodecamp/shared/config/certification-settings`, whose exports point at `dist/`.
- **Workspace package subpath is not exported** counts an import of a subpath that a package's `exports` does not declare. Cal.diy has 3; freeCodeCamp has none.
- **Asset path matches no file** counts asset imports whose target is absent. For Cal.diy it is one generated CSS file; for freeCodeCamp it is 61 paths, including a local `env.json` that the repository does not commit.
- **Module not found** counts references whose target does not exist at the pin. For Cal.diy it is 18; for freeCodeCamp it is 10, all `.woff` font files, which are not asset files in this part.
- **Re-exports** are counted separately. The unresolved 21 Cal.diy and 4 freeCodeCamp re-exports carry one of the reasons above.
- Cal.diy's one excluded reference points at an `.mjs` file, which is not one of the four extensions read in this part.
- **freeCodeCamp and CommonJS.** `require()` loading is phase 9. Files that load code that way show those dependencies as absent from edges and from unresolved records by design.

These figures were measured after the query-suffix, bare-specifier and review fixes, with parser_version `codecraft-parsing 0.1.0 (languages typescript and javascript; tree-sitter 0.26.0; tree-sitter-typescript 0.23.2; tree-sitter-javascript 0.25.0; js resolver protocol 1; typescript 6.0.3)`.

Any later change to these figures must be explained against this section. A change caused by a new TypeScript or JavaScript rule is expected only where a pinned repository contains the construct the rule covers.
