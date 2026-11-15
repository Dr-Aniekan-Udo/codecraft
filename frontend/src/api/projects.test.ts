import { describe, expect, it } from 'vitest'
import { latestAnalysisLabel, parseProjectDetailResponse, parseProjectsResponse } from './projects'
import type { ProjectSummary } from './projects'

const projectSummary = {
  id: 'project_1',
  name: 'Aster',
  created_at: '2026-11-10T12:00:00Z',
  is_sample: true,
  latest_analysis_state: 'complete',
  latest_analysis_created_at: '2026-11-10T12:05:00Z',
}

const projectDetail = {
  id: 'project_1',
  name: 'Aster',
  created_at: '2026-11-10T12:00:00Z',
  is_sample: true,
}

const projectAnalysis = {
  id: 'analysis_1',
  state: 'complete',
  created_at: '2026-11-10T12:05:00Z',
  is_sample: true,
}

describe('parseProjectsResponse', () => {
  it('maps the response fields and keeps the latest analysis', () => {
    expect(parseProjectsResponse({ projects: [projectSummary] })).toEqual([
      {
        id: 'project_1',
        name: 'Aster',
        createdAt: '2026-11-10T12:00:00Z',
        isSample: true,
        latestAnalysisState: 'complete',
        latestAnalysisCreatedAt: '2026-11-10T12:05:00Z',
      },
    ])
  })

  it('accepts a project with both latest analysis fields null', () => {
    expect(
      parseProjectsResponse({
        projects: [
          {
            ...projectSummary,
            latest_analysis_state: null,
            latest_analysis_created_at: null,
          },
        ],
      }),
    ).toEqual([
      {
        id: 'project_1',
        name: 'Aster',
        createdAt: '2026-11-10T12:00:00Z',
        isSample: true,
        latestAnalysisState: null,
        latestAnalysisCreatedAt: null,
      },
    ])
  })

  it('accepts a project with both latest analysis fields present', () => {
    const [project] = parseProjectsResponse({ projects: [projectSummary] })
    expect(project?.latestAnalysisState).toBe('complete')
    expect(project?.latestAnalysisCreatedAt).toBe('2026-11-10T12:05:00Z')
  })

  it('preserves the order the API returned, newest first', () => {
    const projects = parseProjectsResponse({
      projects: [
        projectSummary,
        {
          ...projectSummary,
          id: 'project_2',
          name: 'Older',
          created_at: '2026-11-01T12:00:00Z',
        },
      ],
    })
    expect(projects.map((project) => project.id)).toEqual(['project_1', 'project_2'])
  })

  it('accepts an empty list', () => {
    expect(parseProjectsResponse({ projects: [] })).toEqual([])
  })

  it('rejects a body without a projects list', () => {
    expect(() => parseProjectsResponse({})).toThrow()
    expect(() => parseProjectsResponse(null)).toThrow()
    expect(() => parseProjectsResponse({ projects: {} })).toThrow()
  })

  it('rejects a project with only one latest analysis field', () => {
    expect(() =>
      parseProjectsResponse({
        projects: [{ ...projectSummary, latest_analysis_created_at: null }],
      }),
    ).toThrow()
    expect(() =>
      parseProjectsResponse({
        projects: [{ ...projectSummary, latest_analysis_state: null }],
      }),
    ).toThrow()
  })

  it('rejects a project with an unknown latest analysis state', () => {
    expect(() =>
      parseProjectsResponse({
        projects: [{ ...projectSummary, latest_analysis_state: 'stale' }],
      }),
    ).toThrow()
  })

  it('rejects a project with blank id or name', () => {
    expect(() =>
      parseProjectsResponse({ projects: [{ ...projectSummary, id: '' }] }),
    ).toThrow()
    expect(() =>
      parseProjectsResponse({ projects: [{ ...projectSummary, name: '  ' }] }),
    ).toThrow()
  })

  it('rejects a project with an invalid creation or latest analysis time', () => {
    expect(() =>
      parseProjectsResponse({
        projects: [{ ...projectSummary, created_at: 'not-a-date' }],
      }),
    ).toThrow()
    expect(() =>
      parseProjectsResponse({
        projects: [{ ...projectSummary, latest_analysis_created_at: 'not-a-date' }],
      }),
    ).toThrow()
  })

  it('rejects a project without a boolean sample marker', () => {
    expect(() =>
      parseProjectsResponse({ projects: [{ ...projectSummary, is_sample: null }] }),
    ).toThrow()
  })
})

describe('parseProjectDetailResponse', () => {
  it('maps the project and its analyses', () => {
    expect(
      parseProjectDetailResponse({
        project: projectDetail,
        analyses: [projectAnalysis],
      }),
    ).toEqual({
      project: {
        id: 'project_1',
        name: 'Aster',
        createdAt: '2026-11-10T12:00:00Z',
        isSample: true,
      },
      analyses: [
        {
          id: 'analysis_1',
          state: 'complete',
          createdAt: '2026-11-10T12:05:00Z',
          isSample: true,
        },
      ],
    })
  })

  it('rejects a missing project', () => {
    expect(() => parseProjectDetailResponse({ analyses: [] })).toThrow()
    expect(() => parseProjectDetailResponse({ project: null, analyses: [] })).toThrow()
  })

  it('rejects missing or invalid analysis rows', () => {
    expect(() =>
      parseProjectDetailResponse({ project: projectDetail, analyses: {} }),
    ).toThrow()
    expect(() =>
      parseProjectDetailResponse({
        project: projectDetail,
        analyses: [{ ...projectAnalysis, state: 'stale' }],
      }),
    ).toThrow()
    expect(() =>
      parseProjectDetailResponse({
        project: projectDetail,
        analyses: [{ ...projectAnalysis, created_at: 'not-a-date' }],
      }),
    ).toThrow()
  })
})

describe('latestAnalysisLabel', () => {
  const summary = (latestAnalysisState: ProjectSummary['latestAnalysisState']): ProjectSummary => ({
    id: 'project_1',
    name: 'Aster',
    createdAt: '2026-11-10T12:00:00Z',
    isSample: true,
    latestAnalysisState,
    latestAnalysisCreatedAt:
      latestAnalysisState === null ? null : '2026-11-10T12:05:00Z',
  })

  it('labels the latest analysis state as text', () => {
    expect(latestAnalysisLabel(summary('queued'))).toBe('Queued')
    expect(latestAnalysisLabel(summary('running'))).toBe('Running')
    expect(latestAnalysisLabel(summary('complete'))).toBe('Complete')
    expect(latestAnalysisLabel(summary('failed'))).toBe('Failed')
  })

  it('says there are no analyses when the latest state is null', () => {
    expect(latestAnalysisLabel(summary(null))).toBe('No analyses')
  })
})
