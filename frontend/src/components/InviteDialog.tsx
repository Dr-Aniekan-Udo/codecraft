import { useAuth, useOrganization } from '@clerk/react'
import { useRef, useState } from 'react'
import type { FormEvent } from 'react'
import type { OrganisationRole } from '../api/useMembershipStatus'

export function InviteDialog({
  apiUrl,
  role,
}: {
  apiUrl: string
  role: OrganisationRole
}) {
  // Clerk's API uses the US spelling 'organization'; the application's domain
  // term is 'organisation'.
  const { organization: activeOrganisation } = useOrganization()
  const { getToken } = useAuth()
  const dialogRef = useRef<HTMLDialogElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)
  const [sending, setSending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [sentTo, setSentTo] = useState<string | null>(null)

  // The API reported this role for the verified token; Clerk's permission
  // value is not used for the active organisation's role.
  const canInvite = role === 'admin'
  if (!canInvite || !activeOrganisation) return null

  function reset(): void {
    setError(null)
    setSentTo(null)
    setSending(false)
  }

  function open(): void {
    reset()
    dialogRef.current?.showModal()
    inputRef.current?.focus()
  }

  function close(): void {
    dialogRef.current?.close()
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!activeOrganisation || sending) return

    const form = event.currentTarget
    const emailValue = new FormData(form).get('email')
    const emailAddress = typeof emailValue === 'string' ? emailValue.trim() : ''

    if (!emailAddress) {
      setError('Enter an email address.')
      return
    }

    setSending(true)
    setError(null)
    setSentTo(null)

    try {
      const token = await getToken({
        organizationId: activeOrganisation.id,
        skipCache: true,
      })
      if (!token) {
        setError('Your session could not be read. Reload the page and try again.')
        return
      }

      const response = await fetch(`${apiUrl}/v1/invitations`, {
        method: 'POST',
        headers: {
          Accept: 'application/json',
          Authorization: `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          organisation_id: activeOrganisation.id,
          email_address: emailAddress,
        }),
      })

      if (response.status === 403) {
        setError('Only organisation admins can invite someone.')
        return
      }
      if (response.status === 422) {
        setError('That email address could not be invited.')
        return
      }
      if (!response.ok) {
        setError('The invitation could not be sent. Try again.')
        return
      }

      setSentTo(emailAddress)
      form.reset()
    } catch {
      setError('The invitation could not be sent. Try again.')
    } finally {
      setSending(false)
    }
  }

  return (
    <>
      <button
        type="button"
        className="header-invite"
        onClick={open}
        aria-haspopup="dialog"
      >
        Invite
      </button>
      <dialog
        ref={dialogRef}
        className="dialog"
        aria-labelledby="invite-title"
        aria-describedby="invite-description"
        onClose={reset}
      >
        <form className="dialog__form" onSubmit={(event) => void handleSubmit(event)}>
          <h2 id="invite-title">Invite a member</h2>
          <p id="invite-description">
            Invite someone to <span className="mono">{activeOrganisation.name}</span> by
            email. Only organisation admins can invite.
          </p>

          <div className="field">
            <label className="field__label" htmlFor="invite-email">
              Email address
            </label>
            <input
              ref={inputRef}
              id="invite-email"
              className="input"
              name="email"
              type="email"
              autoComplete="email"
              required
            />
          </div>

          {error ? (
            <p className="inline-message" role="alert">
              {error}
            </p>
          ) : null}
          {sentTo ? (
            <p className="inline-message inline-message--success" role="status">
              Invitation sent to <span className="mono">{sentTo}</span>.
            </p>
          ) : null}

          <div className="dialog__actions">
            <button type="button" className="button" onClick={close}>
              {sentTo ? 'Close' : 'Cancel'}
            </button>
            <button type="submit" className="button button--primary" disabled={sending}>
              {sending ? 'Sending…' : 'Send invitation'}
            </button>
          </div>
        </form>
      </dialog>
    </>
  )
}
