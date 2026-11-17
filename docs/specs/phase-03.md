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
- **Parsing is bounded.** A maximum file count and a maximum file size are set. A repository over either limit fails the run with a stated reason. It never hangs or runs out of memory, and a file over the size limit is excluded with its reason, never read in part. This applies to every read, including configuration files.
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
- **A file with a syntax error is recorded as failed with the syntax error's position.** It is not skipped silently, and its edges are absent. Its node still appears, so the gap is visible on the map.
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

- **gh-aw.** Commit: `[PIN REQUIRED: full commit ID and date]`

### Build

- Read each repository's module path from its module file, and treat that path as the root for resolving imports inside the repository. Also read the workspace file and any local `replace` directives. Each workspace module and each local replacement target sits inside the repository, and resolves to its own folder with its own module path.
- Read each Go file's imports and turn them into edges. Go edges point at **packages**, not at single files. A package is the set of files in one folder with the same package name. An edge from a file to a package means the file uses that package.
- Handle the Go-specific cases in the constraints below.
- Record build constraints for each file, and exclude files that do not apply to the platform the parser is targeting, with a reason.
- Compute coverage per the shared contract, using package-level denominators.
- Create the Go fixtures used by this part.

### Constraints

- **An edge to a package is recorded as an edge to the package's folder.** It is never recorded as an edge to one file, because Go does not say which file in a package is used. The output says the target is a package.
- **Imports that point inside a repository module resolve. Imports from outside every repository module are external.** A path is inside a module only when it equals the module path, or continues from it after a `/`. So with the module `github.com/acme/app`, the path `github.com/acme/app/pkg` is inside, and `github.com/acme/app-tools/pkg` is external, recorded with its module name. Each in-repository module is checked this way, including workspace modules and local replacement targets.
- **A folder with no matching package is unresolved with that reason.** A module path that points at a folder that does not exist is never guessed at.
- **Build constraints decide which files count.** A file that is excluded for the target platform is recorded as excluded with the constraint named. It is not treated as missing.
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

### Acceptance check

1. Run the parser on each Go fixture. Its output matches the expected output exactly.
2. Run it on the pinned gh-aw repository. Report files found, files parsed, files skipped with a reason for each, and package counts. The figures add up.
3. Hand-check three packages from the gh-aw output: each edge to a package must exist in the source, and each import in the source must be accounted for.
4. Rename a package that an import points at, in a copy of one fixture, and re-run. Exactly one unresolved reference appears, with its reason named.
5. Write the gh-aw output to a file and read it back. Every field is present and the types hold.
6. Confirm the output for the Python fixtures is unchanged by this part. Re-run them and compare with their expected output.

### Stop point

Report the results with the exact output. Then wait. Do not start 3c.

## Part 3c: TypeScript and JavaScript

**Pinned real repositories for this part:**

- **Cal.diy.** Commit: `[PIN REQUIRED: full commit ID and date]`. A large TypeScript monorepo, used for workspace and path resolution.
- **freeCodeCamp.** Commit: `[PIN REQUIRED: full commit ID and date]`. Mixed JavaScript and TypeScript at scale.

### Build

- Walk the repository and decide which files become nodes. Files are TypeScript, TSX, JavaScript and JSX. Files inside dependency folders are excluded, with a reason.
- Read each file's imports and re-exports, and turn them into edges:
  - plain imports
  - re-exports (`export * from`, `export { x } from`)
  - dynamic imports whose module name is a literal string
  - type-only imports, recorded as their own kind
- Resolve every reference with TypeScript's own module resolver, through a small Node helper. The helper uses the TypeScript compiler, pinned to one version, and is called by the parser through a versioned request and response format. The nearest configuration file to each file is used, so path aliases, `extends` and index files resolve the way the compiler resolves them.
- Record coverage per the shared contract. Re-exports get their own coverage figure, because barrel files are where the video's graph silently lost edges.
- Create the TypeScript and JavaScript fixtures used by this part.

### Constraints

- **The TypeScript compiler's resolver is the authority for these languages.** The parser does not reimplement resolution rules. It asks the helper, and the helper's answer is the edge. Where the parser and the compiler disagree, the compiler is right, and the disagreement is a bug in the parser.
- **The helper has a versioned contract.** The request and response format carries a version number. The parser refuses an answer from a helper whose version it does not recognise, and reports that as a failure, not as silence.
- **The helper is pinned.** Its TypeScript version is fixed in the helper's own dependency file and recorded in every output. Changing it is a deliberate act, and it changes the parser version.
- **The helper runs in a fixed way.** It is called once per repository with all references in one batch, not once per file, so a large repository is not slowed by a process per import.
- **Re-exports must resolve or carry a named reason.** For every re-export found, the output shows whether it resolved. A barrel file with an unresolved re-export is reported with the reason, never silently shortened.
- **Path aliases from configuration resolve, and an alias that does not match is unresolved.** An alias that matches no configured path is recorded with the reason, not guessed.
- **Dependency folders are excluded, with a reason.** Installed packages are never nodes, and their imports are external.
- **Generated and declaration files are handled explicitly.** Declaration files are recorded as nodes with their kind, so they can be told apart. Generated files are excluded only when the repository marks them so, and the exclusion names the marker.
- **Coverage's denominator counts every import and re-export seen.** Type-only imports are counted in the denominator, and their kind is shown.
- **Node is a runtime dependency of the parser.** This must be approved by the user before the part is built, because it adds a runtime requirement to the server.

### TypeScript and JavaScript fixtures created in this part

1. **Barrel files.** An index file re-exporting from sibling modules, one of which is itself a barrel.
2. **Path aliases.** A configuration file with a path alias, a second configuration file that extends it, and imports that use both.
3. **Nearest configuration.** Two packages in one repository with different aliases for the same name, each resolving to its own package.
4. **Type-only and dynamic imports.** A type-only import, a literal dynamic import, and a non-literal dynamic import, which must be unresolved with its reason.
5. **Declaration files.** A declaration file beside its implementation.
6. **Mixed JavaScript and TypeScript.** A JavaScript file importing a TypeScript file, and the reverse.
7. **Dependency folder.** A folder standing in for installed packages, which must produce no nodes.

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
