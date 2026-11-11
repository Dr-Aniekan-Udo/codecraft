-- The eight tables that hold an analysis. Every table carries the team that owns
-- it, is readable only through its policy, and is created with row-level security
-- enabled in this same migration so no window exists where it returns everything.

create table public.projects (
  id uuid primary key default gen_random_uuid(),
  team_id text not null,
  name text not null,
  created_at timestamptz not null default now(),
  is_sample boolean not null default false,
  unique (id, team_id)
);

alter table public.projects enable row level security;

revoke all on table public.projects from anon, authenticated, service_role;
revoke all on table public.projects from public;
grant select on table public.projects to authenticated;

create policy "members read their team's projects"
  on public.projects
  for select
  to authenticated
  using (
    exists (
      select 1
      from public.membership as membership_row
      where membership_row.user_id = (select auth.jwt() ->> 'sub')
        and membership_row.team_id = projects.team_id
    )
  );

create index projects_team_created_idx on public.projects (team_id, created_at desc);

create table public.analyses (
  id uuid primary key default gen_random_uuid(),
  team_id text not null,
  project_id uuid not null,
  state text not null default 'queued',
  created_at timestamptz not null default now(),
  is_sample boolean not null default false,
  unique (id, team_id),
  constraint analyses_state_check
    check (state in ('queued', 'running', 'complete', 'failed')),
  constraint analyses_project_fk
    foreign key (project_id, team_id)
    references public.projects (id, team_id)
    on delete cascade
);

alter table public.analyses enable row level security;

revoke all on table public.analyses from anon, authenticated, service_role;
revoke all on table public.analyses from public;
grant select on table public.analyses to authenticated;

create policy "members read their team's analyses"
  on public.analyses
  for select
  to authenticated
  using (
    exists (
      select 1
      from public.membership as membership_row
      where membership_row.user_id = (select auth.jwt() ->> 'sub')
        and membership_row.team_id = analyses.team_id
    )
  );

-- The dashboard reads the newest analyses for one team.
create index analyses_team_created_idx on public.analyses (team_id, created_at desc);
create index analyses_project_idx on public.analyses (project_id);

create table public.files (
  id uuid primary key default gen_random_uuid(),
  team_id text not null,
  analysis_id uuid not null,
  path text not null,
  created_at timestamptz not null default now(),
  unique (id, team_id),
  constraint files_analysis_fk
    foreign key (analysis_id, team_id)
    references public.analyses (id, team_id)
    on delete cascade
);

alter table public.files enable row level security;

revoke all on table public.files from anon, authenticated, service_role;
revoke all on table public.files from public;
grant select on table public.files to authenticated;

create policy "members read their team's files"
  on public.files
  for select
  to authenticated
  using (
    exists (
      select 1
      from public.membership as membership_row
      where membership_row.user_id = (select auth.jwt() ->> 'sub')
        and membership_row.team_id = files.team_id
    )
  );

create index files_analysis_idx on public.files (analysis_id);

create table public.edges (
  id uuid primary key default gen_random_uuid(),
  team_id text not null,
  analysis_id uuid not null,
  source_file_id uuid not null,
  target_file_id uuid not null,
  kind text not null,
  created_at timestamptz not null default now(),
  constraint edges_analysis_fk
    foreign key (analysis_id, team_id)
    references public.analyses (id, team_id)
    on delete cascade,
  constraint edges_source_file_fk
    foreign key (source_file_id, team_id)
    references public.files (id, team_id)
    on delete cascade,
  constraint edges_target_file_fk
    foreign key (target_file_id, team_id)
    references public.files (id, team_id)
    on delete cascade
);

alter table public.edges enable row level security;

revoke all on table public.edges from anon, authenticated, service_role;
revoke all on table public.edges from public;
grant select on table public.edges to authenticated;

create policy "members read their team's edges"
  on public.edges
  for select
  to authenticated
  using (
    exists (
      select 1
      from public.membership as membership_row
      where membership_row.user_id = (select auth.jwt() ->> 'sub')
        and membership_row.team_id = edges.team_id
    )
  );

create index edges_analysis_idx on public.edges (analysis_id);

create table public.routes (
  id uuid primary key default gen_random_uuid(),
  team_id text not null,
  analysis_id uuid not null,
  file_id uuid not null,
  method text not null,
  path text not null,
  created_at timestamptz not null default now(),
  constraint routes_analysis_fk
    foreign key (analysis_id, team_id)
    references public.analyses (id, team_id)
    on delete cascade,
  constraint routes_file_fk
    foreign key (file_id, team_id)
    references public.files (id, team_id)
    on delete cascade
);

alter table public.routes enable row level security;

revoke all on table public.routes from anon, authenticated, service_role;
revoke all on table public.routes from public;
grant select on table public.routes to authenticated;

create policy "members read their team's routes"
  on public.routes
  for select
  to authenticated
  using (
    exists (
      select 1
      from public.membership as membership_row
      where membership_row.user_id = (select auth.jwt() ->> 'sub')
        and membership_row.team_id = routes.team_id
    )
  );

create index routes_analysis_idx on public.routes (analysis_id);

create table public.explanations (
  id uuid primary key default gen_random_uuid(),
  team_id text not null,
  analysis_id uuid not null,
  file_id uuid not null,
  content_hash text not null,
  body text not null,
  created_at timestamptz not null default now(),
  constraint explanations_analysis_fk
    foreign key (analysis_id, team_id)
    references public.analyses (id, team_id)
    on delete cascade,
  constraint explanations_file_fk
    foreign key (file_id, team_id)
    references public.files (id, team_id)
    on delete cascade
);

alter table public.explanations enable row level security;

revoke all on table public.explanations from anon, authenticated, service_role;
revoke all on table public.explanations from public;
grant select on table public.explanations to authenticated;

create policy "members read their team's explanations"
  on public.explanations
  for select
  to authenticated
  using (
    exists (
      select 1
      from public.membership as membership_row
      where membership_row.user_id = (select auth.jwt() ->> 'sub')
        and membership_row.team_id = explanations.team_id
    )
  );

create index explanations_analysis_idx on public.explanations (analysis_id);

create table public.file_roles (
  id uuid primary key default gen_random_uuid(),
  team_id text not null,
  analysis_id uuid not null,
  file_id uuid not null,
  role text not null,
  created_at timestamptz not null default now(),
  constraint file_roles_analysis_fk
    foreign key (analysis_id, team_id)
    references public.analyses (id, team_id)
    on delete cascade,
  constraint file_roles_file_fk
    foreign key (file_id, team_id)
    references public.files (id, team_id)
    on delete cascade
);

alter table public.file_roles enable row level security;

revoke all on table public.file_roles from anon, authenticated, service_role;
revoke all on table public.file_roles from public;
grant select on table public.file_roles to authenticated;

create policy "members read their team's file roles"
  on public.file_roles
  for select
  to authenticated
  using (
    exists (
      select 1
      from public.membership as membership_row
      where membership_row.user_id = (select auth.jwt() ->> 'sub')
        and membership_row.team_id = file_roles.team_id
    )
  );

create index file_roles_analysis_idx on public.file_roles (analysis_id);

create table public.insights (
  id uuid primary key default gen_random_uuid(),
  team_id text not null,
  analysis_id uuid not null,
  kind text not null,
  detail jsonb not null,
  created_at timestamptz not null default now(),
  constraint insights_analysis_fk
    foreign key (analysis_id, team_id)
    references public.analyses (id, team_id)
    on delete cascade
);

alter table public.insights enable row level security;

revoke all on table public.insights from anon, authenticated, service_role;
revoke all on table public.insights from public;
grant select on table public.insights to authenticated;

create policy "members read their team's insights"
  on public.insights
  for select
  to authenticated
  using (
    exists (
      select 1
      from public.membership as membership_row
      where membership_row.user_id = (select auth.jwt() ->> 'sub')
        and membership_row.team_id = insights.team_id
    )
  );

create index insights_analysis_idx on public.insights (analysis_id);

-- The membership sync role has no table privilege on the eight tables. It reaches
-- them only through this routine, which runs with the migration role's rights and
-- therefore bypasses the select policies. The fixed empty search path keeps every
-- unqualified name in pg_catalog and forces the table names below to be explicit.
create function public.delete_team_rows(p_team_id text)
returns table (table_name text, deleted_rows bigint)
language plpgsql
security definer
set search_path = ''
as $$
declare
  deleted_edges bigint;
  deleted_routes bigint;
  deleted_explanations bigint;
  deleted_file_roles bigint;
  deleted_insights bigint;
  deleted_files bigint;
  deleted_analyses bigint;
  deleted_projects bigint;
begin
  if p_team_id is null or pg_catalog.btrim(p_team_id) = '' then
    raise exception 'team identifier must not be null or empty';
  end if;

  delete from public.edges as edge_row where edge_row.team_id = p_team_id;
  get diagnostics deleted_edges = row_count;

  delete from public.routes as route_row where route_row.team_id = p_team_id;
  get diagnostics deleted_routes = row_count;

  delete from public.explanations as explanation_row where explanation_row.team_id = p_team_id;
  get diagnostics deleted_explanations = row_count;

  delete from public.file_roles as file_role_row where file_role_row.team_id = p_team_id;
  get diagnostics deleted_file_roles = row_count;

  delete from public.insights as insight_row where insight_row.team_id = p_team_id;
  get diagnostics deleted_insights = row_count;

  delete from public.files as file_row where file_row.team_id = p_team_id;
  get diagnostics deleted_files = row_count;

  delete from public.analyses as analysis_row where analysis_row.team_id = p_team_id;
  get diagnostics deleted_analyses = row_count;

  delete from public.projects as project_row where project_row.team_id = p_team_id;
  get diagnostics deleted_projects = row_count;

  return query
  select *
  from (
    values
      ('edges'::text, deleted_edges),
      ('routes'::text, deleted_routes),
      ('explanations'::text, deleted_explanations),
      ('file_roles'::text, deleted_file_roles),
      ('insights'::text, deleted_insights),
      ('files'::text, deleted_files),
      ('analyses'::text, deleted_analyses),
      ('projects'::text, deleted_projects)
  ) as counts(table_name, deleted_rows);
end;
$$;

revoke all on function public.delete_team_rows(text) from public, anon, authenticated, service_role;
grant execute on function public.delete_team_rows(text) to codecraft_membership_sync;
