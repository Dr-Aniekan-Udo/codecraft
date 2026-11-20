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
