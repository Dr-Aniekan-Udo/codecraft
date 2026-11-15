# Phase 2 — Schema and dashboard

**Goal.** Each organisation sees only its own analyses, and the database proves it. Switching organisations changes what the same page shows, and nothing in the application decides who may read what.

This phase creates the data model and the dashboard that reads it. Nothing in this phase writes analyses. Those come with the pipeline.

## Build

- **Eight tables:** projects, analyses, files, edges, routes, explanations, file roles and insights. Each row carries the organisation it belongs to, and each table is readable only through its policy.
- **Organisation ownership.** Every row records the organisation it belongs to as a text identifier. Organisations live in the identity provider, so no table holds a foreign key to them. When an organisation is deleted in the identity provider, its rows are removed from all eight tables.
- **Row-level security on all eight tables**, with one select policy each. A row is visible only when the signed-in person has a membership row for that row's organisation.
- **The organisation's project table.** The organisation's root lists its projects as rows. Each row shows the project name, the state of its latest analysis, and when that analysis was created. An organisation with no projects sees an empty state.
- **Three routes, one shell.** `/` is the organisation's project table. `/projects/:projectId` lists that project's analyses, newest first, each with its state. `/projects/:projectId/analyses/:analysisId` shows that analysis in the workspace. The three columns stay the same on all three routes; only the centre changes. The address holds the place, so refresh and the back button return to it.
- **Switching organisations** changes the active organisation, and the same page then lists that organisation's analyses.
- **Sample analyses.** A script creates sample projects and analyses for two organisations, so the check can show that each organisation sees only its own. Every sample row is labelled as a sample.

## Constraints

- **Authorization is a property of the database, not of the application.** No table is readable without a policy on it. The dashboard does not filter by organisation in its own code. If a query returns another organisation's row, the fault is the policy, not the page.
- **The policy checks membership for the row's organisation.** It does not trust the organisation named in the token alone. A person who is not a member of an organisation gets no rows from it, even if they ask for that organisation by its identifier.
- **Each table is created with its policy in the same migration.** A table without a policy returns nothing, which is visible. A table where row-level security was never enabled returns everything, silently. The second must never be possible, even briefly.
- **A link reveals nothing to a non-member.** Opening a project or analysis link in an organisation the person does not belong to shows the same not-found message as a project that does not exist. It never reveals that the project exists, its name, or its organisation.
- **Migrations contain no sample data.** The production project receives every migration. Sample rows are created by the script, which is run deliberately and is removed when the pipeline phase lands. Keeping data out of migrations means a migration can never put fake analyses in front of real organisations.
- **The API role has select access only** on these tables in this phase. Nothing in this phase writes to them, so the API role gets no insert, update or delete rights.
- **Every table in every exposed schema is covered by the row-level security test.** The test enumerates the tables, fails if any has row-level security disabled, and fails if any role holds a privilege outside the allow-list.
- **Deleting an organisation removes its rows in one database operation.** The identity provider's organisation-deleted event reaches the same endpoint that handles membership. After the signature is verified, one security-definer routine deletes every row carrying that organisation identifier from all eight tables in one transaction and returns how many rows it removed from each. It refuses a null or empty identifier, removes the organisation's membership rows too, and resolves every name it uses through a fixed path so it cannot be redirected to another object. It is owned by the migration role and is executable only by the membership sync role, never by the public, anonymous users or signed-in users. That role holds no select, insert, update or delete on the eight tables, and row-level security is not forced on their owner, so the routine removes rows the select policy hides from the caller. A test proves that.
- **The webhook verifies first, then dispatches.** Existing membership events keep their behaviour. An organisation-deleted event takes the organisation identifier from the deleted-object payload. An organisation-deleted event that matches no rows succeeds, and any event type the endpoint does not handle succeeds without doing work.
- **Lists are bounded.** A list returns at most 50 rows, ordered by creation time, newest first. Each query names its columns. The page does not poll.
- **Switching an organisation changes the data the page reads, not the query.** The same query runs for every organisation, with the organisation as a parameter. A separate query for each organisation would drift apart over time.

## Acceptance check

1. Switch to the first organisation. Its root lists its two projects, each with its latest state. Switch to the second. The list changes.
2. Open a project. Its analyses appear, newest first, each with its state. Open one. The workspace shows its details, and the three columns do not change.
3. Refresh on the analysis page. The same analysis is shown. The back button returns to the project, then to the table.
4. Paste the address of a project in an organisation you are not in. It shows not-found, as a project that does not exist would.
5. In the database dashboard, all eight tables show row-level security enabled, and each has one select policy.
6. Delete an organisation in the identity provider. Its rows are gone from all eight tables and from the membership table, and the other organisation's rows and membership rows remain.
7. The sample rows are labelled as samples, and no migration contains any data.

## Not in this phase

Analysing a repository, the analysis form, the pipeline, the parser, progress updates, writing analyses from the application, and the stale state. Organisation management beyond what already exists. The repository entry, the map, and resuming the last place within each organisation.
