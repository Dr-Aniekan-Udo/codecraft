import { useOutletContext, useParams } from 'react-router'
import { ANALYSIS_STATE_LABELS } from '../api/analyses'
import type { AnalysisDetail } from '../api/analyses'
import type { ResourceState } from '../api/useResource'
import type { MembershipState } from '../api/useMembershipStatus'
import { useAnalysisDetail } from '../api/useAnalysisDetail'
import type { WorkspaceContextValue } from '../auth/workspaceContext'
import { NotFoundMessage } from '../components/NotFoundMessage'
import { PageLoading } from '../components/PageLoading'
import { Workspace } from '../components/Workspace'
import { formatUtc } from '../lib/formatDate'
import { isMembershipPending, membershipExplanation } from '../lib/membership'

/**
 * The analysis facts the API reports. There is no graph, map or placeholder
 * here; this phase shows only what the analysis record says.
 */
export function AnalysisFacts({ analysis }: { analysis: AnalysisDetail }) {
  return (
    <section className="app-section" aria-labelledby="analysis-heading">
      <h1 id="analysis-heading" className="section-heading">
        <span className="mono">{analysis.projectName}</span>
        {analysis.isSample ? (
          <span className="sample-tag">Sample</span>
        ) : null}
      </h1>

      <dl className="analysis-facts">
        <div className="analysis-fact">
          <dt>State</dt>
          <dd>{ANALYSIS_STATE_LABELS[analysis.state]}</dd>
        </div>
        <div className="analysis-fact">
          <dt>Created</dt>
          <dd className="mono">{formatUtc(analysis.createdAt)}</dd>
        </div>
      </dl>
    </section>
  )
}

function AnalysisContent({
  membership,
  projectId,
  analysis,
}: {
  membership: MembershipState
  projectId: string | undefined
  analysis: ResourceState<AnalysisDetail>
}) {
  if (membership !== 'member') {
    const explanation = membershipExplanation(membership)
    return explanation ? (
      <p className="plain-line" role="status">
        {explanation}
      </p>
    ) : null
  }

  if (analysis.status === 'idle' || analysis.status === 'loading') {
    return <PageLoading />
  }

  if (analysis.status === 'not-found') {
    return <NotFoundMessage />
  }

  if (analysis.status === 'error') {
    return (
      <p className="plain-line plain-line--alert" role="alert">
        {analysis.message}
      </p>
    )
  }

  // The analysis must belong to the project named in the address. A record
  // that answers for another project is treated like a missing page.
  if (analysis.data.projectId !== projectId) {
    return <NotFoundMessage />
  }

  return <AnalysisFacts analysis={analysis.data} />
}

export function AnalysisPage() {
  const { projectId, analysisId } = useParams()
  const { apiUrl, membership, role, analyses, selectedAnalysisId } =
    useOutletContext<WorkspaceContextValue>()
  const analysis = useAnalysisDetail(
    apiUrl,
    membership === 'member',
    analysisId ?? null,
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
      <AnalysisContent
        membership={membership}
        projectId={projectId}
        analysis={analysis}
      />
    </Workspace>
  )
}
