import type { ReactNode } from 'react'
import { ANALYSIS_STATE_LABELS } from '../api/analyses'
import type { AnalysesState } from '../api/useAnalyses'
import type { MembershipState, OrganisationRole } from '../api/useMembershipStatus'
import { useWorkspaceIdentity } from '../auth/useWorkspaceIdentity'
import { isMembershipPending } from '../lib/membership'

type FinalMembership = Exclude<MembershipState, 'idle' | 'checking'>

const MEMBERSHIP_FACTS: Record<
  FinalMembership,
  { label: string; shape: 'filled' | 'half' | 'outlined' }
> = {
  member: { label: 'Confirmed', shape: 'filled' },
  syncing: { label: 'Syncing', shape: 'half' },
  forbidden: { label: 'No access', shape: 'outlined' },
  unavailable: { label: 'Could not confirm', shape: 'outlined' },
}

function finalMembership(state: MembershipState | undefined): FinalMembership | null {
  if (state === undefined || isMembershipPending(state)) return null
  return state
}

function MembershipFact({ state }: { state: FinalMembership }) {
  const fact = MEMBERSHIP_FACTS[state]

  return (
    <span className="membership-fact" data-shape={fact.shape}>
      <span className="membership-fact__mark" aria-hidden="true" />
      <span>{fact.label}</span>
    </span>
  )
}

function AnalysisRail({
  analyses,
  selectedAnalysisId,
}: {
  analyses: AnalysesState | undefined
  selectedAnalysisId: string | null | undefined
}) {
  const count =
    analyses?.status === 'ready' ? analyses.analyses.length : undefined
  const selected =
    analyses?.status === 'ready' && selectedAnalysisId !== null
      ? (analyses.analyses.find(
          (analysis) => analysis.id === selectedAnalysisId,
        ) ?? null)
      : null

  return (
    <>
      <p className="rail-label">
        <span>Analysis</span>
        {count !== undefined ? (
          <span className="rail-label__count">{count}</span>
        ) : null}
      </p>

      {selected ? (
        <div className="rail-card">
          <p className="rail-card__name mono">{selected.projectName}</p>
          <p className="rail-card__meta">
            <span>{ANALYSIS_STATE_LABELS[selected.state]}</span>
            {selected.isSample ? (
              <span className="sample-tag">Sample</span>
            ) : null}
          </p>
        </div>
      ) : (
        <p className="rail-empty">No analysis selected</p>
      )}

      <p className="rail-note">Switch in the centre list</p>
    </>
  )
}

/**
 * The signed-in shell: a context rail, the active section, and the detail pane.
 * The grid is defined once so loading and final states have the same rects.
 */
export function Workspace({
  membership,
  role,
  analyses,
  selectedAnalysisId,
  children,
}: {
  membership?: MembershipState
  role?: OrganisationRole
  analyses?: AnalysesState
  selectedAnalysisId?: string | null
  children: ReactNode
}) {
  const confirmed = finalMembership(membership)
  const contextReady = membership !== undefined && !isMembershipPending(membership)
  const { organisationName, role: roleLabel } = useWorkspaceIdentity(
    membership ?? 'idle',
    role ?? null,
  )

  return (
    <div className="workspace">
      <aside
        className="app-rail"
        aria-label={contextReady ? 'Analysis context' : undefined}
      >
        {contextReady ? (
          <AnalysisRail
            analyses={analyses}
            selectedAnalysisId={selectedAnalysisId}
          />
        ) : null}
      </aside>

      <main id="main-content" className="app-main" tabIndex={0}>
        {children}
      </main>

      <aside
        className="app-pane"
        aria-labelledby={confirmed ? 'overview-title' : undefined}
      >
        {confirmed ? (
          <>
            <h2 id="overview-title" className="pane__label">
              Overview
            </h2>
            <dl className="pane__facts">
              {organisationName ? (
                <div className="pane__row">
                  <dt>Organisation</dt>
                  <dd className="mono">{organisationName}</dd>
                </div>
              ) : null}
              {roleLabel ? (
                <div className="pane__row">
                  <dt>Your role</dt>
                  <dd>{roleLabel}</dd>
                </div>
              ) : null}
              <div className="pane__row">
                <dt>Membership</dt>
                <dd>
                  <MembershipFact state={confirmed} />
                </dd>
              </div>
            </dl>
          </>
        ) : null}
      </aside>
    </div>
  )
}
