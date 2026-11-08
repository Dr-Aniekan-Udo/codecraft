# CodeCraft: Design

CodeCraft maps how a codebase depends on itself. Given a public GitHub repository or a local directory, it shows what each file imports, what imports it, and what would break two levels out if it changed. It explains a file from its real neighbours, and it answers questions about the repository by looking facts up, not by recalling them.

Every decision below is made on the merits of the problem: correctness, security, operational simplicity, and a structure that can later be split into services without a rewrite.

## What it covers

**Code:** Python, Go, JavaScript and TypeScript, including JSX, TSX and module variants.

**Config and data files that carry real relationships to code:** JSON, YAML, TOML, SQL and Dockerfiles. A JSON file can point at a path, a SQL file can reference a table, a Dockerfile can copy a directory.

**Excluded:** plain text, Markdown and other prose. They rarely have a provable relationship to code.

**Inputs:** public GitHub URLs and local directory paths. Both produce the same set of files, and the analyzer does not care where they came from.

## Core rule

Every node and every edge comes from parsing real source. An edge exists only when a reference resolves to a real file or a real table in the input. A reference that cannot be resolved is recorded with its reason and is never guessed into an edge. Config and data files follow the same rule: a literal path or table name that exists is an edge, and a name that merely looks similar is not. Edges are drawn only between files in the same language. Cross-language links, such as a TypeScript call matching a Python route, are not drawn, because matching them is heuristic.

The AI explains and labels what the parser found. It never decides what is connected, and it never walks the graph when arithmetic can do it.

## Architecture

Each language has its own parser, and every parser emits the same intermediate representation: the files, the symbols, the edges (each with a kind and a source location), and the unresolved references (each with a reason). Everything downstream works only on that representation. Storage, graph calculations, the API and the explanation layer never learn which language produced an edge. Supporting a new language means writing one parser that emits the same representation.

The system has these parts:

- **Acquisition:** turns a URL or path into a set of files.
- **Parsing:** one component per language, plus handling for config and data files.
- **Resolution:** turns raw references into edges or unresolved records, using each language's own rules.
- **Analysis:** pure calculations over the representation, such as fan-in, fan-out, blast radius and chains.
- **Storage:** persists analyses and enforces who may read them.
- **API:** the interface used by the frontend and by any other client.
- **Explanation:** the AI layer, which reads only from the representation and cites what it looked up.

Parts communicate only through the representation or a versioned API contract. Nothing reaches into another part's internals. Any part can therefore become its own service later without its contract changing.

## Frontend

React with a Vite single-page application, talking to the Python API.

The deciding requirement is interaction latency. Selecting, expanding and highlighting respond immediately, and anything derivable from the edge list is computed in the browser with no network round trip. The graph canvas is JavaScript work regardless of what surrounds it, so the canvas and its layout run in the browser. React has the deepest set of graph-canvas and layout libraries with first-class integration, and this is a dense tool with many panels whose state needs to be managed carefully. Vite is used because the server is Python, so a server-rendering framework would add a second server without serving any purpose here.

The cost is two languages. It is contained by generating TypeScript types from the API's schema, so every data shape is defined once, in the Python models.

Graph arithmetic lives in TypeScript and nowhere else. The browser receives the edge list once per analysis and computes fan-in, fan-out, blast radius and chains with pure functions. Python does not repeat that arithmetic.

The UI follows the rule that colour carries meaning or is absent. Incoming and outgoing edges have distinct colours, file kinds have a small palette, and everything else is greyscale. Nothing moves unless the person clicked it. Light and dark themes are both complete palettes, and the person's choice persists across reloads.

## Authentication

Supabase Auth. Organizations, memberships and invitations are tables in the same Postgres database.

The reason is revocation. When organization access is carried inside a signed token, removing someone takes effect only when their token refreshes, which is a security property that depends on a refresh cycle. When membership lives in the database, the row-level policy checks current membership on every query, so removal takes effect on the next request. Authorization data and the policy that reads it sit in one system, which is easier to reason about and to test.

Sign-in is offered through GitHub, Google and email, for identity only. The GitHub sign-in requests no repository scope, and no user token is stored.

Roles are owner, admin and member. Custom roles are not part of this version.

## Database

Postgres on Supabase. Access control is enforced in the database.

Postgres is used because the requirements (organizations, shared analyses, per-row access rules) are Postgres features. A single-file database has no policy layer, so its authorization would sit in application code, and the rule that the database decides who may read a row would no longer hold.

Row-level security is enabled on every table, and each table has explicit policies. Column privileges hide internal fields from the API role. No view exposes rows without a policy. Application code cannot widen access, because it cannot bypass the policy.

An automated test enumerates every table in every exposed schema and fails if any table has row-level security disabled, or if any role holds a privilege outside an explicit allow-list. The test runs locally and in CI. The reason for making it automatic is that the two failure modes are unequal. A table with security enabled and no policy returns nothing, which is visible. A table where security was never enabled returns everything, silently. The second must be impossible, not merely unlikely.

## Database access from the API

The API verifies the signed-in user's token, then runs that request's queries as that user, inside a transaction that sets the role and the token claims. Policies therefore apply to every read and write the API makes.

The API never holds a service-level credential. That credential bypasses row-level policies, so holding it in a running application would make authorization depend on application code again. The migration runner is the only process with elevated database access, and its credential is never present in the running application's environment.

All database connections come from one connection factory. A check fails if any other code opens a connection. The rule holds because the only way to get a connection is the factory, not because each change remembers it.

Tokens are verified against the provider's published public keys, checking signature, issuer and expiry. The API needs the project URL for this and no secret.

## Explanation and the agent

The agent is a typed, Python-native framework such as Pydantic AI. Graph lookups are exposed to the model as tools, each returning data from the analysis. The model cannot construct an edge. Every answer is built from tool results, and the trace records each lookup.

The model client is constructed in exactly one module, chosen by configuration. Calling a model from anywhere else fails a check, so changing provider is a configuration change in one place.

A chat answer shows its lookups before the answer itself. An answer with no lookups behind it is treated as a failure. An automated check confirms that every explanation names only files present in the input.

## Observability

Instrumentation uses OpenTelemetry, which is vendor-neutral. The tracing backend is selected by environment variables, so it can change without touching code. Every model call is traced, and the cache lookup happens inside the trace, so a cache hit appears as a recorded run that contains no model call. The cache is therefore verifiable rather than assumed.

## Parsing and concurrency

Parsing runs in a process pool on standard Python 3.14. Each worker receives a file and returns an immutable result. A single coordinator writes to storage. Workers share no mutable state, so a race condition cannot corrupt another worker's work.

Free-threaded Python is not used. The tree-sitter grammar packages publish only stable-ABI wheels, which do not install on the free-threaded interpreter. The choice is revisited when those packages publish free-threaded wheels and a benchmark on target hardware shows a clear gain.

The web layer is asynchronous, and parsing never runs inside a request. Progress is streamed to the client with Server-Sent Events, so the interface updates without polling.

Parsing is bounded by explicit limits on file count and file size. A repository over a limit fails with a stated reason rather than hanging or exhausting memory.

## Import resolution

Resolution is the highest-risk component, because its failures are silent. A resolver that is ninety percent right produces a map where nobody can tell which edges are wrong.

Each language's resolver supports a defined set of import forms. Anything outside that set is reported as unresolved, with its reason, and shown prominently. Unresolved references are never guessed.

Verification uses a reference implementation where one exists. For TypeScript and JavaScript, the TypeScript compiler runs as a development and CI oracle over fixture repositories, and its answers are compared with the resolver's. For Go, the toolchain's own package listing runs over fixture modules. Python resolution depends on the interpreter's search path at runtime and has no single authoritative oracle, so it is verified against hand-checked fixtures, and the defined set of supported forms is what keeps its guarantee honest. The oracles run only in development and CI, and the runtime has no dependency on Node or the Go toolchain.

## Deployment

One deployable application with internal boundaries that match the parts listed above. Each boundary communicates through the intermediate representation or a versioned contract, so any boundary can become a separate service later without changing its contract. Splitting now would add network failure modes without a present benefit.

## Environment

Configuration is defined by the environment template in the project. Its rules:

- The frontend reads only variables with the public prefix, and only public values use it. A secret never carries that prefix.
- The API process reads only its own section.
- The migration credential is never loaded by the running application.
- Every variable is documented where it is defined.

## Fixed decisions

These are settled. An agent working on the project may propose a change in writing and must not make it.

- The authentication provider, the policy on any table, the grants on any role, and the rule that the API holds no service-level credential.
- Adding, removing or upgrading a dependency. This is enforced through the agent tool's permission settings, not only by instruction.
- The edge rule and resolver semantics: what counts as an edge and what is reported as unresolved.
- Environment variable names, and which of them are secret.
- What the API exposes: its routes, the fields it returns, and what each route may do.
- The checks. A check is never disabled, skipped or loosened to make a change pass. A check that cannot run fails loudly.
- The connection factory and the model-client module. No other code opens database connections or calls a model.

## Open items, to decide at their phase

- The UI component kit, chosen in the frontend phase.
- The tracing backend, chosen by configuration when observability is built.
- The retention policy for stored analyses.

## Acceptance

Each of these is checked by hand or by a script, never assumed.

- On a known repository, five files checked by hand match what the resolver reports as their imports.
- Coverage states what was skipped and why, and its numbers are believable.
- A user in one organization cannot read or write rows belonging to another, verified by querying as that user.
- A user removed from an organization loses access on their next request, verified by a test.
- The row-level security test passes and covers every exposed table.
- The API process contains no service-level credential, verified by a check on its environment and code.
- An explanation never names a file absent from the input.
- The chat panel shows its lookups before any answer.
- Parsing a large repository in the background does not block the interface.

## Known risks

**Silent resolution failure.** Path aliases, index files, re-exports and barrel files lose edges without any visible error. Unresolved counts are shown prominently, because loud reporting is preferred over a tidy picture.

**Folding large graphs.** Collapsing a large repository into something readable needs a threshold that is tuned against real repositories, not guessed.

**Measuring AI quality.** Reading outputs and judging them good is not measurement. Answer quality needs a number, and the method for producing it is the least settled part of this design.
