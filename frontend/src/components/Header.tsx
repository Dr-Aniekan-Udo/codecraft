import { UserButton, useAuth, useOrganization, useUser } from '@clerk/react'
import { useState } from 'react'
import { Link } from 'react-router'
import type { MembershipState, OrganisationRole } from '../api/useMembershipStatus'
import { usePendingInvitationCount } from '../api/usePendingInvitationCount'
import { InviteDialog } from '../components/InviteDialog'
import { OrganisationMenu } from '../components/OrganisationMenu'
import { OrganisationSwitcher } from '../components/OrganisationSwitcher'
import { ThemeControl } from '../components/ThemeControl'
import { resolveOrganisationName } from '../lib/identity'
import { isMembershipPending } from '../lib/membership'

function InvitationsControl() {
  const count = usePendingInvitationCount()
  const label =
    count === null
      ? 'Invitations'
      : count === 0
        ? 'Invitations, none pending'
        : `Invitations, ${count} pending`

  return (
    <Link
      className="icon-button"
      to="/invitations"
      aria-label={label}
      title={label}
    >
      <svg
        viewBox="0 0 16 16"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.2"
        aria-hidden="true"
        focusable="false"
      >
        <rect x="2" y="3.5" width="12" height="9" rx="1" />
        <path d="M2.5 4.5 8 8.5l5.5-4" />
      </svg>
      {count !== null && count > 0 ? (
        <span className="icon-badge" aria-hidden="true">
          {count}
        </span>
      ) : null}
    </Link>
  )
}

export function Header({
  apiUrl,
  membership,
  role,
}: {
  apiUrl: string
  membership: MembershipState
  role: OrganisationRole
}) {
  const { isLoaded, sessionClaims } = useAuth()
  const { isLoaded: userLoaded } = useUser()
  // The account control needs the user object as well as the session. Holding
  // the whole action row until both are ready makes every action appear together.
  const controlsReady = isLoaded && userLoaded
  // Clerk's API uses the US spelling 'organization'; the application's domain
  // term is 'organisation'.
  const { organization: activeOrganisation } = useOrganization()
  const [renamedName, setRenamedName] = useState<string | null>(null)
  const isMember = membership === 'member'
  const isPending = isMembershipPending(membership)
  const activeName = activeOrganisation?.name.trim()
  const organisationName = isMember
    ? (renamedName ??
      (activeName ? activeName : null) ??
      resolveOrganisationName(sessionClaims))
    : null
  const organisationControlVisible = isLoaded && !isPending

  return (
    <header className="app-header">
      <span className="app-brand">CodeCraft</span>

      {organisationControlVisible ? (
        <OrganisationSwitcher
          organisationName={organisationName}
          showOrganisationNames={isMember}
        />
      ) : (
        <span className="org-switcher org-switcher--placeholder" aria-hidden="true" />
      )}

      {/* The action row stays laid out before Clerk has loaded, but invisible,
          so the header keeps its height and every action appears together. */}
      <div
        className={
          controlsReady
            ? 'app-header__actions'
            : 'app-header__actions app-header__actions--pending'
        }
      >
        <InvitationsControl />
        {isMember ? (
          <OrganisationMenu apiUrl={apiUrl} onRenamed={setRenamedName} />
        ) : null}
        <ThemeControl />
        <UserButton />
        {isMember ? <InviteDialog apiUrl={apiUrl} role={role} /> : null}
      </div>
    </header>
  )
}
