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
