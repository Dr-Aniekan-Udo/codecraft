import type { AnalysesState } from '../api/useAnalyses'
import type {
  MembershipState,
  OrganisationRole,
} from '../api/useMembershipStatus'

export type WorkspaceContextValue = {
  apiUrl: string
  membership: MembershipState
  role: OrganisationRole
  analyses: AnalysesState
  selectedAnalysisId: string | null
}
