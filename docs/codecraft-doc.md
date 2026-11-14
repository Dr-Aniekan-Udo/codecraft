# CodeCraft: Design

The product decisions behind this build, written before it starts, with the reasoning attached. The reasoning matters more than the decision. You will hit forks this document doesn't cover, and you need to know which way the thinking was leaning.

Read the part you need before you build something. Don't read it all at once, and don't paste it into a prompt.

## What it is

Sign in, point CodeCraft at a repository, and get a map of it. The repository can be a public GitHub URL or a local directory. Each folder is a box, and each import is a line between files. Open a folder into its files. Select a file and see what it imports, what imports it, and what breaks two levels out if it changes. Ask for an explanation and get a paragraph written from that file and its real neighbours. Ask a question of the repository and watch it look the answer up.

The codebase can be TypeScript, JavaScript, Python or Go, or a mix of them. Config and data files that carry real relationships to code are part of the map too: JSON, YAML, TOML, SQL and Dockerfiles.

## The problem

Codebases now routinely contain code nobody on the team has read. An agent wrote it, someone confirmed it worked, it shipped. That is a reasonable way to work, and it is not going to stop. But it accumulates structure nobody chose: files that import through three layers of re-exports, a utility forty files depend on, a module nothing has referenced in months.

The questions that follow are structural. What is this file, what depends on it, what breaks if it changes. Answering them today means reading imports one file at a time and holding the results in working memory. That stops working at around thirty files, and it stops being attempted at all somewhere past a hundred.

## Who it's for

A developer opening a codebase they didn't write. Most often it's one they built with an agent, across many sessions, and can no longer hold in their head.

They can read code fine. What they can't see is its shape.

Increasingly this is a team problem. A team of four all shipping this way inherits four sets of code nobody read, and the person who joins next inherits all of it at once. So an analysis belongs to an organisation rather than to whoever ran it. A repository is mapped once, and everyone after that starts from the map.

This description is the test every feature is measured against. When something tempting comes up, such as a quality score, a rating or a review panel, the question is whether this person wants it. Usually they don't. They want to know what depends on this file.

## Why this hasn't stuck before

Codebase visualisation is not a new idea, and the track record is poor. CodeSee built something close to this with real funding and is gone. Sourcetrail ran for years as a desktop tool and was archived. Any plan here has to account for that rather than assume it away.

The most likely explanation is that both were selling a map of a codebase the user had already read. A map you could have drawn yourself is a nice-to-have, and nice-to-haves lose. What changed is that people now ship code they have never read. That turns the same artifact into something needed on a specific afternoon, for a specific reason.

The current generation of AI tools mostly works the other way round. They hand the repository to a model and let it describe the structure. That is much faster to build, which is why there are many of them, and it is the approach this product deliberately does not take.

That's the bet. It is a bet, and it should be stated as one.

## The rule everything rests on

**Every box and every line comes from really parsing the code.**

The AI may explain and label. It may never decide that two files are connected, and it may never walk the graph when arithmetic can do it instead.

A dependency graph that is ninety percent right is worse than no graph, because there is no way to tell which ten percent is wrong. The moment a model is allowed to guess at an edge, every edge becomes a maybe, and the product is a nice-looking picture.

An edge exists only when a reference resolves to a real file or a real table in the input. A reference that cannot be resolved is recorded with its reason and never guessed into an edge. A route is shown only when its method and full path are both exact. A name that merely looks similar to a real file is not evidence of a connection.

## Scope

- Sign-in with GitHub, Google or email, for identity only. No repository scope, no stored user token. Public repositories only.
- Organisations. Every analysis belongs to one. People are invited into one, and what they can see follows from which one they are in. Two roles, the identity provider's defaults: admin and member. The creator is the owner, and holds the admin role.
- Parsing every file in scope. Imports, re-exports, dynamic imports and `require` calls become edges, because a large amount of real code still uses them.
- Fan-in and fan-out per file.
- The map, with folders folding into boxes, expanding into files, selection, highlighting and a detail pane.
- Blast radius and dependency chain, as arithmetic over the edge list.
- Explanations of files and folders, with a cache that is not optional.
- Labelling files that convention could not identify, rather than guessing what they are.
- Coverage reporting: how much of the repository was parsed, and why the rest was not.
- Live progress while a repository is analysed.
- A chat panel answered by an agent that looks facts up rather than recalling them.
- Evaluations that measure the explanations and the agent, so changes are judged by a number.
- Framework knowledge through adapters: Next.js and Express for TypeScript and JavaScript, FastAPI for Python, and the Go standard HTTP package for Go. Each adapter recovers only exact routes.

## Language rules

Each rule below is a constraint on the resolver. Where the rule says "reported", the reason is recorded and shown.

**TypeScript and JavaScript.** Resolution is done by the TypeScript compiler's own resolver, not by a reimplementation. Its answers are authoritative. Every resolved import records which resolution path was taken: an extension, an index file, a package entry point or a path alias.

- Under a package that declares itself as a module, relative imports must carry runtime-valid extensions. An import that compiles but would fail at runtime is reported as a runtime problem.
- Workspace packages inside the repository resolve to their files. Anything in dependency folders is external and is counted, not drawn.
- Type-only imports and exports are a separate edge kind, so runtime dependencies can be told apart from compile-time ones.
- Imports of JSON, CSS, SVG and image files are edges of an asset kind.
- `require` and `import()` with a literal string are edges. A template string or a variable is reported as unresolved. Bundler globs expand to one edge per matched file.
- Aliases defined only in a bundler's configuration are reported as unresolved, unless that configuration is read too.
- An import whose letter case differs from the file on disk is reported, because it works on some operating systems and fails on others.
- Symbolic links inside the repository must not create duplicate nodes or loops.
- Build output, minified files and generated bundles are excluded by default and reported as excluded, not as missing.

**Python.** Resolution depends on the import root, which is determined from the project's metadata and reported. Layout is either flat or under a source folder, and the rule that chose it is shown.

- Relative imports that climb above the top-level package are reported as unresolved.
- Packages without an initialisation file are followed as namespace packages, and coverage notes that they were.
- Star imports create an edge to the module. The names they bring in are unknown unless the module declares them, and the map says so.
- Imports under a type-checking guard are type-only. Imports inside a function are lazy. Imports inside an optional-dependency guard are optional. Each is its own edge kind.
- `importlib.import_module` and `__import__` with a literal string are edges. Computed names are reported.
- When a stub file and a source file both exist, they describe one module.
- Files that cannot be parsed, use a legacy encoding or contain legacy syntax are reported with the reason.
- Virtual environments committed to the repository are external.
- Test files and the test runner's configuration are entry points, because the runner reaches them, not imports.

**Go.** Go's package model is different, so edges point at packages and each package maps to the files in its directory.

- The module path comes from the module file. Replacement directives and multi-module workspaces are read, so the repository boundary is correct.
- Test files form their own edge kind. External test packages in the same directory are separate packages.
- Build constraints exclude files for other platforms. Excluded files are reported as excluded for the build context shown on the map, never as absent. The default context is shown to the person viewing the map.
- Dot imports and blank imports each have their own edge kind.
- Calls into C code are reported as unresolved, because the C code is not part of what the parser reads.
- Embedded files with a literal path are edges. A glob expands to the matching files.
- Files marked as generated are labelled as generated.

**Configuration and data files.** These produce edges only when a value names something that exists in the input.

- JSON with comments and trailing commas is read as JSONC, because the TypeScript configuration format allows both.
- Files over the size limit are skipped with a reason, never read partially.
- YAML anchors, aliases and multiple documents are supported. Literal references, such as a local action in a CI workflow or a build context in a compose file, are edges. Templated values are reported as unresolved.
- TOML entry points and tool configuration that name paths are edges.
- SQL is read for one declared dialect. A table reference is an edge only when the table is created in the input. Migrations are applied in order so the map shows the final state and keeps the history. Dynamic SQL built in strings is reported as unresolved.
- Dockerfile copies from a build stage are edges to that stage. A copy is an edge to a file only if the build context includes it, so ignore rules are read.

## Out of scope, and why

Each of these is something a model will propose, because each sounds like an improvement. The reason matters more than the refusal.

- **Scores, grades, severity badges and "issues found".** This product explains a codebase. It does not review one. Once there is a number, people argue with the number instead of reading the map.
- **The agent walking the graph itself.** The agent picks a starting point and a direction. The same arithmetic that draws the map does the walk. If the model does the walking, invented structure returns.
- **Private repositories.** This requires a user token that would then have to be stored. Not in this version.
- **Approximate routes.** If a route's method and full path cannot both be recovered from the syntax, nothing is shown. A wrong route is the same failure as an invented edge.
- **Cross-language edges.** A TypeScript call matching a Python route is heuristic, and it is the first place a guessed edge would appear.
- **Third-party code.** Packages in dependency folders, the Go module cache and Python environments are external. Analysing them would multiply the map and mix someone else's structure into this one.
- **Other web frameworks.** Frameworks beyond the four adapters in version 1 are not supported yet. Each one is added as its own adapter, and each must first state which of its routes can be recovered exactly.
- **Documentation frameworks.** Their content is prose, and prose is excluded from the map.
- **Notebooks, Vue, Svelte and Astro.** Each needs its own parser. Until one exists, these files are reported as skipped with a reason, so the map never pretends to understand a file it cannot read.
- **Languages beyond the four listed and the configuration formats listed.** Not because they are hard, but because getting these right is the whole proposition.

## How it works

No folder names here. The structure is yours to choose. These are constraints on behaviour.

**The parser is standalone.** It takes a directory and returns files, edges, unresolved references and a coverage report. It does not know the web framework or the database exists, and it runs from a plain script with nothing else running. If it can't run standalone, the layering is wrong.

**Each language has its own parser, and every parser emits the same representation.** The representation holds the files, the symbols, the edges (each with a kind and a source location), the unresolved references (each with a reason) and the coverage report. Storage, graph calculations, the API, the explanations and the agent work only on that representation, and none of them learn which language produced an edge. Supporting a new language means writing one parser.

**The TypeScript resolver is a separate helper.** It is a small Node program that uses the TypeScript compiler to resolve references. The Python parser calls it through a versioned contract, and both sides validate the messages they exchange. The TypeScript version is pinned, because resolution results change between versions. Node is provided by the project's tool pinning, not by whatever is installed on the machine.

**Framework knowledge is an adapter, not a branch.** Knowing that a file in a particular position is a page is framework knowledge, and it lives in an adapter. The parser contains no framework checks. An adapter may classify files and recover routes, and it may only use facts the parser already produced.

**Graph calculations are pure functions** over a list of files and a list of edges. They do no data fetching and need nothing mocked to test them.

**Parsing is bounded.** Explicit limits on file count and file size make a large repository fail with a stated reason rather than hang or run out of memory.

**Coverage counts what the parser did not look for.** Module-loading syntax the parser does not recognise is counted as unreported, not as success. A project whose graph is nearly empty while coverage reads 100 percent is a failure, and the map must show it as one.

**Analyses record the parser version that produced them.** When the parser changes, existing analyses are marked as stale, so an old result is never presented as current.

## Pipeline

A person pastes a public GitHub URL or chooses a local path. The analyzer fetches the repository as an archive, selects the files in scope, parses them, and stores the result. The person then goes straight to the map.

- Each analysis records the commit it came from, so a repository is never silently re-analysed.
- One analysis exists per repository per organisation. Pasting a repository that has already been analysed opens the existing analysis. Rerunning is a separate, explicit action.
- Progress is streamed to the page as the run moves through its stages. The browser does not poll.
- Every network call has a timeout. A stalled download fails the run with a recorded reason instead of hanging.
- A run that throws records the failure. A run that disappears without failing is marked stale after a defined period, so the dashboard never shows a dead run as working.
- Status updates carry the identifier of the run that made them and apply only if that run still owns the record. A slow run that fails late must not overwrite a newer run's result.

## Frameworks

Version 1 has one framework adapter for each language: Next.js and Express for TypeScript and JavaScript, FastAPI for Python, and the Go standard HTTP package for Go. An adapter reads a framework's conventions on top of the parser's output, using only facts the parser already produced. It gives files roles, and it recovers routes only when both the method and the full path are exact.

**Next.js.** Roles come from file conventions: page, layout, route handler, loading, error, not-found, template, middleware, instrumentation and configuration files, plus the pages-router convention. Routes come from route handler exports named for an HTTP method, and from page locations. Dynamic segments are shown in their written form, never expanded to guessed values. Route groups, parallel-route slots and intercepting routes are recognised so their paths are read correctly. Server actions are marked by their `"use server"` directive, at file level or function level. Client boundaries are shown, so the map can display where server and client code meet.

**Express.** Roles come from folder conventions for routes, controllers, services, middleware and models, with both singular and plural names accepted. Routes are shown only when the path is a literal and the router is the application itself, or when the full path is complete in one file. Routers mounted under a prefix in another file, and routes built from variables, are composed across files and cannot be recovered exactly. Those routes are not shown, and the coverage report states why.

**FastAPI.** Roles come from folder and naming conventions for routers, schemas, models, services and dependencies, with singular and plural names accepted. Routes are shown when a route decorator on the application object has a literal path. Routes on a router are shown only when that router's full path is complete in the same file. A prefix supplied by an include call in another file composes the path across files, so those routes are not shown, and the coverage report states why.

**Go standard HTTP package.** Roles come from package and file conventions: command entry points, handlers, and internal packages. Routes are shown when a pattern registered on a mux in the same file is a string literal combining a method and a path, as the standard library accepts since Go 1.22. A mux passed between files, or a pattern built from variables, is composed or computed, so those routes are not shown.

Every adapter is tested with fixtures that contain both a literal route, which must be shown, and a composed route, which must be absent. Adding a framework later follows the same steps: it states its exact cases before it is built, and its fixtures come with it.

## The interface

A dense developer tool, not a dashboard. Small type, tight spacing, and monospace for anything that is a file path. Someone using this is scanning many names at once, and the layout should assume that.

**The hierarchy.** An organisation holds projects. A project is one repository and holds its analyses over time. An analysis is one run, pinned to a commit, and is queued, running, complete or failed. The workspace is the map and detail view of one analysis. The organisation's root lists its projects, a project's page lists its analyses, and an analysis's page is its workspace. The three columns stay the same on every route.

**The shell has three columns and is built once.** The three columns take 3, 8 and 4 parts of the width. The left rail is context: the current selection and its count, with coverage and exploration added in later phases. Its position and width do not change. The map fills the middle. The detail pane sits on the right. The pane has an Overview tab when nothing is selected, and tabs for Structure, Explanation and Ask once a file or folder is selected. Later phases fill these areas and do not move them.

**Folding is a rule, not a guess.** Every directory starts as its own node. Working from the deepest directory upward, any directory holding fewer than two files merges into its parent. Opening a folded node shows its files, and a folder with many files scrolls. The two-file threshold is the default, and it is tuned against real repositories before it is treated as final.

**Edges have a direction the eye can read without colour.** Incoming edges are solid, with the arrowhead at the file. Outgoing edges are dashed, with the arrowhead at the target. Colour reinforces direction but never carries it alone.

**Selection shows the neighbourhood.** Selecting a file or folder keeps it, its edges and the items they connect to at full strength, and dims the rest. Clicking the same item again, clicking empty canvas or closing the pane clears the selection.

**Anything derivable from the edge list is instant.** If an answer is arithmetic over data the browser already holds, it appears immediately, with no spinner and no network request. A spinner in front of arithmetic teaches people to distrust the fast paths, and most of the interface is fast paths.

**The map is drawn deterministically.** The layout is computed in the browser from the edge list. The same analysis always draws the same way, so a person can return to a map and find things where they left them.

**Insights are collapsed by default.** They report import cycles, files nothing imports, heavily depended-upon files and unusually large files. A file that nothing imports is not automatically unused. Pages, routes, layouts, middleware and test files are reached by the framework or the test runner, so they count as entry points, and the insight does not flag them.

**Coverage is visible, not buried.** Parsed, skipped and unresolved counts sit where a person looks first. A map that hides its gaps is the failure this product exists to prevent.

**The palette uses the Okabe-Ito set,** which is designed to stay distinguishable under common colour-vision deficiency. Incoming is blue. Outgoing is vermillion. Blue and vermillion are the most reliable pair across deuteranopia, protanopia and tritanopia. Green and amber are not used, because red-green colour blindness collapses them into nearly identical tones.

**Three theme states:** follow the system, force light, or force dark. The choice survives a reload, and both palettes are complete and verified separately.

**Accessibility is WCAG 2.2 AA.** This is part of every phase's acceptance, not a later pass.

- Colour is never the only signal. Every meaning carried by colour also has a shape, a dash pattern or a text label.
- Selection is shown by an outline and a tinted fill, not by a hue, so selecting something cannot be mistaken for a direction.
- File kinds are shown by a label and an icon. Colour may reinforce a kind but never carries it alone.
- Text meets 4.5 to 1 contrast against its surface. Meaningful graphics, including edges, node borders, the selection outline and the focus ring, meet 3 to 1.
- Every action on the map can be done from the keyboard, focus is always visible, and every file and edge has a text label that a screen reader announces. The same data is available as a list, so the map is never the only route to information.
- Type stays readable at 200 percent zoom without horizontal scrolling of the main content. Interactive targets are at least 24 by 24 CSS pixels.
- Nothing moves unless it was clicked. Any transition respects the system's reduced-motion setting.

## Explanations

An explanation is written from the file's real neighbours: what it imports, what imports it and its role. The model receives the file source, fetched at the analysed commit and checked against the stored hash, together with the edges read from storage.

Each explanation is cached by the hash of its content. If the file has not changed, the cached explanation is returned. If it has changed, a new one is generated.

The cache lookup happens inside the trace, not before it. A cache hit appears as a recorded run that contains no model call and no tokens, so the cache can be verified rather than assumed.

Files that no adapter could classify are labelled with a role from a fixed list. A label is generated when someone asks for an explanation of that file. It is never a routable role, and it never changes the graph.

Every explanation is checked against the paths it was shown. Any path the explanation names that was not in the context it received is recorded as invented on the trace. This check is code, not a model.

## The agent

The chat panel is answered by an agent that runs as its own service, separate from the web API. The service is written in Python, and it calls the API's read-only endpoints for everything it needs. It has no database credential and no signing key.

The agent has six tools: a summary of the analysis, a search of files by part of a path, a list of files by role, the direct neighbours of a file, a transitive walk in either direction, and the route table. Each tool is a thin wrapper around the same graph functions that draw the map. The agent never has its own version of the traversal.

The model never chooses which analysis it can see. When a person asks a question, the API mints a short-lived token that names one organisation and one analysis, and it signs that token with a key only the API holds. The agent carries the token to the API, and the API checks it on every request. Repository text can contain instructions, and those must not change what the agent is allowed to read. A tampered, expired or foreign token reads nothing.

The agent's instructions define its behaviour. It answers only from lookups, and every answer shows the lookups it made before the answer. It does not infer a connection from a name or a convention. It does not judge quality, security, performance or style, because the dependency map cannot show those, and it says what it can answer instead. A failed lookup returns an explicit failure, never a plausible answer.

The agent is self-hosted in the project's own container. It is not deployed to a vendor-managed runtime, so no repository content is held outside the project's control beyond what the observability backend receives.

## Evaluation

Quality is measured with three kinds of evaluator. Each one answers a different question, and the design is honest about which answers are exact.

- **Invented paths.** Deterministic. Every path an explanation names is compared with the set of paths it was shown. This is set membership, with an exact answer, and it runs live on every explanation the system serves, cached or not. The check must reject a path that matches only the tail of a real one, and a path hidden behind spacing or formatting. Tests try to fool it on purpose.
- **Role accuracy.** Deterministic ground truth. Roles that naming conventions already determine are the expected answers. The classifier is shown the file without its own convention label, and only the roles it is allowed to return are scored. A file that imports itself must never have its own label in the neighbour list, because that would give the model the answer.
- **Prompt comparison.** The same dataset is run through two prompt versions, and the results are scored side by side, so a change to a prompt is judged by a number.

Some quality questions have no exact answer. Whether an explanation is specific enough is judged by a model, and the results are reported as judgments, not as facts. A judged score is never presented as harder than it is.

Evaluation datasets are built only when every example has been created. An incomplete dataset is removed rather than reused.

## Observability

Instrumentation uses OpenTelemetry, which is vendor-neutral. Traces are exported to LangSmith, which is the first backend and is used for traces and for experiments.

Traces contain repository content, because prompts include file source and outputs echo it. Before any repository content is sent to a backend, the data region of that backend must be confirmed against the project's requirements, and the retention period must be known. Until both are confirmed, tracing runs only against local content.

Every model call is traced. The cache lookup happens inside the trace, as described in the explanations section.

## Authentication

Clerk handles identity and organisations: sign-in through GitHub, Google and email, organisation creation, invitations, and the admin and member roles. The creator is recorded as the owner in the membership mirror, and holds the admin role. Custom roles are not part of this version. An admin can delete an organisation through the identity provider's browser interface, because the admin role carries that permission and Clerk does not allow it to be removed from the creator's role. This is accepted: admins are elevated only by the owner, after the owner trusts them, and deletion still removes the organisation's data through the webhook.

Sign-in is for identity only. The GitHub sign-in requests no repository scope, and no user token is stored.

Every person gets a personal organisation at first sign-in. A person who was invited can also accept the invitation and belongs to both organisations.

Authorization is not Clerk's job. Clerk establishes who a person is. The database decides what that person may read.

The session token may carry the organisation's name so that the workspace title can render on the first paint. That name is display only and is never used for authorization.

**Revocation is the point that must be right.** An organisation claim carried inside a signed token goes stale. Removing someone would take effect only when their token refreshed. So membership is mirrored into the database. Clerk's organisation events arrive by webhook, and the API writes them into a membership table. Row-level policies check that table on every query, not the token. Removal takes effect as soon as the webhook is processed.

## Database

Postgres on Supabase, with access control enforced in the database.

Postgres is used because the requirements are Postgres features: organisations, shared analyses and per-row access rules. A single-file database has no policy layer, so its authorization would sit in application code, and the rule that the database decides who may read a row would no longer hold.

Row-level security is enabled on every table, with explicit policies. Column privileges hide internal fields from the API role. No view exposes rows without a policy. Application code cannot widen access, because it cannot bypass the policy.

An automated test enumerates every table in every exposed schema and fails if any table has row-level security disabled, or if any role holds a privilege outside an explicit allow-list.

The API verifies the user's token against Clerk's published keys, checking signature, issuer and expiry. It then runs that request's queries as that user, inside a transaction that sets the role and the token claims. Policies therefore apply to every read and write it makes. The exact integration with Supabase is confirmed against its documentation when the database phase begins.

The API never holds a Supabase service-level credential. That credential bypasses row-level policies, so holding it in a running application would make authorization depend on application code again. The migration runner is the only process with elevated database access, and its credential is never present in the running application's environment.

The membership sync writes through a narrow database role that can touch only the membership table.

The API holds three secrets of its own. The first is the Clerk webhook signing secret, which verifies that membership events came from Clerk and grants no data access. The second is the key that signs agent tokens, which lets the API prove that a token was issued by the API and names an analysis the person may read. The third is the Clerk Backend API secret, used only to create an invitation with a return URL, to change a member's role, to remove a member, and to delete an organisation. Each of these is checked by the API first, and the identity provider is called only after the check passes.

All database connections come from one connection factory. A check fails if any other code opens a connection.

## Environment

Configuration is defined by the environment template in the project. Its rules:

- The frontend reads only variables with the public prefix, and only public values use it. A secret never carries that prefix.
- Each service reads only its own section.
- The migration credential is never loaded by the running application.
- Every variable is documented where it is defined.

## Fixed decisions

These are settled. An agent working on the project may propose a change in writing and must not make it.

- The authentication provider, the policy on any table, the grants on any role, the membership sync, and the rule that the API holds no Supabase service-level credential.
- The two identity-provider roles, admin and member, and the rule that only the owner promotes or demotes. Role changes and member removals go through the backend. The accepted browser-delete risk for admins is recorded in the design and is not to be removed without a new decision.
- The signing key for agent tokens, its lifetime, and the rule that the agent holds no signing key.
- The edge rule and resolver semantics, per language, including which references are reported as unresolved.
- The four framework adapters in version 1, and the exactness rule each one follows.
- The TypeScript resolver as the authority for TypeScript and JavaScript resolution, and its pinned version.
- Adding, removing or upgrading a dependency. This is enforced through the agent tool's permission settings, not only by instruction.
- Environment variable names, and which of them are secret.
- What the API exposes: its routes, the fields it returns and what each route may do. The three dashboard read routes are fixed: `GET /v1/projects` returns the organisation's projects with each project's latest analysis state and creation time; `GET /v1/projects/{project_id}` returns one project and its analyses newest first; `GET /v1/analyses/{analysis_id}` returns one analysis with its project name. Each returns not-found identically for an unreadable and an unknown identifier.
- The checks. A check is never disabled, skipped or loosened to make a change pass. A check that cannot run fails loudly.
- The connection factory and the model-client module. No other code opens database connections or calls a model.
- The accessibility standard, the rule that colour is never the only signal, and the palette's colour-vision requirements.
- The rule that a run's status can be changed only by the run that owns it.

## Open items, to decide at their phase

- The UI component kit, chosen in the frontend phase.
- The retention period for stored analyses and traces.
- The default build context for Go and the default import root for Python, confirmed against real repositories.
- The exact folding threshold, tuned against real repositories.

## What has to be true before this ships

These are checked by hand or by script, never assumed.

- On a known repository, five files checked by hand match what the parser reports as their imports, in each language the repository uses.
- Coverage states what was skipped and why, and its numbers are believable. A graph that is nearly empty while coverage reads complete fails this check.
- A user in one organisation cannot read or write rows belonging to another. This is verified by querying as that user, not by reading the code.
- A user removed from an organisation loses access on their next request, verified by a test that removes a member and makes a request.
- Every table in the schema has row-level security enabled, and the automated test covers every exposed table.
- No service in the system holds a Supabase service-level credential, verified by a check on its environment and code.
- A tampered, expired or foreign agent token reads nothing.
- A slow run's failure cannot overwrite a newer run's status, verified by a test that runs both.
- An analysis from an earlier parser version is marked stale.
- The invented-path check rejects a path that matches only the tail of a real one, and a path hidden behind formatting.
- An explanation never names a file absent from the repository.
- Each framework adapter's fixtures show a literal route as present and a composed route as absent, with the reason in the coverage report.
- The chat panel shows its lookups before any answer.
- Every interactive element can be operated by keyboard, every screen passes the automated accessibility check, and the map is readable in greyscale.
- Parsing a large repository in the background does not block the interface.

## Where this is likely to go wrong

**Silent resolution failure.** A repository that uses barrel files, aliases or unusual layouts can lose most of its edges without any visible error. Unresolved counts are shown prominently, because a tidy picture that is quietly wrong is worse than an untidy one that admits its gaps.

**Folding large graphs.** The two-file threshold works on typical repositories and will be wrong on some. Expect to tune it.

**Measuring AI quality.** Reading a few outputs and judging them good is not measurement. Answer quality needs a number, and some parts of that number are judgments by a model. Those are reported as judgments.

**Repository text reaching the model as instructions.** Source files can contain text that tries to change what the agent does. The agent's access is set by a token the model cannot change, and its instructions say to ignore instructions found in repository content. Both rules must hold together.

**Traces holding repository content.** Observability is valuable, and it also copies code to a second place. Region and retention must be confirmed before tracing is enabled against real repositories.
