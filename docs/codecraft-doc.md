# CodeCraft: Design

The product decisions behind this build, written before it starts, with the reasoning attached. The reasoning matters more than the decision. You will hit forks this document doesn't cover, and you need to know which way the thinking was leaning.

Read the part you need before you build something. Don't read it all at once, and don't paste it into a prompt.

## What it is

Sign in, point CodeCraft at a repository, and get a map of it. The repository can be a public GitHub URL or a local directory. Each folder is a box, and each import is a line between files. Open a folder into its files. Select a file and see what it imports, what imports it, and what breaks two levels out if it changes. Ask for an explanation and get a paragraph written from that file and its real neighbours.

Then a panel where you can ask the repository a question and watch it look the answer up.

The codebase can be Python, Go, JavaScript or TypeScript, or a mix. Config and data files that carry real relationships to code are part of the map too: JSON, YAML, TOML, SQL and Dockerfiles.

## The problem

Codebases now routinely contain code nobody on the team has read. An agent wrote it, someone confirmed it worked, it shipped. That is a reasonable way to work and it is not going to stop, but it accumulates structure nobody chose. Files that import through three layers of re-exports. A utility forty files depend on. A module nothing has referenced in months.

The questions that follow are structural. What is this file, what depends on it, what breaks if it changes. Answering them today means reading imports one file at a time and holding the results in working memory. That stops working at around thirty files, and it stops being attempted at all somewhere past a hundred.

## Who it's for

A developer opening a codebase they didn't write. Most often it's one they built themselves with an agent, across many sessions, and can no longer hold in their head.

They can read code fine. What they can't see is its shape.

And increasingly that isn't one person's problem. A team of four all shipping this way inherits four sets of code nobody read, and the person who joins next inherits all of it at once. So an analysis belongs to an organization rather than to whoever happened to run it. A repository is mapped once, and everyone after that starts from the map.

This description is the test every feature gets measured against. When something tempting comes up, such as a quality score, a rating or a review panel, the question is whether the person described here wants it. Usually they don't. They want to know what depends on this file.

## Why this hasn't stuck before

Codebase visualisation is not a new idea, and the track record is poor. CodeSee built something close to this with real funding and is gone. Sourcetrail ran for years as a desktop tool and was archived. Any plan here has to account for that rather than assume it away.

The most likely explanation is that both were selling a map of a codebase the user had already read. A map you could have drawn yourself is a nice-to-have, and nice-to-haves lose. What changed is that people now ship code they have never read. That turns the same artifact into something needed on a specific afternoon, for a specific reason.

The current generation of AI tools mostly works the other way round. They hand the repository to a model and let it describe the structure. That is much faster to build, which is why there are many of them, and it is the approach this product is deliberately not taking. The next section explains why.

That's the bet. It is a bet, and it should be stated as one.

## The rule everything rests on

**Every box and every line comes from really parsing the code.**

The AI may explain and label. It may never decide that two files are connected, and it may never walk the graph when arithmetic can do it instead.

The reason is bluntly stated: a dependency graph that is ninety percent right is worse than no graph, because there is no way to tell which ten percent is wrong. The moment a model is allowed to guess at an edge, every edge becomes a maybe, and the product is a nice-looking picture.

Pressure to break this comes from two directions. "AI code analysis" pulls toward letting the model reason about structure. Anything calling itself a code tool drifts toward becoming a code reviewer. Both are refused.

An edge exists only when a reference resolves to a real file or a real table in the input. A reference that cannot be resolved is recorded with its reason and never guessed into an edge. Config and data files follow the same rule: a literal path or table name that exists is an edge, and a name that merely looks similar is not.

## Scope

- Sign-in with GitHub, Google or email, for identity only. No repository scope, no stored user token, public repositories only.
- Organizations. Every analysis belongs to one, people are invited into one, and what you can see follows from which one you are in. Default roles only.
- Parsing every file. Imports, re-exports and dynamic imports become edges. `require()` counts as well, because a large amount of real code still uses it.
- Fan-in and fan-out per file.
- The map: folders folding into boxes, expanding into files, selection, highlighting, and a detail panel.
- Blast radius and dependency chain, as arithmetic over the edge list.
- Explaining a file, with a cache that isn't optional.
- Labelling files that convention couldn't identify, rather than guessing what they are.
- Coverage reporting: how much of the repository was parsed, and why the rest wasn't.
- Live progress during parsing, because parsing a real repository is not instant.
- A chat panel answered by an agent that looks facts up rather than recalling them.
- A check on whether the AI ever names a file that doesn't exist.
- External dependencies, meaning packages installed from outside the repository. They are counted and listed, but they are not drawn as boxes, because the map is about this repository.

## Language-specific behaviour

Each language has rules that determine which references count, and those rules are where edges are most often lost or invented. The defined set of forms is what keeps each resolver honest.

**Python.** Relative imports resolve against the package structure. Re-exports through an `__init__` file are followed, and `__all__` is respected. Conditional imports inside `try` blocks count as edges, marked as conditional. `importlib` calls count only when the module name is a string literal. Anything computed at runtime is unresolved. Packages without an `__init__` file are followed by their directory structure, and the coverage report says so.

**Go.** The module path comes from the module file, and an import is a package path rather than a file. Edges go to a package, which maps to the files in that directory. Imports of packages outside the module are external. The vendor directory is treated as external. Build tags are read, and files excluded by a tag are shown as excluded, not as absent.

**JavaScript and TypeScript.** Path aliases from the compiler configuration are resolved, along with extensions, index files, and the package manifest's entry points. Barrel files, meaning files that re-export others, are followed, because a repository built on them loses most of its edges otherwise. `require()` and dynamic `import()` count when the path is a literal. JSX and TSX are parsed as their own grammars.

**Config and data files.** JSON, YAML and TOML count as edges only when a value is a path or a name that resolves to something in the input. A CI workflow that names a script, a compose file that names a build directory, and a project file that names a package all qualify. SQL counts a table reference only when the table is created in the input. A Dockerfile counts a copy or add only when the source path exists.

## Out of scope, and why

Each of these is something a model will propose, because each sounds like an improvement. The reason matters more than the refusal.

- **Scores, grades, severity badges, "three issues found".** This product explains a codebase. It does not review one. Once there is a number, people argue with the number instead of reading the map.
- **Letting the agent traverse the graph itself.** The agent picks a starting point and a direction. The same arithmetic that draws the canvas does the walk. If the model does the walking, invented structure comes straight back in.
- **Private repositories.** This requires a token that would then have to be stored. Not in this version.
- **Approximate routes.** If a route's method and full path cannot both be recovered from the syntax, show nothing. A wrong route is the same failure as an invented edge.
- **Queues, containers and workers.** One deployable application. If a repository is too large to parse within a request, that is a limit to state honestly, not an architecture to build around.
- **Cross-language edges.** A TypeScript call matching a Python route is heuristic. It is the first place a guessed edge would appear, so it is not drawn.
- **Resolving third-party code.** Packages in dependency folders, the Go module cache and Python site-packages are external. Analysing them would multiply the map by an order of magnitude and mix someone else's structure into this one.
- **Languages beyond these four and the listed config formats.** Not because they are hard, but because getting these right is the entire proposition.

## How it works

No folder names here. The structure is yours to choose. These are constraints on behaviour.

**The parser is standalone.** It takes a directory path and returns files, edges, unresolved references and a coverage report. It does not know the web framework exists, does not know the database exists, and runs from a plain script with nothing else running. If it can't run standalone, the layering is wrong.

**Every language has its own parser, and every parser emits the same representation.** The representation holds the files, the symbols, the edges (each with a kind and a source location) and the unresolved references (each with a reason). Storage, graph calculations, the API and the explanation layer work only on that representation and never learn which language produced an edge. Supporting a new language means writing one parser. Nothing else changes.

**Framework knowledge is an adapter, not a branch.** The first version ships with no framework adapters. Knowing that a file in a particular position is a Next.js page belongs in an adapter, and the adapter interface exists now so that the first framework can be added without touching the parser. An `if (framework === ...)` inside parsing code means the boundary has failed.

**Graph calculations are pure functions** over a list of files and a list of edges. No data fetching inside them, and nothing to mock in order to check them.

**Identity comes from Clerk, and access comes from the database.** Clerk decides who a person is and manages organizations, invitations and roles. Supabase Postgres decides what that person may read. The application never decides access on its own.

**Revocation is the point that must be right.** An organization claim carried inside a signed token goes stale. Removing someone would take effect only when their token refreshed, which is a security property that depends on a refresh cycle nobody controls. So membership is mirrored into the database. Clerk's organization events arrive by webhook, and the API writes them into a membership table. Row-level policies check that table on every query, not the token. Removal takes effect as soon as the webhook is processed.

**Row-level security is on by default, not per table.** The two failure modes are not symmetrical. A table with security enabled and no policy yet returns nothing, which is visible. A table where someone forgot to enable it returns everything, silently. The second must be impossible rather than unlikely. An automated test enumerates every table and fails if any has security disabled.

**Every AI call is traced and cached**, with the cache read inside the traced function, so a cache hit appears as a recorded run containing no model call. That is what makes the cache verifiable rather than assumed.

**The model client is configured by protocol, not provider.** Many providers and local servers speak one of two wire protocols, so configuration names the protocol, the endpoint and the model. The client module is the only code that calls a model, and nothing is defaulted in code.

## The interface

A dense developer tool, not a dashboard. Small type, tight spacing, and monospace for anything that is a file path. Someone using this is scanning a lot of names at once, and the layout should assume that rather than fight it.

Dense does not mean inaccessible. The interface meets WCAG 2.2 AA, the current web accessibility standard. This is part of every phase's acceptance, not a later pass.

**Colour is never the only signal.** Every meaning that colour carries also has a shape or a text cue. Incoming edges are solid, with the arrowhead at the file. Outgoing edges are dashed, with the arrowhead at the target. The detail panel names each edge as incoming or outgoing. The map stays readable in greyscale, in print, and for colour-blind users.

**The palette uses the Okabe-Ito set,** which is designed to stay distinguishable under the common forms of colour-vision deficiency. Incoming is blue (#0072B2 in light mode, a lighter tint in dark mode). Outgoing is vermillion (#D55E00 in light mode, #E69F00 in dark mode). Blue and vermillion are the most reliable pair across deuteranopia, protanopia and tritanopia. Green and amber are not: for red-green colour blindness they collapse into nearly identical tones, so they are not used.

**Selection is not a hue.** The selected item gets a two-pixel outline in the primary text colour, plus a tinted fill. The accent is not one of the edge colours, so selecting something can never be mistaken for a direction.

**Kind is shown by label and icon.** Each file kind has a text label and a glyph. Colour may reinforce a kind, but never carries it alone, and kind colours never reuse the two edge colours.

**Contrast.** Text meets 4.5:1 against its surface. Graphics that carry meaning, including edges, node borders, the selection outline and the focus ring, meet 3:1. Light and dark palettes are verified separately, and the exact values are confirmed by an automated contrast check rather than by eye.

**Keyboard and screen readers.** Every action in the map can be done from the keyboard: moving between files, selecting, expanding a folder, and opening the detail panel. Focus is always visible. Each file and edge has a text label that a screen reader announces. The map is never the only way to reach information. The same data is available as a list.

**Size and zoom.** Type stays readable at 200% browser zoom, without horizontal scrolling of the main content. Interactive targets are at least 24 by 24 CSS pixels.

**Themes.** Three states: follow the system, force light, or force dark. The choice survives a reload. Both palettes are complete and verified separately.

**Nothing moves on its own.** Motion happens because something was clicked. No ambient animation, no pulsing, no drifting graph. Any transition added later respects the system's reduced-motion setting.

**Anything derivable from the edge list is instant.** If an answer is arithmetic over data the browser already holds, it appears immediately, with no spinner and no network request. A spinner in front of a calculation teaches people to distrust the fast paths, and most of the interface is fast paths.

**The shell is built once.** Where the panels sit, and what each one is for, is settled in an early phase. Later phases add to those panels and do not rearrange them. Specific placement lives in the phase specs.

**Coverage is visible, not buried.** Parsed, skipped and unresolved counts sit where the person looks first. A map that hides its gaps is the failure this product exists to prevent.

## Architecture

The parts are: acquisition (turns a URL or path into files), parsing (one component per language), resolution (turns references into edges or unresolved records), analysis (pure calculations), storage (persists analyses and enforces who may read them), the API (the interface for the frontend and any other client), and explanation (the AI layer, which reads only from the representation).

The parts talk only through the representation or a versioned API contract. Nothing reaches into another part's internals. Any part can become its own service later without its contract changing. Splitting now would add network failure modes with no present benefit, so it is not done now.

Parsing runs in a process pool on standard Python 3.14. Each worker receives a file and returns an immutable result. A single coordinator writes to storage. Workers share no mutable state, so a race condition in one cannot corrupt another's work.

Free-threaded Python is not used. Its main benefit is threads sharing one process's memory, which this design deliberately avoids. The tree-sitter grammar packages also publish only stable-ABI wheels, which do not install on the free-threaded interpreter. The choice is revisited when those packages publish free-threaded wheels and a benchmark on target hardware shows a clear gain.

The web layer is asynchronous, and parsing never runs inside a request. Progress streams to the client with Server-Sent Events, which is simpler than polling and fits a one-way stream.

Parsing is bounded by explicit limits on file count and file size. A repository over a limit fails with a stated reason rather than hanging or exhausting memory.

## Frontend

React with a Vite single-page application, talking to the Python API.

The deciding requirement is interaction latency. Selecting, expanding and highlighting must respond immediately, and the graph canvas runs in the browser regardless. React has the deepest set of graph-canvas and layout libraries with first-class integration, and this is a dense tool with many panels whose state has to be managed carefully. Vite is used because the server is Python, so a server-rendering framework would add a second server with no purpose.

The cost is two languages. It is contained by generating TypeScript types from the API's schema, so every data shape is defined once, in the Python models.

Graph arithmetic lives in TypeScript and nowhere else. The browser receives the edge list once per analysis and computes fan-in, fan-out, blast radius and chains with pure functions. Python does not repeat that arithmetic.

## Database

Postgres on Supabase, with access control enforced in the database.

Postgres is used because the requirements are Postgres features: organizations, shared analyses and per-row access rules. A single-file database has no policy layer, so its authorization would sit in application code, and the rule that the database decides who may read a row would no longer hold.

Row-level security is enabled on every table, with explicit policies. Column privileges hide internal fields from the API role. No view exposes rows without a policy. Application code cannot widen access, because it cannot bypass the policy.

The API verifies the user's token against Clerk's published keys, checking signature, issuer and expiry. It then runs that request's queries as that user, inside a transaction that sets the role and the token claims. Policies therefore apply to every read and write it makes. Supabase's third-party auth integration with Clerk makes the user's identity available to the policies. The exact setup is confirmed against Supabase's documentation when the database phase begins.

The API never holds a Supabase service-level credential. That credential bypasses row-level policies, so holding it in a running application would make authorization depend on application code again. The migration runner is the only process with elevated database access, and its credential is never present in the running application's environment.

The membership sync writes through a narrow database role that can touch only the membership table. It is not the application role and not the service credential.

The API holds one Clerk secret: the webhook signing secret. It verifies that membership events really came from Clerk and grants no data access.

All database connections come from one connection factory. A check fails if any other code opens a connection. The rule holds because the only way to get a connection is through the factory, not because each change remembers it.

## Explanation and the agent

The agent is a typed, Python-native framework, such as Pydantic AI. Graph lookups are exposed to the model as tools, each returning data from the analysis. The model cannot construct an edge. Every answer is built from tool results, and the trace records each lookup.

A chat answer shows its lookups before the answer itself. An answer that arrives with no lookups behind it is the exact failure this product exists to prevent, so it counts as a failure. An automated check confirms that every explanation names only files present in the input.

## Observability

Instrumentation uses OpenTelemetry, which is vendor-neutral, so the tracing backend is chosen by configuration and can change without touching code. Every model call is traced, and the cache lookup happens inside the trace.

## Environment

Configuration is defined by the environment template in the project, with these rules:

- The frontend reads only variables with the public prefix, and only public values use it. A secret never carries that prefix.
- The API process reads only its own section.
- The migration credential is never loaded by the running application.
- Every variable is documented where it is defined.

## Fixed decisions

These are settled. An agent working on the project may propose a change in writing and must not make it.

- The authentication provider, the policy on any table, the grants on any role, and the rule that the API holds no Supabase service-level credential.
- The membership sync, including the narrow role that writes it, and the rule that membership is read from the table, never from token claims.
- Adding, removing or upgrading a dependency. This is enforced through the agent tool's permission settings, not only by instruction.
- The edge rule and resolver semantics: what counts as an edge and what is reported as unresolved, per language.
- Environment variable names, and which of them are secret.
- The accessibility standard (WCAG 2.2 AA), the rule that colour is never the only signal, and the palette's colour-vision requirements.
- What the API exposes: its routes, the fields it returns, and what each route may do.
- The checks. A check is never disabled, skipped or loosened to make a change pass. A check that cannot run fails loudly.
- The connection factory and the model-client module. No other code opens database connections or calls a model.

## Open items, to decide at their phase

- The UI component kit, chosen in the frontend phase.
- The tracing backend, chosen by configuration when observability is built.
- The retention policy for stored analyses.
- Which framework adapter, if any, comes first.

## What has to be true before this ships

These are checked by hand or by script, never assumed.

- Pointed at a known repository, five files checked by hand match what the parser claims they import, in each language the repository uses.
- Coverage states what was skipped and why, and the numbers are believable.
- Signed in from a different organization, the first organization's rows do not come back from the query at all. This is verified by querying as that user, not by reading the code.
- A user removed from an organization loses access on their next request. This is verified by a test that removes a member and makes a request.
- Every table in the schema has row-level security enabled, and the automated test covers every exposed table.
- The API process contains no Supabase service-level credential, verified by a check on its environment and code.
- An explanation never names a file absent from the repository, and that is demonstrated by a check rather than asserted.
- The chat panel shows what it looked up before it answers.
- Automated accessibility checks report no serious or critical violations on every screen.
- The contrast check passes for both palettes, for text and for meaningful graphics.
- The core flow, from opening a repository to reading an explanation, can be completed by keyboard alone, with focus visible throughout.
- The map is reviewed under colour-vision simulation, and a greyscale capture still shows direction and selection without colour.
- Parsing a large repository in the background does not block the interface.

## Where this is likely to go wrong

**Folding folders into readable boxes.** A large repository has to collapse into something legible, and the threshold has to be solved for rather than guessed. Expect at least one wrong answer here before a right one.

**Import resolution.** Path aliases, index files, re-exports, barrels. The risk isn't failure. It's silent failure. A repository built on barrel files loses most of its edges and still renders a clean, confident, wrong picture. This is the one place where loud reporting wins over a tidy interface.

**Measuring whether the AI output is any good.** Reading a few outputs and judging them fine is not measurement. The requirement is that answer quality becomes a number. The method for producing that number is genuinely open, and it is the least settled part of this plan.