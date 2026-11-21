# Phase 3: The parser

**Goal.** Turn a repository on disk into its files and the real connections between them, and prove the result is right.

This phase is built in three parts, in order: **3a Python**, **3b Go**, **3c TypeScript and JavaScript**. Each part ends at a stop point. Do not start the next part until the previous one's checks have been run and reported.

## Output contract (applies to every part)

The parser's output is the contract that every later phase reads. It is stated once here and must not change casually. Any change needs a written decision, because the map, the detail pane, the adapters and the agent all depend on it. The field-by-field contract of record is the parser output contract document kept with the design documents; the list below is its summary. The contract has one shared core for every language, plus a details section for each language's own data. Each language adds its own edge kinds through a written change to the contract.

The output for one repository holds:

- **Files.** For each file: its path relative to the repository root, the folder it belongs to, its line count, a content hash, its language, and whether it is a node or was excluded.
- **Edges.** For each connection: the file it starts from, the file it points to, and its kind (import, re-export, dynamic import, or, in later parts, a language-specific kind). An edge exists only when its target is a real file or package in the input.
- **Unresolved references.** For each reference that could not be resolved: the file it came from, the reference as written, and a named reason.
- **External references.** References that point outside the repository, such as standard library or third-party packages. These are recorded as external, not as failures.
- **Excluded files.** Files left out on purpose, each with a reason.
- **Coverage.** For every reference seen: how many resolved inside the repository, how many are symbols of a resolved module, how many are external, how many were excluded, and how many failed. Failures are kept as examples, not only as a count. Coverage also records the number of namespace packages in the walked repository.
- **Adapter role** for each file. In this phase, every file gets the fallback role, which assumes no framework.
- **Parser version.** Every output records the version of the parser that produced it.

Fan-in and fan-out are not part of the parser output. The frontend computes them from the edges, in line with the rule that graph arithmetic lives in the frontend.

## Shared rules (apply to every part)

- **The parser reads text. It never runs, imports, installs or builds the code it reads.** It does not need the libraries a repository depends on to be present on the machine.
- **The parser fetches nothing.** It takes a directory path. How the directory got there is not its concern.
- **Every edge comes from parsing real source.** An edge exists only when a reference resolves to a real file or package in the input. Nothing is inferred from file names, folder names, conventions or similarity.
- **An unresolved reference is recorded, never dropped and never guessed.**
- **File selection is structural.** Seed from entry points and walk outward, or keep whole directories. Never keep the largest N files by line count. That keeps a file and drops the leaf it imports, which produces edges pointing at nothing.
- **The core contains no framework name.** No web framework, UI library or database client is imported by the parser, and no framework name appears in the parser core.
- **Each part is checked on its own.** A failure in one part is found in that part's small surface, not in all three.
- **Test fixtures are plain files.** Source, manifests and an expected-output file. Nothing in a fixture is installed or run. Fixtures live in the backend's fixtures area, grouped by language, and are excluded from every workspace and linter.
- **Each language is isolated.** Code for one language does not import code for another. Shared behaviour, such as walking, hashing and output assembly, lives in a common part that every language may use. The boundary is enforced by an automated check, not by convention.
- **Parsing is bounded.** A maximum file count and a maximum file size are set. A repository over the file-count limit fails the run with a stated reason. A file over the size limit is excluded with its reason, never read in part, and parsing continues with the other files. The run never hangs or runs out of memory. This applies to every read, including configuration files.
- **Nothing is omitted silently.** A directory that cannot be listed, a file that cannot be read, and a file whose text cannot be encoded are each recorded with a reason. The run continues where it safely can. A scan with an unreadable part is never reported as complete.
- **Symbolic links never create duplicate nodes or loops.** A link is recorded with its reason and its contents are not read. A link pointing inside the repository does not create a second node for the same file.
- **Committed virtual environments are external.** A folder holding an installed environment that is committed to the repository is excluded as third-party code. Its contents create no nodes and no edges, and it is recorded with its reason.
- **Real repositories are pinned.** Each real test repository is pinned to one commit, written into this spec with its full commit ID and date. They are cloned by the test harness, never committed to our repo, and never cloned by the parser. The measured figures for each pinned repository are kept in the baseline record in the contracts area, and each later run is compared against it.

## Part 3a: Python

**Pinned real repositories for this part:**

- **Flask.** Commit: `22d924701a6ae2e4cd01e9a15bbaf3946094af65`, dated 19 February 2026, release 3.1.3
- **Ludwig.** Commit: `d0298809f87b12272f97388bb901f1776c37c84b`, dated 27 October 2026, release v0.17.10. Ludwig is primarily a machine-learning library rather than a web application. It is used here for scale and mixed import styles, not for route accuracy.

### Build

- Walk a Python repository: decide which files become nodes, count lines, hash contents, and mark package folders (folders with an `__init__` file).
- Read each file's imports with a real Python syntax parser and turn these into edges:
  - absolute imports (`import a.b`, `from a.b import c`)
  - relative imports (`from . import x`, `from ..pkg import y`), resolved from the file's own package position
  - dynamic imports whose module name is a literal string (`importlib.import_module("a.b")`)
- Determine the **import root** for the repository from its own configuration where it has one (the source directory named in its project file, or a `src` layout), and otherwise from the repository root. The import root is recorded in the output. The project file is read as data. Setup scripts that are programs are not read, so a source folder defined only in such a script is not detected and the repository root is used instead. That case is reported with the rule used.
- Classify each reference as resolved, symbol, external, excluded or failed, with a reason for every failure.
- Compute coverage and the namespace package count.
- Provide the command that runs the parser on a directory and prints a summary. Provide the option that writes the full output to a file.
- Create the Python fixtures used by this part (see the fixture list below).

### Constraints

- **Relative imports resolve from the file's package, not the repository root.** A relative import is resolved by counting its leading dots from the file's own position. Resolving it from the root produces edges to files that do not exist.
- **Namespace packages are handled explicitly.** A folder with no `__init__` file still contributes modules when it is inside the import root. The output records whether a package was regular or namespace, so a wrong guess is visible.
- **Standard library and third-party imports are external, not failures.** A module that is not in the repository is recorded as external, with its top-level name. It is never counted as unresolved, because a missing edge to `os` is not a parser fault.
- **A name in the repository that shadows an external name resolves to the repository.** If `utils` exists inside the import root, `import utils` resolves there, not to any installed package of the same name.
- **A non-literal dynamic import is unresolved with the reason "non-literal dynamic import".** It is never guessed, and never silently counted as external.
- **An imported name that is not a module is a symbol, not an edge.** For `from X import name`, when `X` resolves inside the repository and `name` names no module there, `name` is recorded in coverage with the status "symbol of resolved module, not verified". It stays in the denominator and is not a failure.
- **A star import draws its edge and is marked as names not enumerated.** For `from X import *`, the edge to `X` is drawn when `X` resolves inside the repository, as for any import. The reference carries the status "names not enumerated", because the names it brings in are not listed by the parser. No names are invented, and the status is counted in coverage, not as a failure.
- **A file with a syntax error is recorded as failed with the syntax error's position.** It is not skipped silently, and its edges are absent. Its node still appears, so the gap is visible on the map. Each import that can still be read in the failed file, and that points inside the repository, is recorded as a failed reference at its own position, with the reason "file has a syntax error". An import that points outside the repository stays external.
- **Imports inside string literals, comments and docstrings produce no edges.** Only real import statements count. Reading text with a regular expression is not an acceptable method.
- **Conditional and guarded imports are kept.** An import inside a `try` block, an `if TYPE_CHECKING` block, or a function body is a real import and produces an edge. Its kind stays `import` (or `dynamic_import`), and a separate condition label records how it is guarded: type-only, optional, or lazy. Consumers read the kind to know it is an import, and the label to know when it runs.
- **Coverage counts every import statement the parser sees**, including symbol, external, excluded and failed ones. A denominator that counts only resolvable imports makes coverage look better than it is.

### Python fixtures created in this part

Each fixture is small enough to check every edge by hand, and each has an `expected` output written before the code runs.

1. **Flat package.** Three modules, one absolute import each, one circular pair.
2. **Relative imports.** A nested package using single and double dots, including one that goes above its package and must be reported as unresolved.
3. **Namespace package.** A folder without an `__init__` file that contains modules, imported from a sibling package.
4. **Shadowing.** A repository module with the same name as a standard library module, imported by name.
5. **Guarded and dynamic imports.** An import inside a `try` block, a `TYPE_CHECKING` import, a literal `importlib` call, and a non-literal `importlib` call.
6. **Syntax error.** One file that does not parse, next to a valid file that imports it.
7. **Strings and comments.** A file that mentions an import inside a docstring and a comment, and has no real import, must produce zero edges.
8. **Imported name that is not a module.** A `from X import name` where `name` is a function or class defined in the module `X`, not a file. It must be recorded as a symbol in coverage, with no edge and no failure.

### Acceptance check

**Run these and report the numbers.** All terminal, all yours.

1. Run the parser on each Python fixture. Its output matches the fixture's expected output exactly, including every edge, every unresolved reference with its reason, and the coverage figures.
2. Run it on the pinned Flask repository. Report files found, files parsed, files skipped, and a reason for every skip. The three numbers add up.
3. Run it on the pinned Ludwig repository. Report the same figures, and report coverage. Coverage must show a real denominator.
4. Hand-check five files from the Flask output against the source. Each edge listed for them must exist in the source, and each import in the source must appear as an edge, a symbol, an external or failed reference with a reason.
5. Rename a module that an import points at, in a copy of one fixture, and re-run. Exactly one unresolved reference appears, with its reason named.
6. Write the Flask output to a file and read it back. Every field is present and the types hold.
7. Search the parser core for the names of the Python web frameworks. None appear.

**Expected numbers for the real repositories are recorded on the first run, then reviewed by the user.** They are measured, not guessed. The first recorded figures become the baseline for later runs.

### Stop point

Report the results of checks 1 to 7 with the exact output. Then wait. Do not start 3b.

## Part 3b: Go

**Pinned real repository for this part:**

- **gh-aw.** Commit: `399a445fe2d8926c616b54b1b82a16b5b2be4445`, dated 10 November 2026, release v1.2.2. This repository is one layout among many, not the target of the design.
- **etcd, the multi-module layout.** Repository `github.com/etcd-io/etcd`. Commit: `0a173d0410a96d01091b484daae81365bbcde57e`, dated 23 October 2026, release v3.7.3. Reason for choosing it: it has several modules, each with its own module file, joined by local replacement directives to sibling folders. Every local replacement target at this pinned commit exists, so the missing-target rule is tested by a fixture, not by this repository.
- **lazydocker, the single-module vendored layout.** Repository `github.com/jesseduffield/lazydocker`. Commit: `7e7aadc2071d58031bf2daafca1fbd4093efc23f`, release v0.25.2, dated 19 April 2026. Reason for choosing it: a single module whose dependencies are vendored, which tests vendor exclusion in a real repository.

### Build

- Find every module in the repository. A module is any folder that holds a module file, whether or not a workspace file names it. A module file inside a folder that the Go tool ignores, or inside a vendor or testdata folder, is not a repository module, and its folder is excluded with the reason that applies to that folder. Read each module's path from its module file, and the workspace file and local replacement directives as data. Any repository may contain one module, several modules, nested modules, or none, so the parser must handle each of these by the Go rules and never by a guessed folder layout.
- Read each Go file's imports and turn them into edges. Go edges point at **packages**, not at single files. A package is the set of files in one folder with the same package name. An edge from a file to a package means the file uses that package.
- Handle the Go-specific cases in the constraints below.
- Record build constraints for each file, and exclude files that do not apply to the platform the parser is targeting, with a reason.
- Compute coverage per the shared contract, using package-level denominators.
- Create the Go fixtures used by this part.

### Constraints

- **An edge to a package is recorded as an edge to the package's folder.** It is never recorded as an edge to one file, because Go does not say which file in a package is used. The output says the target is a package.
- **Imports that point inside a repository module resolve. Imports from outside every repository module are external.** A path is inside a module only when it equals the module path, or continues from it after a `/`. So with the module `github.com/acme/app`, the path `github.com/acme/app/pkg` is inside, and `github.com/acme/app-tools/pkg` is external, recorded with its module name. Each in-repository module is checked this way, including workspace modules and local replacement targets.
- **A folder with no matching package is unresolved with that reason.** A module path that points at a folder that does not exist is never guessed at.
- **Build constraints decide which files count, for one fixed target.** Every build constraint is evaluated for the target linux/amd64, so the same repository gives the same result on any machine. The target is recorded in the Go details of the output. A file excluded for the target is recorded as excluded, with the constraint named and the same reason stated in both the exclusion reason and the build constraint exclusion reason. It is not treated as missing.
- **Go manifests are data, not nodes.** `go.mod` and `go.work` files are file records with no language, not nodes, excluded with the reason "not a Go file". They are read for module paths and replacements, and produce no edges of their own.
- **A file belongs to the nearest module above it.** Each Go file is assigned to the module whose folder is its closest ancestor holding a module file. An import is resolved against all modules found, and the module with the longest matching path is used. A nested module is therefore its own module, and its files are never attributed to the parent.
- **Import paths match a module by exact path or by a following "/".** An import resolves to a module only when it equals the module path, or continues from it after a "/". Major-version suffixes are part of the path: a module declared as `example.com/app/v2` owns imports under that path, and a folder named `v2` does not create a module.
- **Replacement directives are classified by target.** A replacement to a local folder inside the repository makes that folder a module, and imports resolve to it. A replacement to a version is a third-party module and its imports are external. A replacement to a local folder outside the repository fails each import that uses it, with the reason "replacement target is outside the repository". A replacement to a local path that does not exist fails each import that uses it, with the reason "replacement target does not exist". Such a target is never guessed or created.
- **Module files are read as data in every valid form.** The module path may be quoted. Comments are ignored. Directives may use block form. Indirect markers are ignored. A module file with an unreadable or malformed directive has its file record carry the failure, with the reason. Each import that depends on that module is recorded as failed with the same reason. A module file with a malformed directive is omitted from the module list, and its path is not used for resolution. Imports to packages outside the repository remain external, even when they come from a file inside the failed module's folder. Only a module file with no readable path fails every import from its folder, because the parser cannot tell internal imports from external ones without it. Nothing is guessed.
- **A repository with no module file has no module path.** Imports cannot be attributed to a repository module, so each import is recorded as failed with the reason "no module file declares a path". Nothing is guessed from folder names.
- **Folders beginning with "_" or "." are excluded, each with the reason "ignored by the Go tool".** The Go tool ignores them, so they are not nodes. Vendored code and testdata are excluded as already stated.
- **The import "C" is a cgo pseudo-package, not a package.** It is neither an edge nor a failure, and it is not a third-party module. It is recorded with the status "cgo pseudo-package" and counted in coverage in its own category.
- **Importing a main package is a failure.** An import whose target folder contains only `package main` files is recorded as failed, with the reason "imports a main package". The edge is not drawn.
- **A conflicting file that already has a syntax error keeps the syntax reason.** The conflict is still reported on every other conflicting file, and on each import into that folder, with the conflict reason. The more specific cause is kept on the file where it applies.
- **Conflicting package names in one folder are a failure.** After build-constraint exclusion, a folder whose non-test files name more than one package, other than the `_test` package, records each conflicting file as failed, with the reason "conflicting package names in one folder".
- **Generated files are parsed as written.** A file whose header marks it as generated is a node like any other, because its imports are real. The parser does not trust or skip generated markers.
- **A file the grammar cannot read is failed, and its reason says so when the cause is known.** A file with a syntax error is failed with its position and draws no edges, as already stated. When the error is on, or inside, a `new` call whose argument is an expression rather than a type, the reason is "Go 1.26 new with expression argument, not read by the current grammar". An error that spans the whole file keeps the generic reason, because it does not identify a single cause. Any other syntax error keeps the generic reason. The named reason never changes whether an edge is drawn, and never causes an import to be guessed. Each import that can still be read in a Go file that fails for any reason, including a syntax error, a conflicting package name, or a damaged import block, and that points inside the repository, is recorded as a failed reference at its own position. Its reason is "file has a syntax error" when the file has a syntax error, and otherwise the file's own failure reason. An import spec that holds more than one path is recorded as a failed reference with the reason "malformed import spec", so the second path is never silently dropped. Where an import has more than one applicable reason, the first that applies is used, in this order: unreadable path; cgo; failed module; no module file; trailing slash or empty path; replacement failure; external package; file failure. Where a failed route and an external route both match, the longer path decides, as it does between a healthy module and a malformed one. Where a replacement and a module have the same path, the replacement's outcome decides: a missing local target fails, and a version replacement stays external. A replacement in the workspace file overrides one in a module file for the same module path. A target inside a folder that holds a module file that failed to parse is unresolved with that module's failure reason. An import that points outside the repository stays external, because whether a package is external does not depend on whether its file parses. No edge is drawn from any import in the failed file. A failed file's imports therefore never disappear from coverage without a record.
- **A package count includes external test packages.** The package count is the number of distinct pairs of folder and package name among the nodes. A node with no package clause has no package name, is not importable, and is not counted as a package. A test file whose package name ends in `_test` is a separate package from the package it tests, and is counted separately.
- **Test files are nodes, and they never create edges into the packages they test.** A test file imports the code it tests, but the code does not depend on its test. Test files therefore produce edges out, but no edges in from production code. This is recorded in the output as a test file, so the map can show it differently later.
- **Vendored code and generated test data are excluded, with reasons.** Vendor folders and testdata folders are not nodes and produce no edges. Each exclusion names its reason.
- **Blank imports and dot imports are recorded with their kind.** A blank import (`_ "path"`) runs for its side effects and is kept as its own kind of edge. A dot import is recorded with its kind, not hidden.
- **Aliased imports resolve to their real path.** `import g "path/to/pkg"` resolves to `path/to/pkg`, with the alias recorded.

### Go fixtures created in this part

1. **Package edges.** Two packages where one imports the other through the module path.
2. **External and unresolved.** One import from outside the module, and one import of a path inside the module that names a folder which does not exist.
3. **Build constraints.** Two files in one package with different platform constraints, one of which must be excluded for the target platform.
4. **Test files.** A package with a test file importing the package, which must produce an outgoing edge only.
5. **Vendor and testdata.** A vendor folder and a testdata folder, which must produce no nodes.
6. **Aliases, blank and dot imports.** Each kind recorded with its own edge kind.
7. **Workspace modules.** A workspace file naming two modules, where one imports the other by its exact module path. The import is an edge, and both modules are inside the repository.
8. **Local replacement.** A module file with a replace directive pointing at a folder inside the repository. The replaced module is inside the repository, and an import of it resolves to that folder.
9. **Shared prefix.** A module path and an import whose path begins with the module path but continues with a different name, for example `example.com/app` and `example.com/app-tools/pkg`. The import is external, and the file-level edge for the exact import resolves.
10. **Nested module without a workspace file.** A folder with its own module file, not named by any workspace file. Its files belong to it, and an import of its path resolves into it.
11. **Major-version module path.** A module declared with a `/v2` suffix, where a folder named `v2` is not a module, and imports resolve by the full declared path.
12. **Replacement targets.** One replacement to a version, which is external, and one to a local folder outside the repository, which is failed with its reason.
13. **Module file syntax.** A module file with a quoted path, comments, a block-form require directive and an indirect marker. Its path is read correctly, and the directives are data only.
14. **No module file.** A repository with Go files and no module file. Every import is failed with the reason "no module file declares a path".
15. **Ignored folders.** Folders beginning with "_" and with "." contain Go files. They produce no nodes, each with the reason "ignored by the Go tool".
16. **cgo import.** A file importing "C". The import has the status "cgo pseudo-package", and produces no edge and no failure.
17. **Main package import.** A file importing a folder that contains only a main package. The import is failed with the reason "imports a main package", and no edge is drawn.
18. **Conflicting package names.** A folder with two non-test package names. Each conflicting file is failed with its reason.
19. **Generated file.** A file with a generated-code header. It is a node, and its imports are edges as for any other file.
20. **Malformed module file.** A module file with an unclosed recognised block. The module is omitted, and each import that depends on it is failed with the module file's reason.
21. **Ignored module directives.** A module file with directives the parser does not use. They are ignored, and the module is read normally.
22. **Module file over replacement.** A folder with its own module file, reached by a replacement. Its source is module_file.
23. **Grammar failure reasons.** Two files that fail to parse: one with a new call whose argument is an expression, which gets the named reason, and one with another syntax error, which keeps the generic reason.
24. **Malformed module with no readable path.** A module file with no module line. Every import from its files is failed with the module file's reason.
25. **Folder without a package name.** A file with no package clause. It is not importable and is not counted as a package.
26. **Conflict with a failed file.** A folder whose files name two packages, one of which also has a syntax error. The syntax file keeps its reason, the other file carries the conflict reason, and an import into the folder fails with the conflict reason.
27. **Malformed module with an external import.** A malformed module whose file-level imports include a third-party package. The third-party import stays external, and only the import of the module's own path fails.
28. **Readable imports in a failed file.** A file with a syntax error in its body, with readable imports before the error. Each import that points inside the repository is failed at its own position, and each external import stays external. No edge is drawn.
29. **Imports in a damaged body.** A syntax error inside a function body, followed by an import group. The readable imports are recorded as in fixture 28.
30. **Conflicting file with imports.** A folder whose files name two packages, where a conflicting file imports a path outside the repository and a path inside it. The outside path stays external. The inside path fails with the conflict reason, at its own position.
31. **Malformed import spec.** A single import line with two paths. The first path is ordinary. The second is failed with the reason "malformed import spec", at its own position.
32. **Legacy build precedence.** A file with a modern build line and a legacy build line that disagree. The modern line decides, and the file is included for the target.
33. **Deep build expression.** A build expression nested beyond the reader's depth limit. The file is excluded with the reason "malformed build constraint", and the run continues.
34. **Ignored filenames.** A Go file whose name begins with an underscore is ignored by the Go tool: it is not a node and contributes no imports. A non-Go dotfile is still reported as not a Go file.
35. **Quoted manifest paths.** A replacement whose local target has a space in its quoted path. The path is read as one argument, and imports resolve to it.
36. **Workspace replacement override.** A go.work replacement overrides a failing replacement in a module file for the same path. The workspace target wins.
37. **Non-test package named with a test suffix.** A non-test file whose package name ends in a test suffix is importable, and takes part in conflict detection.
38. **Malformed root with a healthy nested module.** The healthy nested module resolves its own imports. Imports that depend on the malformed root fail with the root's reason.
39. **Nested module ownership.** An import into a nested module's folder, through the parent's path, is unresolved with the reason "package folder belongs to another module". The nested module's own path resolves.
40. **Unknown characters in a build expression.** A build expression containing a character outside the allowed set is excluded with the reason "malformed build constraint". Fixture 40 was written before the code.
41. **Replacement and module with the same path.** A missing local replacement target fails each import of that path, with the reason "replacement target does not exist". The replacement's outcome decides over the module of the same path.
42. **Failed and external routes.** When a failed route and an external route both match, the longer path decides. The shorter failed route does not override the longer external one.
43. **Failed nested module.** A target inside a nested folder whose module file failed to parse is unresolved with that module's failure reason, and does not resolve through the parent.
44. **Modern build line with a comma.** A modern build line containing a comma is excluded with the reason "malformed build constraint". Legacy lines keep their comma-separated grammar.
45. **Workspace replacement precedence.** The go.mod replaces a path with one folder, and go.work replaces it with another. Both folders declare the module path. The workspace folder is selected, and the import resolves to it.
46. **Failed module depth.** A malformed root module, and a healthy nested module one level down. An import into the nested module resolves, because the healthy module owns its folder and the root is above it.
47. **Legacy-only build line.** A file with only a legacy build line, and no modern line. The legacy line is evaluated and decides exclusion for the target.

### Acceptance check

1. Run the parser on each Go fixture. Its output matches the expected output exactly.
2. Run it on each pinned Go repository. Between them they must cover at least two different module layouts. Report files found, files parsed, files skipped with a reason for each, and package counts. The figures add up.
3. Hand-check three packages from the gh-aw output: each edge to a package must exist in the source, and each import in the source must be accounted for.
4. Rename a package that an import points at, in a copy of one fixture, and re-run. Exactly one unresolved reference appears, with its reason named.
5. Write the gh-aw output to a file and read it back. Every field is present and the types hold.
6. Confirm the output for the Python fixtures is unchanged by this part. Re-run them and compare with their expected output.

### Stop point

Report the results with the exact output. Then wait. Do not start 3c.

## Part 3c: TypeScript and JavaScript

**Pinned real repositories for this part:**

- **Cal.diy.** Commit: `1c193cca8682b33b9866c792186033f7ef886682`, dated 1 March 2026, release v6.2.0. A large TypeScript monorepo, used for workspace and path resolution. It depends on symbolic links, which are read as links and never as files, under the shared rules.
- **freeCodeCamp.** Commit: `062c1053bdfdecb846753cbf31fb39d0674a7e1e`, dated 17 November 2026. The repository publishes no releases, so this commit was chosen as the pin rather than a release tag. Mixed JavaScript and TypeScript at scale. Part 3c reads `import` and `export` syntax only. Files that load code with `require()` will show their dependencies as unresolved, because `require()` is handled in phase 9. Coverage for this repository must state that limit, and the baseline must record it.

### Build

- Walk the repository and decide which files become nodes. Files are TypeScript, TSX, JavaScript and JSX. Files inside dependency folders are excluded, with a reason.
- Read each file's imports and re-exports, and turn them into edges:
  - plain imports
  - re-exports (`export * from`, `export { x } from`)
  - dynamic imports whose module name is a literal string
  - type-only imports, recorded as their own kind
  - imports of asset files (JSON, CSS, SVG and images), each as its own kind, pointing at the real file
- Resolve every reference with TypeScript's own module resolver, through a small Node helper. The helper uses the TypeScript compiler, pinned to one version, and is called by the parser through a versioned request and response format. The nearest configuration file to each file is used, so path aliases, `extends` and index files resolve the way the compiler resolves them.
- Read the repository's workspace declaration as data, and map each workspace package's name to its folder. A configuration file's `extends` that names a workspace package resolves to that package's file, and an import of a workspace package resolves to its entry file. No dependency folder is read.
- Record coverage per the shared contract. Re-exports get their own coverage figure, because barrel files are where the video's graph silently lost edges.
- Create the TypeScript and JavaScript fixtures used by this part.

### Constraints

- **The TypeScript compiler's resolver is the authority for these languages.** The parser does not reimplement resolution rules. It asks the helper, and the helper's answer is the edge. Where the parser and the compiler disagree, the compiler is right, and the disagreement is a bug in the parser.
- **The helper has a versioned contract.** The request and response format carries a version number. The parser refuses an answer from a helper whose version it does not recognise, and reports that as a failure, not as silence.
- **The helper is pinned.** Its TypeScript version is fixed in the helper's own dependency file and recorded in every output. Changing it is a deliberate act, and it changes the parser version.
- **The helper runs in a fixed way.** It is called once per repository with all references in one batch, not once per file, so a large repository is not slowed by a process per import.
- **Re-exports must resolve or carry a named reason.** For every re-export found, the output shows whether it resolved. A barrel file with an unresolved re-export is reported with the reason, never silently shortened. A re-export of an asset is a re-export edge with the asset resolution path, and it counts in the re-export figure.
- **Path aliases from configuration resolve, and an alias that does not match is unresolved.** An alias that matches no configured path is recorded with the reason, not guessed.
- **An asset import is an edge to the real file, with its own kind.** JSON, CSS, SVG and image imports are dependencies that fail at runtime when the file is missing, so folding them into `import` or dropping them hides a real reference. An asset path that matches no file is unresolved with its reason.
- **A query or fragment on a specifier is not part of the file path.** Bundlers append `?inline`, `?raw`, `?url` and `#...`; resolving the suffix as a filename reports a real file as missing. The path before the suffix is resolved, and the reference is recorded as written.
- **Dependency folders are excluded, with a reason.** Installed packages are never nodes, and their imports are external.
- **A bare specifier is classified before the asset fallback.** A bare specifier that names no workspace package is external, whatever its extension, because a dependency's JSON file is not a missing asset.
- **Workspace packages resolve inside the repository without an install.** A fresh clone has no dependency folder, so a package-name `extends` or a workspace import would otherwise fail even though the code is present. The workspace declaration and each package's name and entry are read as data, and the compiler resolves the entry file's own contents. A workspace import is an edge when its entry exists, and otherwise unresolved with a named reason. A dependency folder stays external. When a package declares `exports`, a subpath it does not declare is unresolved with a named reason; there is no physical fallback.
- **Generated and declaration files are handled explicitly.** Declaration files are recorded as nodes with their kind, so they can be told apart. Generated files are excluded only when the repository marks them so, and the exclusion names the marker.
- **Coverage's denominator counts every import and re-export seen.** Type-only imports are counted in the denominator, and their kind is shown.
- **Node is a runtime dependency of the parser.** Approved. The helper runs on Node LTS, with its TypeScript version fixed in its own dependency file. It reads text and returns paths, and never installs, imports or runs code from the analysed repository.

### TypeScript and JavaScript fixtures created in this part

1. **Barrel files.** An index file re-exporting from sibling modules, one of which is itself a barrel.
2. **Path aliases.** A configuration file with a path alias, a second configuration file that extends it, and imports that use both.
3. **Nearest configuration.** Two packages in one repository with different aliases for the same name, each resolving to its own package.
4. **Type-only and dynamic imports.** A type-only import, a literal dynamic import, and a non-literal dynamic import, which must be unresolved with its reason.
5. **Declaration and generated files.** A declaration file beside its implementation, and a generated file with a marker that must be excluded with the marker named.
6. **Mixed JavaScript and TypeScript.** A JavaScript file importing a TypeScript file, and the reverse.
7. **Dependency folder.** A folder standing in for installed packages, which must produce no nodes.
8. **Asset imports.** A source file importing a JSON file, a CSS file and an image, each resolving to a real file, one asset import that matches no file, which must be unresolved with its reason, one asset import with a query suffix, which resolves to its file, one bare package asset specifier, which must be external, and one asset re-export, which is a re-export edge with the asset resolution path and counts in the re-export figure.
9. **Workspace package.** A root workspace declaration, a package with a name and an entry, a configuration package, an app importing the package, and a configuration file extending the configuration package. The import is an edge, the `extends` is read, and no dependency folder exists. An import of an undeclared `exports` subpath must be unresolved with its reason.

### Acceptance check

1. Run the parser on each TypeScript and JavaScript fixture. Its output matches the expected output exactly.
2. Run it on the pinned Cal.diy repository. Report files found, files parsed, files skipped with a reason for each, re-exports found, and re-exports resolved. The re-export figures match, or every gap has a named reason.
3. Run it on the pinned freeCodeCamp repository. Report the same figures, plus coverage and the number of unresolved references, with examples of each reason.
4. Hand-check five files from Cal.diy. Each edge must exist in the source, and each import must be accounted for.
5. Rename a module that an import points at, in a copy of one fixture, and re-run. Exactly one unresolved reference appears, with its reason named.
6. Write the freeCodeCamp output to a file and read it back. Every field is present and the types hold.
7. Confirm the Python and Go fixtures' outputs are unchanged. Re-run both and compare with their expected output.
8. Confirm the helper rejects a request with an unknown version and reports a failure.

### Stop point

Report the results with the exact output. Phase 3 is complete when all three parts have passed. Then wait for the user's decision on phase 4.

## Not in this phase

- Framework adapters. Every file gets the fallback role. Adapters come in phases 8, 10 and 11.
- `require()` calls. These come in phase 9.
- Anything rendered. This phase ends in a terminal.
- Folding, the map and the canvas. These come in phase 4.
