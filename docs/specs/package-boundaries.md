# Package boundaries

**Status.** A standing specification. It is not a roadmap phase and has no phase number. It governs how the backend's packages depend on one another, where configuration is read, and where the command-line entry point lives. Every later phase must follow it. A change to it needs a written decision.

**Goal.** Keep each package independent of the others it does not need, so that the parser, the API, the command-line entry point and any future worker can change or run separately, and so that no process loads a secret it does not use.

## Packages

The backend is a workspace of packages under `backend/packages/`. Each has one responsibility.

- **codecraft_core.** The shared shape of data: the parser output model, and nothing else. It holds no logic that runs a parse, no configuration, and no network or database code.
- **codecraft_settings.** The base configuration: the parse limits and the location of the environment file. It is the only place that defines those variables. It depends only on the settings library.
- **codecraft_parsing.** Reads source and produces the core shape. It takes its limits as parameters. It reads no configuration, no database, and no network.
- **codecraft_storage.** The database access layer.
- **codecraft_api.** The web layer: requests, authentication, and the database. It holds the credentials for the database and the identity provider. It extends the base settings with them.
- **codecraft_app.** The command-line entry point. It is the only package allowed to use both the parser and the settings together. Nothing imports it.
- **codecraft_analysis** and **codecraft_explain.** Reserved for later phases. Neither may import any package other than the core until its own specification says otherwise.

## Allowed imports

Each arrow means "may import". Anything not listed is forbidden.

- codecraft_core: imports nothing internal.
- codecraft_settings: imports nothing internal.
- codecraft_parsing: may import codecraft_core. It may not import codecraft_settings, codecraft_api, codecraft_storage or codecraft_app.
- codecraft_storage: may import codecraft_core.
- codecraft_api: may import codecraft_core, codecraft_settings and codecraft_storage. It may not import codecraft_parsing or codecraft_app.
- codecraft_app: may import codecraft_core, codecraft_parsing and codecraft_settings. It may import codecraft_api only for its database and identity settings, and only if its specification says so. Nothing may import codecraft_app.

These rules are enforced by the import-linter contracts in the backend project file. A contract that cannot be satisfied is a stop, not an exception.

## Configuration

1. **Each process loads only the settings it uses.** The command-line entry point loads the base settings and nothing else. It must not load any database, identity or webhook credential.
2. **One definition per variable.** Each variable is defined in exactly one settings class. A change to a limit is made in one place.
3. **One environment file.** The file is `backend/.env`. Its location is computed from the settings module's own location, never from the working directory, so that a command run from any folder reads the same file.
4. **Required values fail at load.** A missing or invalid required value stops the process at load time, and the error names the variable.
5. **The parser takes its limits as parameters.** It never reads configuration itself.
6. **No value is printed.** Documentation and reports name variables, never their values.

## Commands

The command-line entry point lives in codecraft_app and runs as `python -m codecraft_app.parse`. The API package holds no command-line entry point.

## Constraints, with reasons

- **The parser never imports the API or the app.** A parser that depends on the web layer cannot run in a worker, and cannot be tested without it.
- **The API never imports the parser.** When the pipeline needs the parser, it calls it through a defined function in codecraft_app, or through a worker. A direct link would have to be undone later.
- **The command never loads a secret.** Its settings are the base class only. A bug in the command cannot expose a database or identity credential it never loaded.
- **The core stays free of configuration and logic.** Every other package depends on it, so any change to it reaches all of them.

## Acceptance check

1. From backend, every import-linter contract passes, including those named in this specification.
2. The command runs from the backend folder and from another folder, and reads the same environment file in both cases.
3. A missing parse limit stops the command at load time, and the error names the variable.
4. The command, run with only the base settings available, starts without any database or identity variable set.
5. The parser's output, for every Go and Python fixture and for each pinned repository, is unchanged by the move.

## Not in this specification

Which variables each phase needs, which is set in that phase's own specification. The design of the parse pipeline, which belongs to the pipeline phase. Any worker or queue, which belongs to the phase that introduces one.
