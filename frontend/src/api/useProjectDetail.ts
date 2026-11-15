import { parseProjectDetailResponse } from './projects'
import { useResource } from './useResource'
import type { ProjectDetail } from './projects'
import type { ResourceState } from './useResource'

export function useProjectDetail(
  apiUrl: string,
  enabled: boolean,
  projectId: string | null,
): ResourceState<ProjectDetail> {
  const path = projectId ? `/v1/projects/${encodeURIComponent(projectId)}` : null
  return useResource(apiUrl, enabled, path, parseProjectDetailResponse)
}
