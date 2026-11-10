-- The webhook's narrow login role. It has no password here: set that separately, once.
do $$
begin
  if not exists (select 1 from pg_roles where rolname = 'codecraft_membership_sync') then
    create role codecraft_membership_sync login nosuperuser nobypassrls noinherit noreplication;
  end if;
end $$;

grant usage on schema public to codecraft_membership_sync;

create table public.membership (
  user_id text not null,
  team_id text not null,
  created_at timestamptz not null default now(),
  primary key (user_id, team_id)
);

-- Row-level security, grants and the read policy are set up while this migration still
-- owns the table. Ownership moves to the sync role last, because after the move this
-- migration no longer owns the table and cannot change it.
alter table public.membership enable row level security;

revoke all on table public.membership from anon, authenticated, service_role;
revoke all on table public.membership from public;
grant select on table public.membership to authenticated;

-- auth.jwt() carries the verified Clerk subject. auth.uid() would cast it to uuid and fail,
-- because Clerk user IDs are text, not UUIDs.
create policy "members read their own memberships"
  on public.membership
  for select
  to authenticated
  using (user_id = (select auth.jwt() ->> 'sub'));

-- Ownership goes to the sync role, so the webhook can write without any grant on other tables.
-- Table owners bypass row-level security; that is acceptable because only membership sync
-- uses the owner. The transfer needs two things, and both are removed straight after:
--   1. this migration's role must be a member of the new owner;
--   2. the new owner must hold CREATE on the schema.
grant codecraft_membership_sync to current_user;
grant create on schema public to codecraft_membership_sync;
alter table public.membership owner to codecraft_membership_sync;
revoke create on schema public from codecraft_membership_sync;
revoke codecraft_membership_sync from current_user;
