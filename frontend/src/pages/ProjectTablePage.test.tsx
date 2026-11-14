import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router'
import { describe, expect, it } from 'vitest'
import type { ProjectSummary } from '../api/projects'
import { ProjectTable } from './ProjectTablePage'

const projects: ProjectSummary[] = [
  {
    id: 'project_2',
    name: 'Zeta service',
    createdAt: '2026-11-12T08:00:00Z',
    isSample: false,
    latestAnalysisState: 'complete',
    latestAnalysisCreatedAt: '2026-11-12T09:30:00Z',
  },
  {
    id: 'project_1',
    name: 'Alpha service',
    createdAt: '2026-11-10T08:00:00Z',
    isSample: true,
    latestAnalysisState: null,
    latestAnalysisCreatedAt: null,
  },
]

function projectTableMarkup(): string {
  return renderToStaticMarkup(
    <MemoryRouter>
      <ProjectTable projects={projects} />
    </MemoryRouter>,
  )
}

describe('ProjectTable', () => {
  it('renders the Project, Latest analysis and Created headers', () => {
    const markup = projectTableMarkup()
    expect(markup).toContain('>Project<')
    expect(markup).toContain('>Latest analysis<')
    expect(markup).toContain('>Created<')
  })

  it('shows the latest analysis state as text for a project that has one', () => {
    expect(projectTableMarkup()).toContain('Complete')
  })

  it('says No analyses for a project without an analysis', () => {
    expect(projectTableMarkup()).toContain('No analyses')
  })

  it('keeps the project names in the order the API returned them', () => {
    const markup = projectTableMarkup()
    expect(markup.indexOf('Zeta service')).toBeLessThan(
      markup.indexOf('Alpha service'),
    )
  })
})
