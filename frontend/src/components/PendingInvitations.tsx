import { useOrganizationList, useUser } from '@clerk/react'
import { useMemo, useState } from 'react'
import {
  declinedIdsFromUser,
  inviterName,
  pendingInvitationsForUser,
} from '../lib/invitations'
import type { ClerkInvitationRow, InvitationRow } from '../lib/invitations'
import { notifyOrganisationsChanged } from '../lib/organisationEvents'
import { markMembershipSyncPending } from '../lib/organisationSync'

export function PendingInvitations({
  emptyState,
  heading = true,
}: {
  emptyState: boolean
  heading?: boolean
}) {
  const { user } = useUser()
  // Clerk's API uses the US spelling 'organization'; the application's domain
  // term is 'organisation'.
  const { userInvitations, userMemberships } = useOrganizationList({
    userInvitations: { infinite: true, pageSize: 100 },
    userMemberships: { infinite: true, pageSize: 100 },
  })
  const [hiddenInvitationIds, setHiddenInvitationIds] = useState<Record<string, boolean>>(
    {},
  )
  const [busyId, setBusyId] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)

  const visibleInvitations = useMemo(
    () =>
      pendingInvitationsForUser(
        (userInvitations.data ?? []) as ClerkInvitationRow[],
        user,
        hiddenInvitationIds,
      ),
    [hiddenInvitationIds, user, userInvitations.data],
  )

  const showEmptyState =
    emptyState &&
    !userInvitations.isLoading &&
    !userInvitations.isError &&
    !userInvitations.hasNextPage &&
    visibleInvitations.length === 0
  const canLoadMore =
    userInvitations.hasNextPage && userInvitations.fetchNext !== undefined

  async function accept(invitation: InvitationRow): Promise<void> {
    if (busyId) return
    setBusyId(invitation.id)
    setError(null)
    setNotice(null)
    try {
      await invitation.accept()
      setHiddenInvitationIds((previous) => ({ ...previous, [invitation.id]: true }))
      markMembershipSyncPending(invitation.organisation.id)
      notifyOrganisationsChanged()
      if (userInvitations.revalidate) await userInvitations.revalidate()
      if (userMemberships.revalidate) await userMemberships.revalidate()
      setNotice(
        `You joined ${invitation.organisation.name}. Switch to it when you are ready.`,
      )
    } catch {
      setError('The invitation could not be accepted. Try again.')
    } finally {
      setBusyId(null)
    }
  }

  async function decline(invitation: InvitationRow): Promise<void> {
    if (busyId || !user) return
    setBusyId(invitation.id)
    setError(null)
    setNotice(null)
    try {
      const current = declinedIdsFromUser(user)
      await user.updateMetadata({
        unsafeMetadata: {
          declinedOrganisationInvitationIds: { ...current, [invitation.id]: true },
        },
      })
      setHiddenInvitationIds((previous) => ({ ...previous, [invitation.id]: true }))
      notifyOrganisationsChanged()
      if (userInvitations.revalidate) await userInvitations.revalidate()
    } catch {
      setError('The invitation could not be declined. Try again.')
    } finally {
      setBusyId(null)
    }
  }

  if (
    visibleInvitations.length === 0 &&
    !showEmptyState &&
    !userInvitations.isLoading &&
    !userInvitations.isError &&
    !canLoadMore &&
    !error &&
    !notice
  ) {
    return null
  }

  return (
    <section
      className="invitations"
      aria-labelledby={heading ? 'pending-invitations-title' : undefined}
      aria-label={heading ? undefined : 'Pending invitations'}
    >
      {heading ? (
        <h2 id="pending-invitations-title" className="section-label">
          Pending invitations
        </h2>
      ) : null}

      {userInvitations.isLoading ? (
        <p className="plain-line" role="status">
          Loading invitations…
        </p>
      ) : null}

      {userInvitations.isError ? (
        <p className="plain-line plain-line--alert" role="alert">
          Invitations could not be loaded. Try again.
        </p>
      ) : null}

      {showEmptyState ? (
        <div className="empty-state" role="status">
          <p>No pending invitation exists for this account.</p>
          <p>
            If you were invited, sign in with the address the invitation was sent to. Nothing needs
            to be typed here.
          </p>
        </div>
      ) : null}

      {visibleInvitations.length > 0 ? (
        <ul className="invitation-list">
          {visibleInvitations.map((invitation) => (
            <li className="invitation-list__item" key={invitation.id}>
              <div>
                <p className="invitation-list__organisation">
                  {invitation.organisation.name}
                </p>
                <p className="invitation-list__detail">
                  Invited by {inviterName(invitation)}
                </p>
              </div>
              <div className="invitation-list__actions">
                <button
                  type="button"
                  className="button button--primary"
                  onClick={() => void accept(invitation)}
                  disabled={busyId !== null}
                >
                  {busyId === invitation.id ? 'Accepting…' : 'Accept'}
                </button>
                <button
                  type="button"
                  className="button"
                  onClick={() => void decline(invitation)}
                  disabled={busyId !== null}
                >
                  Decline
                </button>
              </div>
            </li>
          ))}
        </ul>
      ) : null}

      {canLoadMore ? (
        <button
          type="button"
          className="button"
          onClick={() => userInvitations.fetchNext()}
          disabled={userInvitations.isFetching}
        >
          Load more invitations
        </button>
      ) : null}

      {error ? (
        <p className="inline-message" role="alert">
          {error}
        </p>
      ) : null}
      {notice ? (
        <p className="inline-message inline-message--success" role="status">
          {notice}
        </p>
      ) : null}
    </section>
  )
}
