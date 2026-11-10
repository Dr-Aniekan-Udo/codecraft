# AGENTS.md

## What this project is

CodeCraft maps how a codebase depends on itself. It parses real source in TypeScript, JavaScript, Python and Go, plus the config and data files that relate to code (JSON, YAML, TOML, SQL, Dockerfiles). It shows the dependency graph, blast radius and explanations grounded in that graph, and it answers questions through an agent that looks facts up.

The full design is in the docs directory. Read only the section you need for the task in front of you. Do not try to read all of it.

## Hard rules

These come first and apply to every change. If a task would break one, stop and ask.

1. An edge exists only when a reference resolves to a real file or table in the input. Never create, infer or guess an edge. Unresolved references are recorded with a reason.
2. Never invent something to fill a gap. Absent is better than approximate. A route is shown only when its method and full path are both exact.
3. The AI explains and labels. It never decides what is connected and never computes graph structure.
4. Graph arithmetic (fan-in, fan-out, blast radius, chains) lives in the frontend TypeScript. Do not add it to the backend or the agent.
5. The following are fixed decisions. Propose changes in writing; do not make them: the authentication provider; any table's policies; any role's grants; the membership sync; the rule that the API holds no Supabase service-level credential; the agent token design; the edge rules per language; the TypeScript resolver as the authority for its languages; environment variable names and which are secret; the API's routes and returned fields; the checks.
6. Do not add, remove or upgrade any dependency. Name the package, say what it is for, and wait for approval.
7. Do not build ahead of the current phase. No scaffolding, stubs or placeholders for later phases.
8. Never disable, skip, loosen or weaken a check to make something pass. If a check cannot run, say so and stop.
9. Never open, print or write a real `.env` file. Use the example template. Secrets never carry the frontend's public prefix. Never print secret values.
10. Database connections come only from the connection factory. Model calls happen only in the model-client module. Do not create connections or call a model anywhere else.
11. Never write code that gives the agent a database credential, a signing key, or access to an analysis other than the one named in its token.
12. No scores, grades, severity levels or "issues found" anywhere. This tool explains a codebase; it does not review one.
13. Do not leave the build broken. If you cannot fix a failure, stop and report it.
14. Never commit, push, open a pull request, or start a new phase on your own initiative. When a phase passes its checks, report the result and wait. Commit, push and open pull requests only when the user asks. Never commit secrets.
15. Review findings from any tool are inputs, not orders. Verify each one against the code before changing anything. Apply the fix if the finding is correct for this project. If it is not, reject it and say why in one sentence.

## Stack

- Backend: Python 3.14, managed with uv as a workspace of packages. FastAPI, Pydantic v2, Postgres through Supabase with row-level security, tree-sitter for parsing, OpenTelemetry for tracing.
- TypeScript resolver: a small Node program using the TypeScript compiler, with a pinned version. It is called by the Python parser through a versioned contract.
- Agent: a Python service, separate from the API. It calls the API's read-only endpoints using tokens the API issues.
- Frontend: React with Vite, TypeScript in strict mode, pnpm.
- Checks: ruff, pyright in strict mode, pytest, import-linter (backend); the TypeScript compiler, eslint, vitest (frontend and resolver).

Library behaviour changes between versions. Before using an API, read the documentation shipped with the installed version, or the lockfile, rather than relying on memory.

## Backend structure

The backend is split by responsibility, one package per responsibility. The core package defines the shared intermediate representation and imports nothing internal. Parsing and analysis must not import the API, storage or explanation packages. import-linter enforces these boundaries, and a failing boundary check is a real failure.

## Commands

Run these from the stated directory. Use uv for all Python work and pnpm for all JavaScript work. Never run pip, npm or yarn, and never create a second lockfile.

Backend, from the backend root:
- `uv sync --all-packages` installs everything.
- `uv run ruff check .` and `uv run ruff format --check .` for lint and format.
- `uv run pyright` for types.
- `uv run pytest` for tests.
- `uv run lint-imports` for package boundaries.

Frontend, from the frontend root:
- `pnpm install` installs everything.
- `pnpm lint`, `pnpm typecheck`, `pnpm test`, `pnpm build`.

A phase is done only when every check in the directories it touches passes. Any command a phase adds is listed in that phase's spec.

## How we work

- Work one phase at a time. Each phase has a spec in the docs directory. If the spec for the task does not exist, stop and ask for it.
- At the start of a session, read this file and the spec for the phase. Then look at the recent commit history. Before building, tell me in a few sentences what you understood the current state to be.
- When a spec is ambiguous, say so before building. Give your recommended reading and the reason.
- Some checks are mine to run: anything needing a browser, a live GitHub connection, a real Supabase project, or a real tracing backend. When the code is ready for those, say so and state exactly what I should check.
- When a phase passes its checks, report what it does and what I should check. Then wait. I decide whether to commit, when to open a pull request, and when to start the next phase.

## Subagents

- Every subagent works only inside this repository. Do not read, write or request access to parent, sibling or other external directories. If a task appears to need one, stop and ask.

## Asking questions

Ask one question at a time. Give two or three labelled options, mark the one you recommend, and give the reason in one sentence. For example: "A) keep the current approach, B) switch to X. I recommend A because it keeps the boundary check passing without an exception." Never pick a direction silently and never build both.

## Communication

Be brief. Do not restate the plan back to me. When a phase is done, say what it does and what the check should show, in a few lines. When something fails, say so plainly and say what you tried. Do not work around a failure quietly. Use plain English; if one sentence is enough, do not write three.

## Conventions

- Strict typing. Do not use `Any`. If a type is genuinely awkward, say so rather than casting.
- Comments explain why a decision was made, not what the code does.
- Database access happens in server code only, never inside interface components.
- Name columns explicitly. Limit list reads. Do not poll the database in a loop.
- Use one obvious way to do each thing. Do not add configuration options nobody asked for.
- Accessibility is WCAG 2.2 AA, and every screen must pass the automated accessibility check. Colour is never the only signal: every meaning carried by colour also has a shape, a dash pattern, or a text label. Use only the palette values defined in the design document, and do not add colours.
- Every interactive element is reachable and operable by keyboard, with a visible focus indicator. Every file and edge has a text label for screen readers.
- The interface is a dense developer tool: small type, tight spacing, monospace for file paths. Nothing moves unless the person clicked it.
- Do not add new interface components, routes or endpoints beyond what the current phase spec names.
