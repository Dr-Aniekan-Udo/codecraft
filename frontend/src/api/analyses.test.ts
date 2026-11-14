import { describe, expect, it } from 'vitest'
import {
  ANALYSIS_STATE_LABELS,
  parseAnalysesResponse,
  parseAnalysisDetailResponse,
} from './analyses'

const completeAnalysis = {
  id: 'analysis_1',
  project_name: 'codecraft',
  state: 'complete',
  created_at: '2026-11-10T12:00:00Z',
  is_sample: true,
}

describe('parseAnalysesResponse', () => {
  it('maps the response fields and keeps the sample marker', () => {
    expect(parseAnalysesResponse({ analyses: [completeAnalysis] })).toEqual([
      {
        id: 'analysis_1',
        projectName: 'codecraft',
        state: 'complete',
        isSample: true,
      },
    ])
  })

  it('accepts an empty list', () => {
    expect(parseAnalysesResponse({ analyses: [] })).toEqual([])
  })

  it('ignores fields the page does not display', () => {
    expect(
      parseAnalysesResponse({
        analyses: [
          {
            id: 'analysis_2',
            project_name: 'other-project',
            state: 'queued',
            created_at: '2026-11-10T12:00:00Z',
            is_sample: false,
            extra: 'ignored',
          },
        ],
        extra: 'ignored',
      }),
    ).toEqual([
      {
        id: 'analysis_2',
        projectName: 'other-project',
        state: 'queued',
        isSample: false,
      },
    ])
  })

  it('rejects a body without an analyses list', () => {
    expect(() => parseAnalysesResponse({})).toThrow()
    expect(() => parseAnalysesResponse(null)).toThrow()
    expect(() => parseAnalysesResponse({ analyses: {} })).toThrow()
  })

  it('rejects a row with an unknown state', () => {
    expect(() =>
      parseAnalysesResponse({ analyses: [{ ...completeAnalysis, state: 'stale' }] }),
    ).toThrow()
  })

  it('rejects a row with missing or blank fields', () => {
    expect(() =>
      parseAnalysesResponse({ analyses: [{ ...completeAnalysis, id: '' }] }),
    ).toThrow()
    expect(() =>
      parseAnalysesResponse({ analyses: [{ ...completeAnalysis, project_name: '  ' }] }),
    ).toThrow()
    expect(() =>
      parseAnalysesResponse({ analyses: [{ ...completeAnalysis, is_sample: null }] }),
    ).toThrow()
  })
})

describe('parseAnalysisDetailResponse', () => {
  const analysisDetail = {
    id: 'analysis_1',
    project_id: 'project_1',
    project_name: 'Aster',
    state: 'complete',
    created_at: '2026-11-10T12:05:00Z',
    is_sample: true,
  }

  it('maps the response fields and keeps the sample marker', () => {
    expect(parseAnalysisDetailResponse({ analysis: analysisDetail })).toEqual({
      id: 'analysis_1',
      projectId: 'project_1',
      projectName: 'Aster',
      state: 'complete',
      createdAt: '2026-11-10T12:05:00Z',
      isSample: true,
    })
  })

  it('ignores fields the page does not display', () => {
    expect(
      parseAnalysisDetailResponse({
        analysis: { ...analysisDetail, extra: 'ignored' },
        extra: 'ignored',
      }),
    ).toEqual({
      id: 'analysis_1',
      projectId: 'project_1',
      projectName: 'Aster',
      state: 'complete',
      createdAt: '2026-11-10T12:05:00Z',
      isSample: true,
    })
  })

  it('rejects a body without an analysis object', () => {
    expect(() => parseAnalysisDetailResponse({})).toThrow()
    expect(() => parseAnalysisDetailResponse(null)).toThrow()
    expect(() => parseAnalysisDetailResponse({ analysis: null })).toThrow()
  })

  it('rejects missing or blank fields', () => {
    expect(() =>
      parseAnalysisDetailResponse({ analysis: { ...analysisDetail, id: '' } }),
    ).toThrow()
    expect(() =>
      parseAnalysisDetailResponse({ analysis: { ...analysisDetail, project_id: '  ' } }),
    ).toThrow()
    expect(() =>
      parseAnalysisDetailResponse({ analysis: { ...analysisDetail, project_name: '' } }),
    ).toThrow()
    expect(() =>
      parseAnalysisDetailResponse({ analysis: { ...analysisDetail, is_sample: null } }),
    ).toThrow()
  })

  it('rejects an invalid creation time', () => {
    expect(() =>
      parseAnalysisDetailResponse({
        analysis: { ...analysisDetail, created_at: 'not-a-date' },
      }),
    ).toThrow()
  })

  it('rejects an unknown state', () => {
    expect(() =>
      parseAnalysisDetailResponse({ analysis: { ...analysisDetail, state: 'stale' } }),
    ).toThrow()
  })
})

describe('ANALYSIS_STATE_LABELS', () => {
  it('labels all four states as text', () => {
    expect(ANALYSIS_STATE_LABELS).toEqual({
      queued: 'Queued',
      running: 'Running',
      complete: 'Complete',
      failed: 'Failed',
    })
  })
})
