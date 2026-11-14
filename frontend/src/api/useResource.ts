import { useAuth } from '@clerk/react'
import { useEffect, useState } from 'react'

export type ResourceState<T> =
  | { status: 'idle' }
  | { status: 'loading' }
  | { status: 'ready'; data: T }
  | { status: 'not-found' }
  | { status: 'error'; message: string }

export const ACCESS_MESSAGE =
  'Access could not be confirmed. Reload the page and try again.'
export const ORGANISATION_MESSAGE =
  'This organisation could not be found. Choose another organisation and try again.'
export const UNAVAILABLE_MESSAGE = 'Analyses could not be loaded. Try again later.'

type Outcome<T> =
  | { kind: 'ok'; data: T }
  | { kind: 'unauthorized' }
  | { kind: 'not-found' }
  | { kind: 'organisation' }
  | { kind: 'unavailable' }

type Settled<T> = {
  requestKey: string
  state: ResourceState<T>
}

async function requestResource<T>(
  apiUrl: string,
  path: string,
  token: string,
  signal: AbortSignal,
  parse: (body: unknown) => T,
): Promise<Outcome<T>> {
  const response = await fetch(`${apiUrl}${path}`, {
    method: 'GET',
    headers: {
      Accept: 'application/json',
      Authorization: `Bearer ${token}`,
    },
    signal,
  })

  if (response.status === 401) return { kind: 'unauthorized' }
  if (response.status === 404) return { kind: 'not-found' }
  if (response.status === 422) return { kind: 'organisation' }
  if (response.status !== 200) return { kind: 'unavailable' }

  try {
    return { kind: 'ok', data: parse(await response.json()) }
  } catch {
    // A body that does not match the contract is a load failure, not a render crash.
    return { kind: 'unavailable' }
  }
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
 * One request per signed-in user, active organisation, API URL and path. The
 * token is minted for the active organisation, so a switch cannot send the
 * previous organisation's token. A changed path aborts the previous request and
 * starts loading; there is no polling.
 */
export function useResource<T>(
  apiUrl: string,
  enabled: boolean,
  path: string | null,
  parse: (body: unknown) => T,
): ResourceState<T> {
  const { isLoaded, isSignedIn, orgId: activeOrganisationId, userId, getToken } = useAuth()
  const [settled, setSettled] = useState<Settled<T> | null>(null)

  const requestKey = `${userId ?? ''}\u0000${activeOrganisationId ?? ''}\u0000${apiUrl}\u0000${enabled ? '1' : '0'}\u0000${path ?? ''}`

  useEffect(() => {
    if (!enabled || !path || !isLoaded || !isSignedIn || !activeOrganisationId || !userId) {
      return
    }

    const organisationId = activeOrganisationId
    const resourcePath = path
    const controller = new AbortController()
    let active = true

    const tokenForOrganisation = async (): Promise<string | null> => {
      const token = await getToken({ organizationId: organisationId, skipCache: true })
      if (token) return token
      try {
        await wait(300, controller.signal)
      } catch {
        return null
      }
      return getToken({ organizationId: organisationId, skipCache: true })
    }

    const run = async () => {
      try {
        let token = await tokenForOrganisation()
        if (!active) return
        if (!token) {
          setSettled({ requestKey, state: { status: 'error', message: ACCESS_MESSAGE } })
          return
        }

        let outcome = await requestResource(
          apiUrl,
          resourcePath,
          token,
          controller.signal,
          parse,
        )
        if (!active) return

        if (outcome.kind === 'unauthorized') {
          try {
            await wait(300, controller.signal)
          } catch {
            return
          }
          if (!active) return
          token = await tokenForOrganisation()
          if (!token) {
            setSettled({ requestKey, state: { status: 'error', message: ACCESS_MESSAGE } })
            return
          }
          outcome = await requestResource(
            apiUrl,
            resourcePath,
            token,
            controller.signal,
            parse,
          )
          if (!active) return
        }

        if (outcome.kind === 'ok') {
          setSettled({ requestKey, state: { status: 'ready', data: outcome.data } })
          return
        }
        if (outcome.kind === 'not-found') {
          setSettled({ requestKey, state: { status: 'not-found' } })
          return
        }
        setSettled({
          requestKey,
          state: {
            status: 'error',
            message:
              outcome.kind === 'organisation'
                ? ORGANISATION_MESSAGE
                : outcome.kind === 'unauthorized'
                  ? ACCESS_MESSAGE
                  : UNAVAILABLE_MESSAGE,
          },
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
  }, [
    activeOrganisationId,
    apiUrl,
    enabled,
    getToken,
    isLoaded,
    isSignedIn,
    parse,
    path,
    requestKey,
    userId,
  ])

  if (!enabled || !path) return { status: 'idle' }
  if (!isLoaded || !isSignedIn || !activeOrganisationId) return { status: 'idle' }
  if (settled?.requestKey === requestKey) return settled.state
  return { status: 'loading' }
}
