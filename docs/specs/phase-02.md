# Phase 2 — Schema and dashboard

**Goal.** Each team sees only its own analyses, and the database proves it. Switching teams changes what the same page shows, and nothing in the application decides who may read what.

This phase creates the data model and the dashboard that reads it. Nothing in this phase writes analyses. Those come with the pipeline.

## Build

- **Eight tables:** projects, analyses, files, edges, routes, explanations, file roles and insights. Each row carries the team it belongs to, and each table is readable only through its policy.
- **Team ownership.** Every row records the team it belongs to as a text identifier. Teams live in the identity provider, so no table holds a foreign key to them. When a team is deleted in the identity provider, its rows are removed from all eight tables.
- **Row-level security on all eight tables**, with one select policy each. A row is visible only when the signed-in person has a membership row for that row's team.
- **The dashboard.** It lists the analyses belonging to the active team, with the name of each analysis's project and the state it is in: queued, running, complete or failed. A team with no analyses sees an empty state.
- **Switching teams** changes the active team, and the same page then lists that team's analyses.
- **Sample analyses.** A script creates sample projects and analyses for two teams, so the check can show that each team sees only its own. Every sample row is labelled as a sample.

## Constraints

- **Authorization is a property of the database, not of the application.** No table is readable without a policy on it. The dashboard does not filter by team in its own code. If a query returns another team's row, the fault is the policy, not the page.
- **The policy checks membership for the row's team.** It does not trust the team named in the token alone. A person who is not a member of a team gets no rows from it, even if they ask for that team by its identifier.
- **Each table is created with its policy in the same migration.** A table without a policy returns nothing, which is visible. A table where row-level security was never enabled returns everything, silently. The second must never be possible, even briefly.
- **Migrations contain no sample data.** The production project receives every migration. Sample rows are created by the script, which is run deliberately and is removed when the pipeline phase lands. Keeping data out of migrations means a migration can never put fake analyses in front of real teams.
- **The API role has select access only** on these tables in this phase. Nothing in this phase writes to them, so the API role gets no insert, update or delete rights.
- **Every table in every exposed schema is covered by the row-level security test.** The test enumerates the tables, fails if any has row-level security disabled, and fails if any role holds a privilege outside the allow-list.
- **Deleting a team removes its rows in one database operation.** The identity provider's team-deleted event reaches the same endpoint that handles membership. After the signature is verified, one security-definer routine deletes every row carrying that team identifier from all eight tables in one transaction and returns how many rows it removed from each. It refuses a null or empty identifier, leaves membership rows untouched, and resolves every name it uses through a fixed path so it cannot be redirected to another object. It is owned by the migration role and is executable only by the membership sync role, never by the public, anonymous users or signed-in users. That role holds no select, insert, update or delete on the eight tables, and row-level security is not forced on their owner, so the routine removes rows the select policy hides from the caller. A test proves that.
- **The webhook verifies first, then dispatches.** Existing membership events keep their behaviour. A team-deleted event takes the team identifier from the deleted-object payload. A team-deleted event that matches no rows succeeds, and any event type the endpoint does not handle succeeds without doing work.
- **Lists are bounded.** A list returns at most 50 rows, ordered by creation time, newest first. Each query names its columns. The page does not poll.
- **Switching a team changes the data the page reads, not the query.** The same query runs for every team, with the team as a parameter. A separate query for each team would drift apart over time.

## Acceptance check

1. With sample analyses for two teams, sign in as a member of the first team. The dashboard lists only the first team's analyses. Switch to the second team. The list changes to that team's analyses, and the network tab shows no request to any other table.
2. Switch to a team with no analyses. The empty state appears.
3. Each analysis shows its project's name and one of the four states: queued, running, complete or failed.
4. In the database dashboard, all eight tables show row-level security enabled, and each has one select policy.
5. Delete a team in the identity provider. Its rows are gone from all eight tables, and the other team's rows and the membership rows remain.
6. The sample rows are labelled as samples, and no migration contains any data.

## Not in this phase

Analysing a repository, the analysis form, the pipeline, the parser, progress updates, writing analyses from the application, and the stale state. Team management beyond what already exists.
