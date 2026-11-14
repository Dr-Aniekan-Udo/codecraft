import { useEffect } from 'react'
import { useLocation, useNavigate, useOutletContext } from 'react-router'
import type { AnalysesState } from '../api/useAnalyses'
import type { MembershipState, OrganisationRole } from '../api/useMembershipStatus'
import { usePendingInvitationCount } from '../api/usePendingInvitationCount'
import type { WorkspaceContextValue } from '../auth/workspaceContext'
import { PageLoading } from '../components/PageLoading'
import { PendingInvitations } from '../components/PendingInvitations'
import { Workspace } from '../components/Workspace'
import { isMembershipPending } from '../lib/membership'

function InvitationsWorkspace({
  membership,
  role,
  analyses,
  selectedAnalysisId,
}: {
  membership: MembershipState
  role: OrganisationRole
  analyses: AnalysesState
  selectedAnalysisId: string | null
}) {
  const invitationCount = usePendingInvitationCount()

  return (
    <Workspace
      membership={membership}
      role={role}
      analyses={analyses}
      selectedAnalysisId={selectedAnalysisId}
    >
      <section className="app-section" aria-labelledby="invitations-heading">
        <h1 id="invitations-heading" className="section-heading">
          Invitations
          {invitationCount !== null && invitationCount > 0 ? (
            <span className="section-heading__count">{invitationCount}</span>
          ) : null}
        </h1>

        <PendingInvitations emptyState />
      </section>
    </Workspace>
  )
}

export function InvitationsPage() {
  const location = useLocation()
  const navigate = useNavigate()
  const { membership, role, analyses, selectedAnalysisId } =
    useOutletContext<WorkspaceContextValue>()

  useEffect(() => {
    // The invitation ticket is deliberately not consumed. Seeing the invitation
    // must not add the person to the organisation; the Accept button is the only path.
    if (
      location.search.includes('__clerk_ticket') ||
      location.search.includes('__clerk_status')
    ) {
      navigate(location.pathname, { replace: true })
    }
  }, [location.pathname, location.search, navigate])

  if (isMembershipPending(membership)) {
    return (
      <Workspace>
        <PageLoading />
      </Workspace>
    )
  }

  return (
    <InvitationsWorkspace
      membership={membership}
      role={role}
      analyses={analyses}
      selectedAnalysisId={selectedAnalysisId}
    />
  )
}
