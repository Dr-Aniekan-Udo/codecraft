export type InvitationOrganisation = {
  id: string
  name: string
}

export type InvitationRow = {
  id: string
  emailAddress: string
  organisation: InvitationOrganisation
  publicMetadata: Record<string, unknown>
  status: string
  accept: () => Promise<unknown>
}

export type ClerkInvitationRow = Omit<InvitationRow, 'organisation'> & {
  publicOrganizationData: InvitationOrganisation
}

export type InvitationUser = {
  unsafeMetadata: Record<string, unknown>
  emailAddresses: ReadonlyArray<{
    emailAddress: string
    verification?: { status?: string | null } | null
  }>
}

export function declinedIdsFromUser(
  user: InvitationUser | null | undefined,
): Record<string, boolean> {
  const value = user?.unsafeMetadata['declinedOrganisationInvitationIds']
  if (typeof value !== 'object' || value === null || Array.isArray(value)) return {}
  const result: Record<string, boolean> = {}
  for (const [key, entry] of Object.entries(value)) {
    if (entry === true) result[key] = true
  }
  return result
}

export function pendingInvitationsForUser(
  invitations: readonly ClerkInvitationRow[],
  user: InvitationUser | null | undefined,
  additionalHiddenIds: Record<string, boolean> = {},
): InvitationRow[] {
  const verifiedEmails = new Set(
    (user?.emailAddresses ?? [])
      .filter((address) => address.verification?.status === 'verified')
      .map((address) => address.emailAddress.toLowerCase()),
  )
  const declined = { ...declinedIdsFromUser(user), ...additionalHiddenIds }

  return invitations
    .map(({ publicOrganizationData, ...invitation }) => ({
      ...invitation,
      organisation: publicOrganizationData,
    }))
    .filter(
      (invitation) =>
        invitation.status === 'pending' &&
        verifiedEmails.has(invitation.emailAddress.toLowerCase()) &&
        !declined[invitation.id],
    )
}

export function inviterName(invitation: InvitationRow): string {
  const name = invitation.publicMetadata['inviter_name']
  if (typeof name === 'string' && name.trim() && name.trim() !== 'An organisation admin') {
    return name.trim()
  }
  const email = invitation.publicMetadata['inviter_email']
  if (typeof email === 'string' && email.trim()) return email.trim()
  return 'An organisation admin'
}
