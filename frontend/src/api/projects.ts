import { ANALYSIS_STATE_LABELS, ANALYSIS_STATES } from './analyses'
import type { AnalysisState } from './analyses'

export type ProjectSummary = {
  id: string
  name: string
  createdAt: string
  isSample: boolean
  latestAnalysisState: AnalysisState | null
  latestAnalysisCreatedAt: string | null
}

export type ProjectRecord = {
  id: string
  name: string
  createdAt: string
  isSample: boolean
}

export type ProjectAnalysis = {
  id: string
  state: AnalysisState
  createdAt: string
  isSample: boolean
}

export type ProjectDetail = {
  project: ProjectRecord
  analyses: ProjectAnalysis[]
}

const stateSet = new Set<string>(ANALYSIS_STATES)

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function nonEmptyString(value: unknown): value is string {
  return typeof value === 'string' && value.trim().length > 0
}

function validTimestamp(value: unknown): value is string {
  return nonEmptyString(value) && !Number.isNaN(Date.parse(value))
}

function parseState(value: unknown, label: string): AnalysisState {
  if (typeof value !== 'string' || !stateSet.has(value)) {
    throw new Error(`${label} has an unknown state.`)
  }
  return value as AnalysisState
}

function parseProjectRecord(value: unknown, label: string): ProjectRecord {
  if (!isRecord(value)) {
    throw new Error(`${label} is not an object.`)
  }
  if (!nonEmptyString(value['id'])) {
    throw new Error(`${label} has no id.`)
  }
  if (!nonEmptyString(value['name'])) {
    throw new Error(`${label} has no name.`)
  }
  const createdAt = value['created_at']
  if (!validTimestamp(createdAt)) {
    throw new Error(`${label} has no valid creation time.`)
  }
  if (typeof value['is_sample'] !== 'boolean') {
    throw new Error(`${label} has no sample marker.`)
  }
  return {
    id: value['id'],
    name: value['name'],
    createdAt,
    isSample: value['is_sample'],
  }
}

function parseProjectAnalysis(value: unknown, index: number): ProjectAnalysis {
  if (!isRecord(value)) {
    throw new Error(`Project analysis at index ${index} is not an object.`)
  }
  if (!nonEmptyString(value['id'])) {
    throw new Error(`Project analysis at index ${index} has no id.`)
  }
  const state = parseState(value['state'], `Project analysis at index ${index}`)
  const createdAt = value['created_at']
  if (!validTimestamp(createdAt)) {
    throw new Error(`Project analysis at index ${index} has no valid creation time.`)
  }
  if (typeof value['is_sample'] !== 'boolean') {
    throw new Error(`Project analysis at index ${index} has no sample marker.`)
  }
  return {
    id: value['id'],
    state,
    createdAt,
    isSample: value['is_sample'],
  }
}

function parseProjectSummary(value: unknown, index: number): ProjectSummary {
  if (!isRecord(value)) {
    throw new Error(`Project at index ${index} is not an object.`)
  }
  if (!nonEmptyString(value['id'])) {
    throw new Error(`Project at index ${index} has no id.`)
  }
  if (!nonEmptyString(value['name'])) {
    throw new Error(`Project at index ${index} has no name.`)
  }
  const createdAt = value['created_at']
  if (!validTimestamp(createdAt)) {
    throw new Error(`Project at index ${index} has no valid creation time.`)
  }
  if (typeof value['is_sample'] !== 'boolean') {
    throw new Error(`Project at index ${index} has no sample marker.`)
  }

  const latestState = value['latest_analysis_state']
  const latestCreatedAt = value['latest_analysis_created_at']
  let latestAnalysisState: AnalysisState | null
  let latestAnalysisCreatedAt: string | null
  if (latestState === null && latestCreatedAt === null) {
    latestAnalysisState = null
    latestAnalysisCreatedAt = null
  } else if (latestState === null || latestCreatedAt === null) {
    // Half a latest analysis would read as either "none" or a specific state;
    // neither is true, so the row is rejected.
    throw new Error(`Project at index ${index} has only one latest analysis field.`)
  } else {
    latestAnalysisState = parseState(latestState, `Project at index ${index} latest analysis`)
    if (!validTimestamp(latestCreatedAt)) {
      throw new Error(`Project at index ${index} has no valid latest analysis time.`)
    }
    latestAnalysisCreatedAt = latestCreatedAt
  }

  return {
    id: value['id'],
    name: value['name'],
    createdAt,
    isSample: value['is_sample'],
    latestAnalysisState,
    latestAnalysisCreatedAt,
  }
}

/**
 * The response is parsed strictly and in the order the API returned it. A
 * malformed row is not dropped or guessed at, because a list that silently
 * omits a project would misrepresent the organisation.
 */
export function parseProjectsResponse(body: unknown): ProjectSummary[] {
  if (!isRecord(body) || !Array.isArray(body['projects'])) {
    throw new Error('The projects response has no list.')
  }

  return body['projects'].map(parseProjectSummary)
}

export function parseProjectDetailResponse(body: unknown): ProjectDetail {
  if (!isRecord(body)) {
    throw new Error('The project response is not an object.')
  }
  const project = parseProjectRecord(body['project'], 'The project')
  if (!Array.isArray(body['analyses'])) {
    throw new Error('The project response has no analyses list.')
  }
  return {
    project,
    analyses: body['analyses'].map(parseProjectAnalysis),
  }
}

export function latestAnalysisLabel(project: ProjectSummary): string {
  return project.latestAnalysisState === null
    ? 'No analyses'
    : ANALYSIS_STATE_LABELS[project.latestAnalysisState]
}
