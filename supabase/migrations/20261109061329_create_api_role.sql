-- The API's restricted login role. It has no password here: set that separately, once.
do $$
begin
  if not exists (select 1 from pg_roles where rolname = 'codecraft_api') then
    create role codecraft_api login nosuperuser nobypassrls noinherit noreplication;
  end if;
end $$;

-- The API switches into the authenticated role for each request, so policies apply.
grant authenticated to codecraft_api;
grant usage on schema public to codecraft_api;

-- Deliberately not granted: anon, service_role, bypassrls, superuser.
