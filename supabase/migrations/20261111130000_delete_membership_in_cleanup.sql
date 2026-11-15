-- Team deletion now removes the mirrored membership rows as well. Without
-- this, the membership mirror can keep rows for a team that no longer exists
-- in Clerk, and the "every table" rule in the phase 1 spec would not hold.
--
-- The function is owned by the migration role, but membership is owned by the
-- narrow sync role. Give the function owner only the membership privileges it
-- needs, then keep the sync role's own rights narrow.
select set_config('codecraft.migration_role', current_user, false);
grant codecraft_membership_sync to current_user;
set role codecraft_membership_sync;
do $$
begin
  execute format(
    'grant select, delete on public.membership to %I',
    current_setting('codecraft.migration_role')
  );
end $$;
reset role;
revoke codecraft_membership_sync from current_user;

create or replace function public.delete_team_rows(p_team_id text)
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

  delete from public.membership as membership_row where membership_row.team_id = p_team_id;
  get diagnostics deleted_membership = row_count;

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

revoke all on function public.delete_team_rows(text) from public, anon, authenticated, service_role;
grant execute on function public.delete_team_rows(text) to codecraft_membership_sync;
