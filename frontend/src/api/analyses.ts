export const ANALYSIS_STATES = ['queued', 'running', 'complete', 'failed'] as const

export type AnalysisState = (typeof ANALYSIS_STATES)[number]

export const ANALYSIS_STATE_LABELS: Record<AnalysisState, string> = {
  queued: 'Queued',
  running: 'Running',
  complete: 'Complete',
  failed: 'Failed',
}

export type AnalysisSummary = {
  id: string
  projectName: string
  state: AnalysisState
  isSample: boolean
}

export type AnalysisDetail = {
  id: string
  projectId: string
  projectName: string
  state: AnalysisState
  createdAt: string
  isSample: boolean
}

const stateSet = new Set<string>(ANALYSIS_STATES)

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function nonEmptyString(value: unknown): value is string {
  return typeof value === 'string' && value.trim().length > 0
}

function parseAnalysis(value: unknown, index: number): AnalysisSummary {
  if (!isRecord(value)) {
    throw new Error(`Analysis at index ${index} is not an object.`)
  }

  if (!nonEmptyString(value['id'])) {
    throw new Error(`Analysis at index ${index} has no id.`)
  }

  if (!nonEmptyString(value['project_name'])) {
    throw new Error(`Analysis at index ${index} has no project name.`)
  }

  const state = value['state']
  if (typeof state !== 'string' || !stateSet.has(state)) {
    throw new Error(`Analysis at index ${index} has an unknown state.`)
  }

  if (typeof value['is_sample'] !== 'boolean') {
    throw new Error(`Analysis at index ${index} has no sample marker.`)
  }

  return {
    id: value['id'],
    projectName: value['project_name'],
    state: state as AnalysisState,
    isSample: value['is_sample'],
  }
}

/**
 * The response is parsed strictly. A malformed row is not dropped or guessed
 * at, because a list that silently omits an analysis would misrepresent the organisation.
 */
export function parseAnalysesResponse(body: unknown): AnalysisSummary[] {
  if (!isRecord(body) || !Array.isArray(body['analyses'])) {
    throw new Error('The analyses response has no list.')
  }

  return body['analyses'].map(parseAnalysis)
}

export function parseAnalysisDetailResponse(body: unknown): AnalysisDetail {
  if (!isRecord(body) || !isRecord(body['analysis'])) {
    throw new Error('The analysis response has no analysis.')
  }

  const value = body['analysis']

  if (!nonEmptyString(value['id'])) {
    throw new Error('The analysis has no id.')
  }
  if (!nonEmptyString(value['project_id'])) {
    throw new Error('The analysis has no project id.')
  }
  if (!nonEmptyString(value['project_name'])) {
    throw new Error('The analysis has no project name.')
  }

  const state = value['state']
  if (typeof state !== 'string' || !stateSet.has(state)) {
    throw new Error('The analysis has an unknown state.')
  }

  const createdAt = value['created_at']
  if (!nonEmptyString(createdAt) || Number.isNaN(Date.parse(createdAt))) {
    throw new Error('The analysis has no valid creation time.')
  }

  if (typeof value['is_sample'] !== 'boolean') {
    throw new Error('The analysis has no sample marker.')
  }

  return {
    id: value['id'],
    projectId: value['project_id'],
    projectName: value['project_name'],
    state: state as AnalysisState,
    createdAt,
    isSample: value['is_sample'],
  }
}
