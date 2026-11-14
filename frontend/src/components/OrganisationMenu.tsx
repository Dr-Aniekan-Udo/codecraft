import { useAuth, useOrganization, useOrganizationList, useUser } from '@clerk/react'
import { useRef, useState } from 'react'
import type { FormEvent } from 'react'
import {
  createOrganisation,
  leaveOrganisation,
  OrganisationRequestError,
  removeOrganisationMember,
  updateOrganisationMemberRole,
} from '../api/organisations'
import type { OrganisationMemberRole } from '../api/organisations'
import { useOrganisations } from '../api/useOrganisations'
import { organisationNameFromToken } from '../lib/identity'
import {
  markMembershipSyncPending,
  markOrganisationCreationPending,
  pendingOrganisationCreationKey,
} from '../lib/organisationSync'

type PendingInvitation = {
  id: string
  emailAddress: string
  revoke: () => Promise<unknown>
}

type OrganisationMember = {
  id: string
  role: string
  publicUserData?: {
    userId?: string
    identifier?: string
    firstName?: string | null
    lastName?: string | null
  }
}

function memberName(member: OrganisationMember): string {
  const first = member.publicUserData?.firstName?.trim() ?? ''
  const last = member.publicUserData?.lastName?.trim() ?? ''
  const name = `${first} ${last}`.trim()
  if (name) return name
  if (member.publicUserData?.identifier) return member.publicUserData.identifier
  return member.publicUserData?.userId ?? 'Member'
}

function roleLabel(
  member: OrganisationMember,
  isOwner: boolean,
  currentUserId: string | undefined,
): string {
  if (isOwner && member.publicUserData?.userId === currentUserId) return 'Owner'
  if (member.role === 'org:admin') return 'Admin'
  if (member.role === 'org:member') return 'Member'
  return member.role
}

function requestMessage(error: unknown, fallback: string): string {
  return error instanceof OrganisationRequestError && error.detail
    ? error.detail
    : fallback
}

export function OrganisationMenu({
  apiUrl,
  onRenamed,
}: {
  apiUrl: string
  onRenamed: (name: string) => void
}) {
  // Clerk's API uses the US spelling 'organization'; the application's domain
  // term is 'organisation'.
  const { organization: activeOrganisation, membership } = useOrganization()
  const { user } = useUser()
  const { getToken } = useAuth()
  const { setActive, userMemberships } = useOrganizationList({
    userMemberships: { infinite: true, pageSize: 100 },
  })
  const organisationsState = useOrganisations(apiUrl)
  const dialogRef = useRef<HTMLDialogElement>(null)
  // One attempt has one key: a double press or retry reuses this ref, and
  // another tab creating the same name reuses the short-lived stored key.
  const createIdempotencyKey = useRef<string | null>(null)
  const [creating, setCreating] = useState(false)
  const [newOrganisationName, setNewOrganisationName] = useState('')
  const [renameValue, setRenameValue] = useState('')
  const [pendingInvitations, setPendingInvitations] = useState<PendingInvitation[]>([])
  const [members, setMembers] = useState<OrganisationMember[]>([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)

  if (!activeOrganisation) return null

  const currentUserId = user?.id
  const canManage = membership?.permissions.includes('org:sys_memberships:manage') ?? false
  const canRename = membership?.permissions.includes('org:sys_profile:manage') ?? false
  const activeOrganisationSummary = organisationsState.organisations.find(
    (organisation) => organisation.organisationId === activeOrganisation.id,
  )
  const anotherOwnedOrganisation = organisationsState.organisations.some(
    (organisation) =>
      organisation.organisationId !== activeOrganisation.id && organisation.isOwner,
  )
  const isOwner = activeOrganisationSummary?.isOwner ?? false

  const open = (): void => {
    setRenameValue(activeOrganisation.name)
    setError(null)
    setNotice(null)
    dialogRef.current?.showModal()
    if (canManage) void loadAdminData()
  }

  function close(): void {
    dialogRef.current?.close()
  }

  const loadAdminData = async (): Promise<void> => {
    if (!canManage) return
    try {
      const [invitations, memberships] = await Promise.all([
        activeOrganisation.getInvitations({ status: ['pending'], pageSize: 100 }),
        activeOrganisation.getMemberships({ pageSize: 100 }),
      ])
      setPendingInvitations(invitations.data)
      setMembers(memberships.data)
    } catch {
      setError('The organisation members could not be loaded.')
    }
  }

  async function handleCreate(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault()
    const name = newOrganisationName.trim()
    const currentUser = user
    if (!name || !currentUser || !setActive || creating) return

    setCreating(true)
    setError(null)
    setNotice(null)

    const createOnce = async () => {
      const idempotencyKey =
        createIdempotencyKey.current ??
        pendingOrganisationCreationKey(currentUser.id, name) ??
        crypto.randomUUID()
      createIdempotencyKey.current = idempotencyKey
      markOrganisationCreationPending(currentUser.id, name, idempotencyKey)

      const token = await getToken({ skipCache: true })
      if (!token) throw new Error('no token')
      const organisationId = await createOrganisation(apiUrl, token, {
        name,
        idempotencyKey,
      })
      markMembershipSyncPending(organisationId)
      if (userMemberships.revalidate) await userMemberships.revalidate()
      await setActive({ organization: organisationId })
      organisationsState.reload()
      createIdempotencyKey.current = null
      setNewOrganisationName('')
      setNotice('Organisation created.')
    }

    try {
      if (navigator.locks) {
        await navigator.locks.request(
          `codecraft:create-organisation:${currentUser.id}`,
          createOnce,
        )
      } else {
        await createOnce()
      }
    } catch (error: unknown) {
      setError(
        requestMessage(error, 'The organisation could not be created. Try again.'),
      )
    } finally {
      setCreating(false)
    }
  }

  const handleRename = async (event: FormEvent<HTMLFormElement>): Promise<void> => {
    event.preventDefault()
    const name = renameValue.trim()
    if (!name || !canRename || busy) return

    setBusy(true)
    setError(null)
    setNotice(null)
    try {
      await activeOrganisation.update({ name })
      let displayedName = name
      try {
        const token = await getToken({
          organizationId: activeOrganisation.id,
          skipCache: true,
        })
        const tokenName = token ? organisationNameFromToken(token) : null
        if (tokenName !== null) displayedName = tokenName
      } catch {
        // The rename succeeded; the entered name is still correct for display.
      }
      onRenamed(displayedName)
      organisationsState.reload()
      setNotice('Organisation renamed.')
    } catch {
      setError('The organisation could not be renamed.')
    } finally {
      setBusy(false)
    }
  }

  async function handleRevoke(invitation: PendingInvitation): Promise<void> {
    if (busy) return
    setBusy(true)
    setError(null)
    try {
      await invitation.revoke()
      await loadAdminData()
    } catch {
      setError('The invitation could not be revoked.')
    } finally {
      setBusy(false)
    }
  }

  const handleRemove = async (member: OrganisationMember): Promise<void> => {
    const memberUserId = member.publicUserData?.userId
    if (busy) return
    if (!memberUserId) {
      setError('The member could not be removed.')
      return
    }

    setBusy(true)
    setError(null)
    setNotice(null)
    try {
      const token = await getToken({
        organizationId: activeOrganisation.id,
        skipCache: true,
      })
      if (!token) {
        setError('Your session could not be read.')
        return
      }
      await removeOrganisationMember(
        apiUrl,
        token,
        activeOrganisation.id,
        memberUserId,
      )
      if (userMemberships.revalidate) await userMemberships.revalidate()
      await loadAdminData()
    } catch (error: unknown) {
      setError(requestMessage(error, 'The member could not be removed.'))
    } finally {
      setBusy(false)
    }
  }

  const handleRole = async (
    member: OrganisationMember,
    role: OrganisationMemberRole,
  ): Promise<void> => {
    const memberUserId = member.publicUserData?.userId
    if (!isOwner || busy || !memberUserId) return

    setBusy(true)
    setError(null)
    setNotice(null)
    try {
      const token = await getToken({
        organizationId: activeOrganisation.id,
        skipCache: true,
      })
      if (!token) {
        setError('Your session could not be read.')
        return
      }
      await updateOrganisationMemberRole(
        apiUrl,
        token,
        activeOrganisation.id,
        memberUserId,
        role,
      )
      await loadAdminData()
      setNotice('Role updated.')
    } catch (error: unknown) {
      setError(requestMessage(error, "The member's role could not be changed."))
    } finally {
      setBusy(false)
    }
  }

  const handleLeave = async (): Promise<void> => {
    const currentUser = user
    if (busy || isOwner || !currentUser || !setActive) return

    setBusy(true)
    setError(null)
    setNotice(null)
    try {
      const token = await getToken({
        organizationId: activeOrganisation.id,
        skipCache: true,
      })
      if (!token) {
        setError('Your session could not be read.')
        return
      }
      await leaveOrganisation(
        apiUrl,
        token,
        activeOrganisation.id,
        currentUser.id,
      )
      if (userMemberships.revalidate) await userMemberships.revalidate()
      organisationsState.reload()
      const remaining = organisationsState.organisations.find(
        (organisation) => organisation.organisationId !== activeOrganisation.id,
      )
      if (remaining) {
        await setActive({ organization: remaining.organisationId })
      }
      close()
    } catch (error: unknown) {
      setError(requestMessage(error, 'The organisation could not be left.'))
    } finally {
      setBusy(false)
    }
  }

  const handleDelete = async (): Promise<void> => {
    if (!isOwner || !anotherOwnedOrganisation || busy) return

    setBusy(true)
    setError(null)
    try {
      const token = await getToken({
        organizationId: activeOrganisation.id,
        skipCache: true,
      })
      if (!token) {
        setError('Your session could not be read.')
        return
      }
      const response = await fetch(
        `${apiUrl}/v1/organisations/${activeOrganisation.id}`,
        {
          method: 'DELETE',
          headers: {
            Accept: 'application/json',
            Authorization: `Bearer ${token}`,
          },
        },
      )
      if (!response.ok) {
        setError(
          response.status === 403
            ? 'You must own another organisation before deleting this one.'
            : 'The organisation could not be deleted.',
        )
        return
      }

      const remaining = organisationsState.organisations.find(
        (organisation) =>
          organisation.organisationId !== activeOrganisation.id &&
          organisation.isOwner,
      )
      if (userMemberships.revalidate) await userMemberships.revalidate()
      organisationsState.reload()
      if (remaining && setActive) {
        await setActive({ organization: remaining.organisationId })
      }
      close()
    } catch {
      setError('The organisation could not be deleted.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <>
      <button
        type="button"
        className="icon-button"
        onClick={open}
        aria-label="Organisations"
        title="Organisations"
        aria-haspopup="dialog"
      >
        <svg
          viewBox="0 0 16 16"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.2"
          aria-hidden="true"
          focusable="false"
        >
          <path d="M2.5 4h2.2M7.3 4h6.2M2.5 8h6.8M11.9 8h1.6M2.5 12h2.2M7.3 12h6.2" />
          <circle cx="6" cy="4" r="1.2" />
          <circle cx="10.6" cy="8" r="1.2" />
          <circle cx="5.6" cy="12" r="1.2" />
        </svg>
      </button>
      <dialog
        ref={dialogRef}
        className="dialog"
        aria-labelledby="organisation-menu-title"
        onClose={() => {
          setError(null)
          setNotice(null)
        }}
      >
        <div className="dialog__form">
          <h2 id="organisation-menu-title">Organisations</h2>

          <section aria-labelledby="create-organisation-title">
            <h3 id="create-organisation-title">Create an organisation</h3>
            <form className="inline-form" onSubmit={(event) => void handleCreate(event)}>
              <label className="visually-hidden" htmlFor="new-organisation-name">
                Organisation name
              </label>
              <input
                id="new-organisation-name"
                className="input"
                value={newOrganisationName}
                onChange={(event) => setNewOrganisationName(event.target.value)}
                placeholder="Organisation name"
                required
              />
              <button
                type="submit"
                className="button"
                disabled={creating || !newOrganisationName.trim()}
              >
                {creating ? 'Creating…' : 'Create'}
              </button>
            </form>
          </section>

          {canRename ? (
            <section aria-labelledby="rename-organisation-title">
              <h3 id="rename-organisation-title">Rename this organisation</h3>
              <form className="inline-form" onSubmit={(event) => void handleRename(event)}>
                <label className="visually-hidden" htmlFor="rename-organisation">
                  Organisation name
                </label>
                <input
                  id="rename-organisation"
                  className="input"
                  value={renameValue}
                  onChange={(event) => setRenameValue(event.target.value)}
                  required
                />
                <button
                  type="submit"
                  className="button"
                  disabled={busy || !renameValue.trim()}
                >
                  Rename
                </button>
              </form>
            </section>
          ) : null}

          {canManage ? (
            <section aria-labelledby="members-title">
              <h3 id="members-title">Members</h3>
              {members.length === 0 ? <p>No members loaded.</p> : null}
              <ul className="plain-list">
                {members.map((member) => {
                  const memberUserId = member.publicUserData?.userId
                  const isCurrentUser =
                    memberUserId !== undefined && memberUserId === currentUserId
                  return (
                    <li
                      key={member.id}
                      className="plain-list__row plain-list__row--member"
                    >
                      <span className="plain-list__name">{memberName(member)}</span>
                      <span className="mono plain-list__role">
                        {roleLabel(member, isOwner, currentUserId)}
                      </span>
                      <span className="plain-list__actions">
                        {isOwner && !isCurrentUser && member.role === 'org:member' ? (
                          <button
                            type="button"
                            className="button"
                            onClick={() => void handleRole(member, 'org:admin')}
                            disabled={busy}
                          >
                            Promote
                          </button>
                        ) : null}
                        {isOwner && !isCurrentUser && member.role === 'org:admin' ? (
                          <button
                            type="button"
                            className="button"
                            onClick={() => void handleRole(member, 'org:member')}
                            disabled={busy}
                          >
                            Demote
                          </button>
                        ) : null}
                        {!isCurrentUser && memberUserId !== undefined ? (
                          <button
                            type="button"
                            className="button"
                            onClick={() => void handleRemove(member)}
                            disabled={busy}
                          >
                            Remove
                          </button>
                        ) : null}
                      </span>
                    </li>
                  )
                })}
              </ul>

              <h3 id="invitations-title">Pending invitations</h3>
              {pendingInvitations.length === 0 ? <p>No pending invitations.</p> : null}
              <ul className="plain-list" aria-labelledby="invitations-title">
                {pendingInvitations.map((invitation) => (
                  <li key={invitation.id} className="plain-list__row">
                    <span className="mono">{invitation.emailAddress}</span>
                    <button
                      type="button"
                      className="button"
                      onClick={() => void handleRevoke(invitation)}
                      disabled={busy}
                    >
                      Revoke
                    </button>
                  </li>
                ))}
              </ul>
            </section>
          ) : null}

          <section aria-labelledby="leave-organisation-title">
            <h3 id="leave-organisation-title">Leave this organisation</h3>
            {isOwner ? (
              <p>
                You cannot leave an organisation you own. Ownership transfer is not
                available in this phase; delete the organisation instead, and only when
                you own another organisation.
              </p>
            ) : (
              <button
                type="button"
                className="button"
                onClick={() => void handleLeave()}
                disabled={busy || !user}
              >
                Leave organisation
              </button>
            )}
          </section>

          <section aria-labelledby="delete-organisation-title">
            <h3 id="delete-organisation-title">Delete this organisation</h3>
            {isOwner ? (
              anotherOwnedOrganisation ? (
                <button
                  type="button"
                  className="button button--danger"
                  onClick={() => void handleDelete()}
                  disabled={busy}
                >
                  Delete organisation
                </button>
              ) : (
                <p>
                  Deleting is refused because you do not own another organisation that
                  remains.
                </p>
              )
            ) : (
              <p>Only the owner can delete this organisation.</p>
            )}
          </section>

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

          <div className="dialog__actions">
            <button type="button" className="button" onClick={close}>
              Close
            </button>
          </div>
        </div>
      </dialog>
    </>
  )
}
