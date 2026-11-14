import { Link, useOutletContext } from 'react-router'
import { latestAnalysisLabel } from '../api/projects'
import type { ProjectSummary } from '../api/projects'
import type { ResourceState } from '../api/useResource'
import type { MembershipState } from '../api/useMembershipStatus'
import { useProjects } from '../api/useProjects'
import type { WorkspaceContextValue } from '../auth/workspaceContext'
import { PageLoading } from '../components/PageLoading'
import { PendingInvitations } from '../components/PendingInvitations'
import { Workspace } from '../components/Workspace'
import { formatUtc } from '../lib/formatDate'
import { isMembershipPending, membershipExplanation } from '../lib/membership'

/**
 * The organisation's projects, in the order the API returned them. Only the
 * name is a link; the latest analysis state and its time read as facts.
 */
export function ProjectTable({ projects }: { projects: ProjectSummary[] }) {
  return (
    <div className="project-table-wrap">
      <table className="project-table">
        <caption className="visually-hidden">Projects</caption>
        <thead>
          <tr>
            <th scope="col">Project</th>
            <th scope="col">Latest analysis</th>
            <th scope="col">Created</th>
          </tr>
        </thead>
        <tbody>
          {projects.map((project) => (
            <tr key={project.id}>
              <td>
                <span className="project-table__project">
                  <Link
                    className="project-table__name mono"
                    to={`/projects/${encodeURIComponent(project.id)}`}
                  >
                    {project.name}
                  </Link>
                  {project.isSample ? (
                    <span className="sample-tag">Sample</span>
                  ) : null}
                </span>
              </td>
              <td className="project-table__state">
                {latestAnalysisLabel(project)}
              </td>
              <td className="project-table__time">
                {project.latestAnalysisCreatedAt === null
                  ? '—'
                  : formatUtc(project.latestAnalysisCreatedAt)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function ProjectTableContent({
  membership,
  projects,
}: {
  membership: MembershipState
  projects: ResourceState<ProjectSummary[]>
}) {
  if (membership !== 'member') {
    const explanation = membershipExplanation(membership)
    return explanation ? (
      <p className="plain-line" role="status">
        {explanation}
      </p>
    ) : null
  }

  if (projects.status === 'idle' || projects.status === 'loading') {
    return <PageLoading />
  }

  if (projects.status === 'error' || projects.status === 'not-found') {
    return (
      <p className="plain-line plain-line--alert" role="alert">
        {projects.status === 'error'
          ? projects.message
          : 'Projects could not be loaded. Try again later.'}
      </p>
    )
  }

  const count = projects.data.length

  return (
    <section className="app-section" aria-labelledby="projects-heading">
      <h1 id="projects-heading" className="section-heading">
        Projects
        <span className="section-heading__count">{count}</span>
      </h1>

      {count === 0 ? (
        <p className="empty-line" role="status">
          No projects for this organisation yet.
        </p>
      ) : (
        <ProjectTable projects={projects.data} />
      )}
    </section>
  )
}

export function ProjectTablePage() {
  const { apiUrl, membership, role, analyses, selectedAnalysisId } =
    useOutletContext<WorkspaceContextValue>()
  const projects = useProjects(apiUrl, membership === 'member')

  if (isMembershipPending(membership)) {
    return (
      <Workspace>
        <PageLoading />
      </Workspace>
    )
  }

  return (
    <Workspace
      membership={membership}
      role={role}
      analyses={analyses}
      selectedAnalysisId={selectedAnalysisId}
    >
      <div className="app-section">
        <PendingInvitations emptyState={false} heading={false} />
        <ProjectTableContent membership={membership} projects={projects} />
      </div>
    </Workspace>
  )
}
