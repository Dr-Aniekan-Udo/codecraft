import { UserButton, useAuth } from '@clerk/react'
import { InviteDialog } from '../components/InviteDialog'
import { TeamSwitcher } from '../components/TeamSwitcher'
import { ThemeControl } from '../components/ThemeControl'
import { resolveTeamName } from '../lib/identity'

export function Header() {
  const { orgId, sessionClaims } = useAuth()
  const teamName = resolveTeamName(sessionClaims, orgId)

  return (
    <header className="app-header">
      <p className="team-name" title={teamName}>
        <span className="visually-hidden">Current team: </span>
        {teamName}
      </p>
      <div className="app-header__controls">
        <TeamSwitcher />
        <InviteDialog />
        <ThemeControl />
        <UserButton />
      </div>
    </header>
  )
}
