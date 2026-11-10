import { useOrganization } from '@clerk/react'
import { useRef, useState } from 'react'
import type { FormEvent } from 'react'

const MANAGE_MEMBERS_PERMISSION = 'org:sys_memberships:manage'

export function InviteDialog() {
  const { organization, membership } = useOrganization()
  const dialogRef = useRef<HTMLDialogElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)
  const [sending, setSending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [sentTo, setSentTo] = useState<string | null>(null)

  const canInvite = membership?.permissions.includes(MANAGE_MEMBERS_PERMISSION) ?? false
  if (!canInvite || !organization) return null

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
    if (!organization || sending) return

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
      await organization.inviteMember({ emailAddress, role: 'org:member' })
      setSentTo(emailAddress)
      form.reset()
    } catch (inviteError) {
      setError(
        inviteError instanceof Error
          ? inviteError.message
          : 'The invitation could not be sent. Try again.',
      )
    } finally {
      setSending(false)
    }
  }

  return (
    <>
      <button type="button" className="button" onClick={open} aria-haspopup="dialog">
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
          <h2 id="invite-title">Invite a teammate</h2>
          <p id="invite-description">
            Invite someone to <span className="mono">{organization.name}</span> by email. Only team
            admins can invite.
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
