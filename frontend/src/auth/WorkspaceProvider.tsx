import { Outlet, useMatch } from 'react-router'
import { useAnalyses } from '../api/useAnalyses'
import type { MembershipState, OrganisationRole } from '../api/useMembershipStatus'
import type { WorkspaceContextValue } from './workspaceContext'

/**
 * The analyses list is read once for the rail. The selected analysis card
 * follows the analysis id in the address, so it stays the same when the centre
 * changes section and never falls back to a row the person did not open.
 */
export function WorkspaceProvider({
  apiUrl,
  membership,
  role,
}: {
  apiUrl: string
  membership: MembershipState
  role: OrganisationRole
}) {
  const analyses = useAnalyses(apiUrl, membership === 'member')
  const analysisMatch = useMatch('/projects/:projectId/analyses/:analysisId')
  const selectedAnalysisId = analysisMatch?.params.analysisId ?? null

  const context: WorkspaceContextValue = {
    apiUrl,
    membership,
    role,
    analyses,
    selectedAnalysisId,
  }

  return <Outlet context={context} />
}
