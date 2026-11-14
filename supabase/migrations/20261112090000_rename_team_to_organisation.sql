-- Rename the domain term from team to organisation. Clerk keeps its US spelling
-- in its own API; only our columns, constraints, indexes, policies and routines
-- use "organisation".

-- Membership is owned by the narrow sync role after 20261110090000, so its
-- column and index renames must run as that role. Renaming an index also needs
-- CREATE on the schema, which the sync role does not keep. The eight analysis
-- tables are still owned by the migration role.
select set_config('codecraft.migration_role', current_user, false);
grant codecraft_membership_sync to current_user;
grant create on schema public to codecraft_membership_sync;
set role codecraft_membership_sync;

do $$
begin
  if exists (
    select 1
    from information_schema.columns
    where table_schema = 'public'
      and table_name = 'membership'
      and column_name = 'team_id'
  ) then
    execute 'alter table public.membership rename column team_id to organisation_id';
  end if;
end $$;

do $$
begin
  if exists (
    select 1
    from pg_catalog.pg_class as index_class
    join pg_catalog.pg_namespace as index_namespace
      on index_namespace.oid = index_class.relnamespace
    where index_namespace.nspname = 'public'
      and index_class.relname = 'membership_one_owner_per_team'
      and index_class.relkind = 'i'
  ) then
    execute 'alter index public.membership_one_owner_per_team rename to membership_one_owner_per_organisation';
  end if;
end $$;

-- The outer cleanup routine is owned by the migration role, which has no
-- DELETE policy on membership. This helper is owned by the table's sync role,
-- so it bypasses the membership policy while the outer routine still owns the
-- single transaction and the eight analysis-table deletes.
create or replace function public.delete_membership_rows(p_organisation_id text)
returns bigint
language plpgsql
security definer
set search_path = ''
as $$
declare
  deleted bigint;
begin
  delete from public.membership where organisation_id = p_organisation_id;
  get diagnostics deleted = row_count;
  return deleted;
end;
$$;

revoke all on function public.delete_membership_rows(text)
  from public, anon, authenticated, service_role;

do $$
begin
  execute format(
    'grant execute on function public.delete_membership_rows(text) to %I',
    current_setting('codecraft.migration_role')
  );
end $$;

reset role;
revoke create on schema public from codecraft_membership_sync;
revoke codecraft_membership_sync from current_user;

alter table public.projects rename column team_id to organisation_id;
alter table public.analyses rename column team_id to organisation_id;
alter table public.files rename column team_id to organisation_id;
alter table public.edges rename column team_id to organisation_id;
alter table public.routes rename column team_id to organisation_id;
alter table public.explanations rename column team_id to organisation_id;
alter table public.file_roles rename column team_id to organisation_id;
alter table public.insights rename column team_id to organisation_id;

alter index if exists public.projects_team_created_idx
  rename to projects_organisation_created_idx;
alter index if exists public.analyses_team_created_idx
  rename to analyses_organisation_created_idx;

alter policy "members read their team's projects"
  on public.projects rename to "members read their organisation's projects";
alter policy "members read their team's analyses"
  on public.analyses rename to "members read their organisation's analyses";
alter policy "members read their team's files"
  on public.files rename to "members read their organisation's files";
alter policy "members read their team's edges"
  on public.edges rename to "members read their organisation's edges";
alter policy "members read their team's routes"
  on public.routes rename to "members read their organisation's routes";
alter policy "members read their team's explanations"
  on public.explanations rename to "members read their organisation's explanations";
alter policy "members read their team's file roles"
  on public.file_roles rename to "members read their organisation's file roles";
alter policy "members read their team's insights"
  on public.insights rename to "members read their organisation's insights";

-- Column renames do not rename constraints or their backing indexes. Rename
-- every remaining name that still contains the old column name.
do $$
declare
  constraint_row record;
begin
  for constraint_row in
    select n.nspname as schema_name, c.relname as table_name, con.conname as constraint_name
    from pg_catalog.pg_constraint as con
    join pg_catalog.pg_class as c on c.oid = con.conrelid
    join pg_catalog.pg_namespace as n on n.oid = c.relnamespace
    where n.nspname = 'public'
      and pg_catalog.strpos(con.conname::text, 'team_id') > 0
    order by n.nspname, c.relname, con.conname
  loop
    execute format(
      'alter table %I.%I rename constraint %I to %I',
      constraint_row.schema_name,
      constraint_row.table_name,
      constraint_row.constraint_name,
      replace(constraint_row.constraint_name::text, 'team_id', 'organisation_id')
    );
  end loop;
end $$;

do $$
declare
  index_row record;
begin
  for index_row in
    select i.schemaname as schema_name, i.indexname as index_name
    from pg_catalog.pg_indexes as i
    where i.schemaname = 'public'
      and pg_catalog.strpos(i.indexname::text, 'team_id') > 0
    order by i.schemaname, i.indexname
  loop
    execute format(
      'alter index %I.%I rename to %I',
      index_row.schema_name,
      index_row.index_name,
      replace(index_row.index_name::text, 'team_id', 'organisation_id')
    );
  end loop;
end $$;

grant codecraft_membership_sync to current_user;
set role codecraft_membership_sync;
comment on column public.membership.is_owner is
  'True only for the person Clerk recorded as the organisation creator.';
reset role;
revoke codecraft_membership_sync from current_user;

create function public.delete_organisation_rows(p_organisation_id text)
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
  deleted_membership bigint;
begin
  if p_organisation_id is null or pg_catalog.btrim(p_organisation_id) = '' then
    raise exception 'organisation identifier must not be null or empty';
  end if;

  delete from public.edges as edge_row where edge_row.organisation_id = p_organisation_id;
  get diagnostics deleted_edges = row_count;

  delete from public.routes as route_row where route_row.organisation_id = p_organisation_id;
  get diagnostics deleted_routes = row_count;

  delete from public.explanations as explanation_row
  where explanation_row.organisation_id = p_organisation_id;
  get diagnostics deleted_explanations = row_count;

  delete from public.file_roles as file_role_row
  where file_role_row.organisation_id = p_organisation_id;
  get diagnostics deleted_file_roles = row_count;

  delete from public.insights as insight_row
  where insight_row.organisation_id = p_organisation_id;
  get diagnostics deleted_insights = row_count;

  delete from public.files as file_row where file_row.organisation_id = p_organisation_id;
  get diagnostics deleted_files = row_count;

  delete from public.analyses as analysis_row
  where analysis_row.organisation_id = p_organisation_id;
  get diagnostics deleted_analyses = row_count;

  delete from public.projects as project_row
  where project_row.organisation_id = p_organisation_id;
  get diagnostics deleted_projects = row_count;

  deleted_membership := public.delete_membership_rows(p_organisation_id);

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
      ('projects'::text, deleted_projects),
      ('membership'::text, deleted_membership)
  ) as counts(table_name, deleted_rows);
end;
$$;

revoke all on function public.delete_organisation_rows(text)
  from public, anon, authenticated, service_role;
grant execute on function public.delete_organisation_rows(text)
  to codecraft_membership_sync;

drop function if exists public.delete_team_rows(text);
