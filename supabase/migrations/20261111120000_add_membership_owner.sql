-- The owner is the person recorded by Clerk as the organisation's creator.
-- Clerk's frontend API never exposes created_by, so the signed webhook mirror
-- stores it here. One team can have at most one owner.
--
-- 20261110090000 moved ownership of this table to the narrow sync role. The
-- migration role no longer owns it, so every membership write must run as the
-- sync role. Grant that role temporarily, do the work, then restore the narrow
-- grants.
grant codecraft_membership_sync to current_user;
grant create on schema public to codecraft_membership_sync;
set role codecraft_membership_sync;

alter table public.membership
  add column if not exists is_owner boolean not null default false;

create unique index if not exists membership_one_owner_per_team
  on public.membership (team_id)
  where is_owner;

comment on column public.membership.is_owner is
  'True only for the person Clerk recorded as the team creator.';

reset role;
revoke create on schema public from codecraft_membership_sync;
revoke codecraft_membership_sync from current_user;
