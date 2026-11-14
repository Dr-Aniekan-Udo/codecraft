import { useAuth } from '@clerk/react'
import { parseProjectsResponse } from './projects'
import { useResource } from './useResource'
import type { ProjectSummary } from './projects'
import type { ResourceState } from './useResource'

export function useProjects(
  apiUrl: string,
  enabled: boolean,
): ResourceState<ProjectSummary[]> {
  // Clerk's API uses the US spelling 'organization'; the application's domain
  // term is 'organisation'.
  const { orgId: activeOrganisationId } = useAuth()
  const path = activeOrganisationId
    ? `/v1/projects?organisation_id=${encodeURIComponent(activeOrganisationId)}`
    : null
  return useResource(apiUrl, enabled, path, parseProjectsResponse)
}
