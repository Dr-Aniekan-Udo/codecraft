-- Remove a deleted organisation's creation-attempt rows in the same cleanup.
--
-- The routine stays owned by the migration role, which also owns the attempts
-- table, so it can delete rows that codecraft_creation can only read or update.

create or replace function public.delete_organisation_rows(p_organisation_id text)
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
  deleted_attempts bigint;
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

  delete from public.organisation_creation_attempts as attempt_row
  where attempt_row.organisation_id = p_organisation_id;
  get diagnostics deleted_attempts = row_count;

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
      ('organisation_creation_attempts'::text, deleted_attempts),
      ('membership'::text, deleted_membership)
  ) as counts(table_name, deleted_rows);
end;
$$;

revoke all on function public.delete_organisation_rows(text)
  from public, anon, authenticated, service_role;
grant execute on function public.delete_organisation_rows(text)
  to codecraft_membership_sync;
