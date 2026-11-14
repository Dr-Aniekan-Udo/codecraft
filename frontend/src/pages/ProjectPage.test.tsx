import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router'
import { describe, expect, it } from 'vitest'
import type { ProjectDetail } from '../api/projects'
import { formatUtc } from '../lib/formatDate'
import { ProjectAnalyses } from './ProjectPage'

const detail: ProjectDetail = {
  project: {
    id: 'project_1',
    name: 'Aster',
    createdAt: '2026-11-10T08:00:00Z',
    isSample: true,
  },
  analyses: [
    {
      id: 'analysis_2',
      state: 'complete',
      createdAt: '2026-11-12T10:00:00Z',
      isSample: true,
    },
    {
      id: 'analysis_1',
      state: 'failed',
      createdAt: '2026-11-11T10:00:00Z',
      isSample: false,
    },
  ],
}

function projectAnalysesMarkup(): string {
  return renderToStaticMarkup(
    <MemoryRouter>
      <ProjectAnalyses detail={detail} />
    </MemoryRouter>,
  )
}

describe('ProjectAnalyses', () => {
  it('renders the analyses in the newest-first order the API returned', () => {
    const markup = projectAnalysesMarkup()
    const newer = formatUtc('2026-11-12T10:00:00Z')
    const older = formatUtc('2026-11-11T10:00:00Z')
    expect(markup.indexOf(newer)).toBeLessThan(markup.indexOf(older))
  })

  it('shows each analysis state as text', () => {
    const markup = projectAnalysesMarkup()
    expect(markup).toContain('Complete')
    expect(markup).toContain('Failed')
  })
})
