import { useAuth } from '@clerk/react'
import { useEffect, useState } from 'react'
import { clearMembershipSyncPending, isMembershipSyncPending } from '../lib/organisationSync'

export type MembershipState =
  | 'idle'
  | 'checking'
  | 'member'
  | 'forbidden'
  | 'syncing'
  | 'unavailable'

/**
 * The role the API reports for the verified token. It is the organisation's
 * short role, not Clerk's membership value, and the browser never decodes the
 * token to obtain it. Null means the API did not report one.
 */
export type OrganisationRole = 'admin' | 'member' | null

export type MembershipResult = {
  state: MembershipState
  role: OrganisationRole
}

type LookupResult =
  | { status: 'member'; role: OrganisationRole }
  | { status: 'forbidden' }
  | { status: 'unavailable' }

type ReportedState = {
  organisationId: string
  userId: string
  state: MembershipState
  role: OrganisationRole
}

function reportedRole(value: unknown): OrganisationRole {
  return value === 'admin' || value === 'member' ? value : null
}

async function readReportedRole(response: Response): Promise<OrganisationRole> {
  try {
    const body: unknown = await response.json()
    if (typeof body !== 'object' || body === null || !('role' in body)) return null
    return reportedRole(body.role)
  } catch {
    // A 200 still confirms membership; the role is simply absent.
    return null
  }
}

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
    // The role is the current answer for the verified token. A cached response
    // from before a role change would keep the old role in the interface.
    cache: 'no-store',
    signal,
  })

  if (response.status === 200) {
    return { status: 'member', role: await readReportedRole(response) }
  }
  if (response.status === 403) return { status: 'forbidden' }
  return { status: 'unavailable' }
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
 * The active organisation's membership is confirmed before its data is
 * rendered. A 403 is "syncing" only while this tab has an explicit pending
 * write; on an ordinary refresh it is a refusal, not a write in progress.
 * The role comes from the same response so no second request is made.
 */
export function useMembershipStatus(apiUrl: string): MembershipResult {
  const { isLoaded, isSignedIn, orgId: activeOrganisationId, userId, getToken } = useAuth()
  const [reported, setReported] = useState<ReportedState | null>(null)

  useEffect(() => {
    if (!isLoaded || !isSignedIn || !activeOrganisationId || !userId) return

    const organisationId = activeOrganisationId
    const controller = new AbortController()
    let active = true

    const attempt = async (): Promise<LookupResult> => {
      try {
        const token = await getToken({
          organizationId: organisationId,
          skipCache: true,
        })
        if (!token) return { status: 'unavailable' }
        return await requestMembership(apiUrl, token, controller.signal)
      } catch {
        return { status: 'unavailable' }
      }
    }

    const run = async () => {
      let result = await attempt()
      if (result.status === 'unavailable') {
        try {
          await wait(300, controller.signal)
        } catch {
          return
        }
        if (!active) return
        result = await attempt()
      }

      if (result.status === 'forbidden' && isMembershipSyncPending(organisationId)) {
        // The pending marker is the only evidence this tab is waiting for a
        // membership write. Keep checking while it is alive, then fall back to
        // a refusal instead of showing "syncing" forever.
        setReported({ organisationId, userId, state: 'syncing', role: null })
        let retryDelay = 1000
        while (active && isMembershipSyncPending(organisationId)) {
          try {
            await wait(retryDelay, controller.signal)
          } catch {
            return
          }
          if (!active) return
          result = await attempt()
          if (result.status === 'member') {
            clearMembershipSyncPending(organisationId)
            setReported({
              organisationId,
              userId,
              state: 'member',
              role: result.role,
            })
            return
          }
          if (result.status !== 'forbidden') break
          retryDelay = Math.min(retryDelay * 2, 8000)
        }
        if (!active) return
      }

      if (result.status === 'member') {
        clearMembershipSyncPending(organisationId)
      }

      const state: MembershipState =
        result.status === 'member'
          ? 'member'
          : result.status === 'forbidden'
            ? 'forbidden'
            : 'unavailable'

      setReported({
        organisationId,
        userId,
        state,
        role: result.status === 'member' ? result.role : null,
      })
    }

    void run()

    return () => {
      active = false
      controller.abort()
    }
  }, [activeOrganisationId, apiUrl, getToken, isLoaded, isSignedIn, userId])

  if (!isLoaded || !isSignedIn || !activeOrganisationId) {
    return { state: 'idle', role: null }
  }
  if (reported?.organisationId === activeOrganisationId && reported.userId === userId) {
    return { state: reported.state, role: reported.role }
  }
  return { state: 'checking', role: null }
}
