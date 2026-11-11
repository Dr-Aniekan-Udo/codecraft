import { useAuth } from '@clerk/react'
import { useEffect, useState } from 'react'
import { parseAnalysesResponse } from './analyses'
import type { AnalysisSummary } from './analyses'

export type AnalysesState =
  | { status: 'idle' }
  | { status: 'loading' }
  | { status: 'ready'; analyses: AnalysisSummary[] }
  | { status: 'error'; message: string }

type Outcome =
  | { ok: true; analyses: AnalysisSummary[] }
  | { ok: false; message: string }

type Settled = {
  requestKey: string
  state: AnalysesState
}

const SESSION_MESSAGE = 'Your session has expired. Reload the page to sign in again.'
const TEAM_MESSAGE = 'This team could not be found. Choose another team and try again.'
const UNAVAILABLE_MESSAGE = 'Analyses could not be loaded. Try again later.'

async function requestAnalyses(
  apiUrl: string,
  token: string,
  organizationId: string,
  signal: AbortSignal,
): Promise<Outcome> {
  const response = await fetch(
    `${apiUrl}/v1/analyses?team_id=${encodeURIComponent(organizationId)}`,
    {
      method: 'GET',
      headers: {
        Accept: 'application/json',
        Authorization: `Bearer ${token}`,
      },
      signal,
    },
  )

  if (response.status === 401) return { ok: false, message: SESSION_MESSAGE }
  if (response.status === 422) return { ok: false, message: TEAM_MESSAGE }
  if (response.status !== 200) return { ok: false, message: UNAVAILABLE_MESSAGE }

  try {
    return { ok: true, analyses: parseAnalysesResponse(await response.json()) }
  } catch {
    return { ok: false, message: UNAVAILABLE_MESSAGE }
  }
}

/**
 * One request per signed-in user, API URL and active team. The team is a query
 * parameter, not a client-side filter, and there is no polling.
 */
export function useAnalyses(apiUrl: string): AnalysesState {
  const { isLoaded, isSignedIn, orgId, userId, getToken } = useAuth()
  const [settled, setSettled] = useState<Settled | null>(null)

  const requestKey = `${userId ?? ''}\u0000${orgId ?? ''}\u0000${apiUrl}`

  useEffect(() => {
    if (!isLoaded || !isSignedIn || !orgId || !userId) return

    const organizationId = orgId
    const controller = new AbortController()
    let active = true

    const run = async () => {
      try {
        const token = await getToken({ skipCache: true })
        if (!active) return
        if (!token) {
          setSettled({ requestKey, state: { status: 'error', message: SESSION_MESSAGE } })
          return
        }

        const outcome = await requestAnalyses(apiUrl, token, organizationId, controller.signal)
        if (!active) return

        setSettled({
          requestKey,
          state: outcome.ok
            ? { status: 'ready', analyses: outcome.analyses }
            : { status: 'error', message: outcome.message },
        })
      } catch {
        if (!active || controller.signal.aborted) return
        setSettled({ requestKey, state: { status: 'error', message: UNAVAILABLE_MESSAGE } })
      }
    }

    void run()

    return () => {
      active = false
      controller.abort()
    }
  }, [apiUrl, getToken, isLoaded, isSignedIn, orgId, requestKey, userId])

  if (!isLoaded || !isSignedIn || !orgId) return { status: 'idle' }
  if (settled?.requestKey === requestKey) return settled.state
  return { status: 'loading' }
}
