import { useOrganizationList, useUser } from '@clerk/react'
import { useMemo } from 'react'
import { pendingInvitationsForUser } from '../lib/invitations'
import type { ClerkInvitationRow } from '../lib/invitations'

/**
 * The pending invitation count for the header badge and the invitations page
 * heading. It is shown only when the first full page of invitations is already
 * held: a partial page would be a wrong count, so it is omitted rather than
 * approximated.
 */
export function usePendingInvitationCount(): number | null {
  const { user } = useUser()
  // Clerk's API uses the US spelling 'organization'; the application's domain
  // term is 'organisation'.
  const { userInvitations } = useOrganizationList({
    userInvitations: { infinite: true, pageSize: 100 },
  })

  return useMemo(() => {
    const invitations = userInvitations.data
    if (
      user === null ||
      invitations === undefined ||
      userInvitations.isError ||
      userInvitations.hasNextPage
    ) {
      return null
    }

    return pendingInvitationsForUser(
      invitations as ClerkInvitationRow[],
      user,
    ).length
  }, [user, userInvitations.data, userInvitations.hasNextPage, userInvitations.isError])
}
