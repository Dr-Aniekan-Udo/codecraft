import { ANALYSIS_STATE_LABELS } from '../api/analyses'
import { useAnalyses } from '../api/useAnalyses'
import { MembershipStatus } from '../components/MembershipStatus'

function Analyses({ apiUrl }: { apiUrl: string }) {
  const analyses = useAnalyses(apiUrl)

  return (
    <section className="analyses" aria-labelledby="analyses-title">
      <h2 id="analyses-title" className="analyses__title">
        Analyses
      </h2>

      {analyses.status === 'idle' || analyses.status === 'loading' ? (
        <p className="analyses__message" role="status">
          Loading analyses…
        </p>
      ) : null}

      {analyses.status === 'error' ? (
        <p className="analyses__message analyses__message--error" role="alert">
          {analyses.message}
        </p>
      ) : null}

      {analyses.status === 'ready' && analyses.analyses.length === 0 ? (
        <p className="analyses__message" role="status">
          No analyses for this team yet.
        </p>
      ) : null}

      {analyses.status === 'ready' && analyses.analyses.length > 0 ? (
        <div className="analysis-table-wrap">
          <table className="analysis-table">
            <caption className="visually-hidden">Analyses for the active team</caption>
            <thead>
              <tr>
                <th scope="col">Project</th>
                <th scope="col">State</th>
              </tr>
            </thead>
            <tbody>
              {analyses.analyses.map((analysis) => (
                <tr key={analysis.id}>
                  <td className="analysis-table__project">
                    <span className="mono">{analysis.projectName}</span>
                    {analysis.isSample ? (
                      <span className="analysis-table__sample">Sample</span>
                    ) : null}
                  </td>
                  <td className="analysis-table__state">
                    {ANALYSIS_STATE_LABELS[analysis.state]}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </section>
  )
}

export function HomePage({ apiUrl }: { apiUrl: string }) {
  return (
    <section className="home" aria-labelledby="page-title">
      <h1 id="page-title" className="home__title">
        CodeCraft
      </h1>
      <MembershipStatus apiUrl={apiUrl} />
      <Analyses apiUrl={apiUrl} />
    </section>
  )
}
