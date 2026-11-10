const TEAM_NAME_FALLBACK = 'No team'

function nonEmptyString(value: unknown): string | null {
  return typeof value === 'string' && value.trim().length > 0 ? value.trim() : null
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function organizationIdFromClaims(
  claims: Record<string, unknown> | null | undefined,
): string | null {
  const organization = claims?.['o']
  if (!isRecord(organization)) return null
  return nonEmptyString(organization['id'])
}

export function teamNameForEmail(email: string | null | undefined): string {
  if (!email) return 'My team'

  const at = email.indexOf('@')
  // The local part is used exactly as written: dots and plus signs included.
  const localPart = at === -1 ? email : email.slice(0, at)
  return `${localPart}'s team`
}

export type TeamNameAccount = {
  primaryEmailAddress: { emailAddress: string } | null
}

export function teamNameForAccount(account: TeamNameAccount): string {
  return teamNameForEmail(account.primaryEmailAddress?.emailAddress)
}

/**
 * The display name comes from the token, never from a lookup. If the display
 * claim is absent, the standard `o.id` claim supplies the team identifier, then
 * Clerk's active organization id. No guessed team name.
 */
export function resolveTeamName(
  claims: Record<string, unknown> | null | undefined,
  activeOrganizationId: string | null | undefined,
): string {
  return (
    nonEmptyString(claims?.['org_name']) ??
    organizationIdFromClaims(claims) ??
    nonEmptyString(activeOrganizationId) ??
    TEAM_NAME_FALLBACK
  )
}
