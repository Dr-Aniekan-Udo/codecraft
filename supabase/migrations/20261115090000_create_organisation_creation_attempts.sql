-- Cross-process idempotency for organisation creation.
--
-- Each browser attempt is keyed by the Clerk user id and the idempotency key it
-- sent. The row records the outcome and the Clerk organisation it produced, but
-- never a name, email address, token or error text.
--
-- The API login role assumes codecraft_creation only for the creation
-- connection. The role is NOLOGIN, so this migration adds no password, secret or
-- service-level credential. No browser role can read or write this table.

do $$
begin
  if not exists (select 1 from pg_roles where rolname = 'codecraft_creation') then
    create role codecraft_creation nologin nosuperuser nobypassrls noinherit noreplication;
  end if;
end $$;

grant usage on schema public to codecraft_creation;

create table public.organisation_creation_attempts (
  user_id text not null,
  idempotency_key text not null,
  status text not null,
  organisation_id text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint organisation_creation_attempts_pkey
    primary key (user_id, idempotency_key),
  constraint organisation_creation_attempts_user_length
    check (char_length(user_id) between 1 and 256),
  constraint organisation_creation_attempts_key_length
    check (char_length(idempotency_key) between 1 and 200),
  constraint organisation_creation_attempts_status
    check (status in ('claimed', 'created', 'failed')),
  constraint organisation_creation_attempts_created_org
    check ((status = 'created') = (organisation_id is not null)),
  constraint organisation_creation_attempts_org_length
    check (organisation_id is null or char_length(organisation_id) between 1 and 256)
);

alter table public.organisation_creation_attempts enable row level security;

revoke all on table public.organisation_creation_attempts from anon, authenticated, service_role;
revoke all on table public.organisation_creation_attempts from public;
grant select, insert, update on table public.organisation_creation_attempts to codecraft_creation;
grant codecraft_creation to codecraft_api;

-- The API role is NOINHERIT, so it does not get these privileges automatically.
-- It must switch to codecraft_creation inside the creation connection.
create policy "creation attempts are read by their user"
  on public.organisation_creation_attempts
  for select
  to codecraft_creation
  using (
    user_id = (select auth.jwt() ->> 'sub')
  );

create policy "creation attempts are inserted by their user"
  on public.organisation_creation_attempts
  for insert
  to codecraft_creation
  with check (
    user_id = (select auth.jwt() ->> 'sub')
  );

create policy "creation attempts are updated by their user"
  on public.organisation_creation_attempts
  for update
  to codecraft_creation
  using (
    user_id = (select auth.jwt() ->> 'sub')
  )
  with check (
    user_id = (select auth.jwt() ->> 'sub')
  );

comment on table public.organisation_creation_attempts is
  'Cross-process organisation-creation idempotency. Holds only the Clerk user id, the browser key, the outcome, the produced Clerk organisation id and timestamps.';
comment on column public.organisation_creation_attempts.status is
  'claimed while the identity-provider call is in flight, created with an organisation id, or failed without one.';
