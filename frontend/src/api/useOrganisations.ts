import { useAuth } from '@clerk/react'
import { useCallback, useEffect, useState } from 'react'
import { clearPendingPersonalOrganisation } from '../lib/organisationSync'
import { fetchOrganisations } from './organisations'
import type { OrganisationSummary } from './organisations'

export type OrganisationsState =
  | { status: 'idle'; organisations: OrganisationSummary[] }
  | { status: 'loading'; organisations: OrganisationSummary[] }
  | { status: 'ready'; organisations: OrganisationSummary[] }
  | { status: 'error'; organisations: OrganisationSummary[]; message: string }

type Settled = {
  userId: string
  state: OrganisationsState
}

export function useOrganisations(
  apiUrl: string,
): OrganisationsState & { reload: () => void } {
  // Clerk's API uses the US spelling 'organization'; the application's domain
  // term is 'organisation'.
  const { isLoaded, isSignedIn, orgId: activeOrganisationId, userId, getToken } = useAuth()
  const [version, setVersion] = useState(0)
  const [settled, setSettled] = useState<Settled | null>(null)

  const reload = useCallback(() => {
    setVersion((current) => current + 1)
  }, [])

  useEffect(() => {
    if (!isLoaded || !isSignedIn || !userId) return

    const controller = new AbortController()
    let active = true

    const run = async () => {
      try {
        const token = await getToken({ skipCache: true })
        if (!active) return
        if (!token) {
          setSettled({
            userId,
            state: {
              status: 'error',
              organisations: [],
              message: 'Your session could not be read.',
            },
          })
          return
        }
        const organisations = await fetchOrganisations(apiUrl, token, controller.signal)
        if (!active) return
        if (organisations.some((organisation) => organisation.isOwner)) {
          clearPendingPersonalOrganisation(userId)
        }
        setSettled({ userId, state: { status: 'ready', organisations } })
      } catch {
        if (!active || controller.signal.aborted) return
        setSettled({
          userId,
          state: {
            status: 'error',
            organisations: [],
            message: 'The organisations list could not be loaded. Try again.',
          },
        })
      }
    }

    void run()

    return () => {
      active = false
      controller.abort()
    }
  }, [activeOrganisationId, apiUrl, getToken, isLoaded, isSignedIn, userId, version])

  const state: OrganisationsState =
    !isLoaded || !isSignedIn || !userId
      ? { status: 'idle', organisations: [] }
      : settled?.userId === userId
        ? settled.state
        : { status: 'loading', organisations: [] }

  return { ...state, reload }
}
