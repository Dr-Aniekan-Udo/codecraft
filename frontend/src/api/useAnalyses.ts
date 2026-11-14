import { useAuth } from '@clerk/react'
import { parseAnalysesResponse } from './analyses'
import { useResource, UNAVAILABLE_MESSAGE } from './useResource'
import type { AnalysisSummary } from './analyses'

export type AnalysesState =
  | { status: 'idle' }
  | { status: 'loading' }
  | { status: 'ready'; analyses: AnalysisSummary[] }
  | { status: 'error'; message: string }

/**
 * The active organisation is a query parameter, not a client-side filter. The
 * shared resource hook mints the token for that organisation and owns the
 * request lifecycle.
 */
export function useAnalyses(apiUrl: string, enabled: boolean): AnalysesState {
  const { orgId: activeOrganisationId } = useAuth()
  const path = activeOrganisationId
    ? `/v1/analyses?organisation_id=${encodeURIComponent(activeOrganisationId)}`
    : null
  const resource = useResource(apiUrl, enabled, path, parseAnalysesResponse)

  switch (resource.status) {
    case 'idle':
      return { status: 'idle' }
    case 'loading':
      return { status: 'loading' }
    case 'ready':
      return { status: 'ready', analyses: resource.data }
    case 'not-found':
      // The analyses list route does not return 404; treat it as a load failure.
      return { status: 'error', message: UNAVAILABLE_MESSAGE }
    case 'error':
      return { status: 'error', message: resource.message }
  }
}
