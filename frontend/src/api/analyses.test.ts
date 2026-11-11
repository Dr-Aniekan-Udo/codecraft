import { describe, expect, it } from 'vitest'
import { ANALYSIS_STATE_LABELS, parseAnalysesResponse } from './analyses'

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
