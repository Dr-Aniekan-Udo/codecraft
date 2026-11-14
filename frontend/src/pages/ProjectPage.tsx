import { Link, useOutletContext, useParams } from 'react-router'
import { ANALYSIS_STATE_LABELS } from '../api/analyses'
import type { ProjectDetail } from '../api/projects'
import type { ResourceState } from '../api/useResource'
import type { MembershipState } from '../api/useMembershipStatus'
import { useProjectDetail } from '../api/useProjectDetail'
import type { WorkspaceContextValue } from '../auth/workspaceContext'
import { NotFoundMessage } from '../components/NotFoundMessage'
import { PageLoading } from '../components/PageLoading'
import { Workspace } from '../components/Workspace'
import { formatUtc } from '../lib/formatDate'
import { isMembershipPending, membershipExplanation } from '../lib/membership'

/**
 * The project's analyses stay exactly in the order the API returned them,
 * newest first. Each row opens that analysis in the workspace.
 */
export function ProjectAnalyses({ detail }: { detail: ProjectDetail }) {
  return (
    <section className="app-section" aria-labelledby="project-heading">
      <h1 id="project-heading" className="section-heading">
        <span className="mono">{detail.project.name}</span>
        {detail.project.isSample ? (
          <span className="sample-tag">Sample</span>
        ) : null}
      </h1>

      {detail.analyses.length === 0 ? (
        <p className="empty-line" role="status">
          No analyses for this project yet.
        </p>
      ) : (
        <ul className="analysis-list" aria-label="Analyses">
          {detail.analyses.map((analysis) => (
            <li key={analysis.id}>
              <Link
                className="analysis-row analysis-row--link"
                to={`/projects/${encodeURIComponent(detail.project.id)}/analyses/${encodeURIComponent(analysis.id)}`}
              >
                <span className="analysis-row__name mono">
                  {formatUtc(analysis.createdAt)}
                </span>
                {analysis.isSample ? (
                  <span className="sample-tag">Sample</span>
                ) : null}
                <span className="analysis-row__state">
                  {ANALYSIS_STATE_LABELS[analysis.state]}
                </span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}

function ProjectContent({
  membership,
  detail,
}: {
  membership: MembershipState
  detail: ResourceState<ProjectDetail>
}) {
  if (membership !== 'member') {
    const explanation = membershipExplanation(membership)
    return explanation ? (
      <p className="plain-line" role="status">
        {explanation}
      </p>
    ) : null
  }

  if (detail.status === 'idle' || detail.status === 'loading') {
    return <PageLoading />
  }

  if (detail.status === 'not-found') {
    return <NotFoundMessage />
  }

  if (detail.status === 'error') {
    return (
      <p className="plain-line plain-line--alert" role="alert">
        {detail.message}
      </p>
    )
  }

  return <ProjectAnalyses detail={detail.data} />
}

export function ProjectPage() {
  const { projectId } = useParams()
  const { apiUrl, membership, role, analyses, selectedAnalysisId } =
    useOutletContext<WorkspaceContextValue>()
  const detail = useProjectDetail(
    apiUrl,
    membership === 'member',
    projectId ?? null,
  )

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
      <ProjectContent membership={membership} detail={detail} />
    </Workspace>
  )
}
