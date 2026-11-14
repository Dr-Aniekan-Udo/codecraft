const PENDING_MEMBERSHIPS_KEY = 'codecraft.pendingMemberships'
const PENDING_PERSONAL_KEY = 'codecraft.pendingPersonalOrganisation'
const PENDING_ORGANISATION_CREATION_KEY = 'codecraft.pendingOrganisationCreation'
const PERSONAL_WRITE_TTL_MS = 60_000
export const MEMBERSHIP_SYNC_TTL_MS = 60_000
const ORGANISATION_CREATION_TTL_MS = 10_000

type PendingMemberships = Record<string, number>

type PendingPersonalOrganisation = {
  userId: string
  idempotencyKey: string
  startedAt: number
}

type PendingOrganisationCreation = {
  userId: string
  name: string
  idempotencyKey: string
  startedAt: number
}

function read<T>(key: string): T | null {
  try {
    const value = window.localStorage.getItem(key)
    return value === null ? null : (JSON.parse(value) as T)
  } catch {
    return null
  }
}

function write(key: string, value: unknown): void {
  try {
    window.localStorage.setItem(key, JSON.stringify(value))
  } catch {
    // The page still works; it just cannot remember the pending write.
  }
}

function remove(key: string): void {
  try {
    window.localStorage.removeItem(key)
  } catch {
    // Nothing to clear.
  }
}

export function markMembershipSyncPending(organisationId: string): void {
  const current = read<PendingMemberships>(PENDING_MEMBERSHIPS_KEY) ?? {}
  write(PENDING_MEMBERSHIPS_KEY, {
    ...current,
    [organisationId]: Date.now(),
  } satisfies PendingMemberships)
}

export function isMembershipSyncPending(organisationId: string): boolean {
  const pending = read<PendingMemberships>(PENDING_MEMBERSHIPS_KEY)
  const startedAt = pending?.[organisationId]
  if (startedAt === undefined) return false
  if (Date.now() - startedAt >= MEMBERSHIP_SYNC_TTL_MS) {
    clearMembershipSyncPending(organisationId)
    return false
  }
  return true
}

export function clearMembershipSyncPending(organisationId: string): void {
  const pending = read<PendingMemberships>(PENDING_MEMBERSHIPS_KEY)
  if (pending === null || pending[organisationId] === undefined) return
  const next = { ...pending }
  delete next[organisationId]
  if (Object.keys(next).length === 0) {
    remove(PENDING_MEMBERSHIPS_KEY)
  } else {
    write(PENDING_MEMBERSHIPS_KEY, next)
  }
}

export function pendingOrganisationCreationKey(userId: string, name: string): string | null {
  const pending = read<PendingOrganisationCreation>(PENDING_ORGANISATION_CREATION_KEY)
  if (
    pending?.userId !== userId ||
    pending.name !== name ||
    Date.now() - pending.startedAt >= ORGANISATION_CREATION_TTL_MS
  ) {
    return null
  }
  return typeof pending.idempotencyKey === 'string' && pending.idempotencyKey.length > 0
    ? pending.idempotencyKey
    : null
}

export function markOrganisationCreationPending(
  userId: string,
  name: string,
  idempotencyKey: string,
): void {
  write(PENDING_ORGANISATION_CREATION_KEY, {
    userId,
    name,
    idempotencyKey,
    startedAt: Date.now(),
  } satisfies PendingOrganisationCreation)
}

export function markPersonalOrganisationPending(
  userId: string,
  idempotencyKey: string,
): void {
  write(PENDING_PERSONAL_KEY, {
    userId,
    idempotencyKey,
    startedAt: Date.now(),
  } satisfies PendingPersonalOrganisation)
}

export function pendingPersonalOrganisationIdempotencyKey(
  userId: string,
): string | null {
  const pending = read<PendingPersonalOrganisation>(PENDING_PERSONAL_KEY)
  if (
    pending?.userId !== userId ||
    Date.now() - pending.startedAt >= PERSONAL_WRITE_TTL_MS
  ) {
    return null
  }
  const key: unknown = pending.idempotencyKey
  return typeof key === 'string' && key.length > 0 ? key : null
}

export function hasPendingPersonalOrganisation(userId: string): boolean {
  const pending = read<PendingPersonalOrganisation>(PENDING_PERSONAL_KEY)
  return (
    pending?.userId === userId && Date.now() - pending.startedAt < PERSONAL_WRITE_TTL_MS
  )
}

export function clearPendingPersonalOrganisation(userId: string): void {
  const pending = read<PendingPersonalOrganisation>(PENDING_PERSONAL_KEY)
  if (pending?.userId === userId) remove(PENDING_PERSONAL_KEY)
}
