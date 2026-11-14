import { useAuth, useOrganization } from '@clerk/react'
import type {
  MembershipState,
  OrganisationRole,
} from '../api/useMembershipStatus'
import { resolveOrganisationName } from '../lib/identity'

export type WorkspaceIdentity = {
  organisationName: string | null
  role: string | null
}

function roleLabel(role: OrganisationRole): string | null {
  if (role === 'admin') return 'Admin'
  if (role === 'member') return 'Member'
  return null
}

/**
 * The organisation and role shown in the detail pane. The organisation name
 * comes from Clerk, which already holds the active organisation. The role comes
 * from the API's verified answer for the token, not from Clerk's membership,
 * because an admin change takes effect on the next request.
 */
export function useWorkspaceIdentity(
  membership: MembershipState,
  role: OrganisationRole,
): WorkspaceIdentity {
  const { sessionClaims } = useAuth()
  // Clerk's API uses the US spelling 'organization'; the application's domain
  // term is 'organisation'.
  const { organization } = useOrganization()

  if (membership !== 'member') {
    return { organisationName: null, role: null }
  }

  const activeName = organization?.name.trim()
  return {
    organisationName: activeName
      ? activeName
      : resolveOrganisationName(sessionClaims),
    role: roleLabel(role),
  }
}
