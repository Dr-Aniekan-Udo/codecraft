import { useAuth } from '@clerk/react'
import { useEffect, useState } from 'react'

export type MembershipState = 'idle' | 'loading' | 'member' | 'forbidden' | 'unavailable'

type LookupResult = 'member' | 'forbidden' | 'unavailable'

type ReportedState = {
  organizationId: string
  state: LookupResult
}

// "First load" means the first completed lookup for this person in this tab,
// not the first render of whichever component happens to be mounted.
let firstLookupFinishedForUser: string | null = null

async function requestMembership(
  apiUrl: string,
  token: string,
  signal: AbortSignal,
): Promise<LookupResult> {
  const response = await fetch(`${apiUrl}/v1/me`, {
    method: 'GET',
    headers: {
      Accept: 'application/json',
      Authorization: `Bearer ${token}`,
    },
    signal,
  })

  if (response.status === 200) return 'member'
  if (response.status === 403) return 'forbidden'
  return 'unavailable'
}

function wait(ms: number, signal: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal.aborted) {
      reject(new DOMException('Aborted', 'AbortError'))
      return
    }

    const timer = window.setTimeout(() => {
      signal.removeEventListener('abort', handleAbort)
      resolve()
    }, ms)

    function handleAbort() {
      window.clearTimeout(timer)
      reject(new DOMException('Aborted', 'AbortError'))
    }

    signal.addEventListener('abort', handleAbort, { once: true })
  })
}

/**
 * The first lookup after the page opens gets one quiet retry, because team
 * membership is written by a webhook that can trail the sign-in by a moment.
 * A first-load 403 after that retry is reported as "team syncing", not as a
 * removal, because the membership row may still be arriving. Later team
 * switches refetch once and never poll.
 */
export function useMembershipStatus(apiUrl: string): MembershipState {
  const { isLoaded, isSignedIn, orgId, userId, getToken } = useAuth()
  const [reported, setReported] = useState<ReportedState | null>(null)

  useEffect(() => {
    if (!isLoaded || !isSignedIn || !orgId || !userId) return

    const organizationId = orgId
    const controller = new AbortController()
    let active = true
    const initialLookup = firstLookupFinishedForUser !== userId

    const attempt = async (): Promise<LookupResult> => {
      try {
        const token = await getToken({ skipCache: true })
        if (!token) return 'unavailable'
        return await requestMembership(apiUrl, token, controller.signal)
      } catch {
        return 'unavailable'
      }
    }

    const run = async () => {
      let result = await attempt()
      if (initialLookup && (result === 'forbidden' || result === 'unavailable')) {
        try {
          await wait(500, controller.signal)
        } catch {
          return
        }
        if (!active) return
        result = await attempt()
        if (result === 'forbidden') {
          result = 'unavailable'
        }
      }

      if (!active) return
      firstLookupFinishedForUser = userId
      setReported({ organizationId, state: result })
    }

    void run()

    return () => {
      active = false
      controller.abort()
    }
  }, [apiUrl, getToken, isLoaded, isSignedIn, orgId, userId])

  if (!isLoaded || !isSignedIn || !orgId) return 'idle'
  if (reported?.organizationId === orgId) return reported.state
  return 'loading'
}
