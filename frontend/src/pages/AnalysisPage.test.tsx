import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import type { AnalysisDetail } from '../api/analyses'
import { formatUtc } from '../lib/formatDate'
import { AnalysisFacts } from './AnalysisPage'

const analysis: AnalysisDetail = {
  id: 'analysis_1',
  projectId: 'project_1',
  projectName: 'Aster',
  state: 'complete',
  createdAt: '2026-11-12T10:00:00Z',
  isSample: true,
}

describe('AnalysisFacts', () => {
  it('renders the project name, state label, created time and sample tag', () => {
    const markup = renderToStaticMarkup(<AnalysisFacts analysis={analysis} />)
    expect(markup).toContain('Aster')
    expect(markup).toContain('Complete')
    expect(markup).toContain(formatUtc(analysis.createdAt))
    expect(markup).toContain('Sample')
  })
})
