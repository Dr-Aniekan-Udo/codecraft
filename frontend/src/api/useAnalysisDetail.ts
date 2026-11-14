import { parseAnalysisDetailResponse } from './analyses'
import { useResource } from './useResource'
import type { AnalysisDetail } from './analyses'
import type { ResourceState } from './useResource'

export function useAnalysisDetail(
  apiUrl: string,
  enabled: boolean,
  analysisId: string | null,
): ResourceState<AnalysisDetail> {
  const path = analysisId ? `/v1/analyses/${encodeURIComponent(analysisId)}` : null
  return useResource(apiUrl, enabled, path, parseAnalysisDetailResponse)
}
