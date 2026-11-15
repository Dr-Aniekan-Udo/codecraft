import { useAuth, useOrganizationList, useUser } from '@clerk/react'
import { useEffect, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import { createPersonalOrganisation, fetchOrganisations } from '../api/organisations'
import type { OrganisationSummary } from '../api/organisations'
import { Workspace } from '../components/Workspace'
import {
  clearPendingPersonalOrganisation,
  hasPendingPersonalOrganisation,
  markPersonalOrganisationPending,
  markMembershipSyncPending,
  pendingPersonalOrganisationIdempotencyKey,
} from '../lib/organisationSync'

const organisationSetupRuns = new Map<string, Promise<void>>()

function runOrganisationSetupOnce(
  userId: string,
  run: () => Promise<void>,
): Promise<void> {
  const existing = organisationSetupRuns.get(userId)
  if (existing) return existing

  const promise = run().finally(() => {
    if (organisationSetupRuns.get(userId) === promise) {
      organisationSetupRuns.delete(userId)
    }
  })

  organisationSetupRuns.set(userId, promise)
  return promise
}

function oldestOwnedOrganisation(
  organisations: OrganisationSummary[],
): OrganisationSummary | null {
  const owned = organisations.filter((organisation) => organisation.isOwner)
  if (owned.length === 0) return null
  return owned.reduce((oldest, organisation) =>
    Date.parse(organisation.createdAt) < Date.parse(oldest.createdAt)
      ? organisation
      : oldest,
  )
}

function SetupMessage({
  title,
  role,
  children,
}: {
  title: string
  role: 'status' | 'alert'
  children: ReactNode
}) {
  return (
    <div className="setup-state" role={role}>
      <h1 className="setup-state__title">{title}</h1>
      <p>{children}</p>
    </div>
  )
}

type OrganisationsLoad =
  | { status: 'loading' }
  | { status: 'ready'; organisations: OrganisationSummary[] }
  | { status: 'error' }

/**
 * The identity provider's create-organisation screen is never rendered. This
 * component creates the first personal organisation quietly through the backend
 * and shows static status text until it has. It also waits for the signed
 * webhook to write a just-created membership instead of creating a second
 * organisation after a refresh.
 */
export function OrganisationBootstrap({
  apiUrl,
  children,
}: {
  apiUrl: string
  children: ReactNode
}) {
  const { isLoaded, isSignedIn, orgId: activeOrganisationId, userId, getToken } = useAuth()
  const { isLoaded: userLoaded } = useUser()
  // Clerk's API uses the US spelling 'organization'; the application's domain
  // term is 'organisation'.
  const {
    isLoaded: organisationListLoaded,
    setActive,
    userMemberships,
  } = useOrganizationList({
    userMemberships: { infinite: true, pageSize: 100 },
  })

  const [organisationsLoad, setOrganisationsLoad] = useState<OrganisationsLoad>({
    status: 'loading',
  })
  const [reload, setReload] = useState(0)
  const [setupError, setSetupError] = useState(false)
  const setupStarted = useRef(false)
  const isReady = activeOrganisationId != null && userLoaded

  useEffect(() => {
    if (!isLoaded || !isSignedIn || !userId || !userLoaded || !organisationListLoaded) return

    const controller = new AbortController()
    let active = true

    const run = async () => {
      try {
        const token = await getToken({ skipCache: true })
        if (!token) throw new Error('no token')
        const organisations = await fetchOrganisations(apiUrl, token, controller.signal)
        if (!active) return
        if (organisations.some((organisation) => organisation.isOwner)) {
          clearPendingPersonalOrganisation(userId)
        }
        setOrganisationsLoad({ status: 'ready', organisations })
      } catch {
        if (!active || controller.signal.aborted) return
        setOrganisationsLoad({ status: 'error' })
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
    getToken,
    isLoaded,
    isSignedIn,
    organisationListLoaded,
    reload,
    userLoaded,
    userId,
  ])

  useEffect(() => {
    if (setupError || setupStarted.current) return
    if (!isLoaded || !isSignedIn || !userId || !userLoaded) return
    if (!organisationListLoaded || !setActive) return
    if (organisationsLoad.status !== 'ready') return

    const owned = oldestOwnedOrganisation(organisationsLoad.organisations)
    if (owned !== null) {
      if (activeOrganisationId == null) {
        setupStarted.current = true
        void runOrganisationSetupOnce(userId, async () => {
          await setActive({ organization: owned.organisationId })
        }).catch((error: unknown) => {
          console.error('Could not activate the organisation.', error)
          setSetupError(true)
        })
      }
      return
    }

    const storedIdempotencyKey = pendingPersonalOrganisationIdempotencyKey(userId)
    if (storedIdempotencyKey === null && hasPendingPersonalOrganisation(userId)) {
      // A pending write with no key comes from an older build. Wait for it
      // instead of racing; a write with a key is safe to retry because the
      // server returns the same organisation for the same key.
      const timer = window.setTimeout(() => setReload((current) => current + 1), 1000)
      return () => window.clearTimeout(timer)
    }

    const idempotencyKey = storedIdempotencyKey ?? crypto.randomUUID()
    if (storedIdempotencyKey === null) {
      markPersonalOrganisationPending(userId, idempotencyKey)
    }

    setupStarted.current = true

    const createOnce = async () => {
      const token = await getToken({ skipCache: true })
      if (!token) throw new Error('no token')
      const latest = await fetchOrganisations(apiUrl, token)
      const alreadyOwned = oldestOwnedOrganisation(latest)
      if (alreadyOwned !== null) {
        clearPendingPersonalOrganisation(userId)
        await setActive({ organization: alreadyOwned.organisationId })
        return
      }

      const organisationId = await createPersonalOrganisation(
        apiUrl,
        token,
        idempotencyKey,
      )
      markMembershipSyncPending(organisationId)
      clearPendingPersonalOrganisation(userId)
      if (userMemberships.revalidate) await userMemberships.revalidate()
      await setActive({ organization: organisationId })
    }

    const run = async () => {
      if (navigator.locks) {
        await navigator.locks.request(
          `codecraft:personal-organisation:${userId}`,
          createOnce,
        )
      } else {
        await createOnce()
      }
    }

    void runOrganisationSetupOnce(userId, run)
      .then(() => {
        setupStarted.current = true
      })
      .catch((error: unknown) => {
        // Keep the pending record so a reload retries with the same key.
        console.error('Could not prepare the organisation.', error)
        setSetupError(true)
      })
  }, [
    apiUrl,
    getToken,
    isLoaded,
    isReady,
    isSignedIn,
    organisationListLoaded,
    activeOrganisationId,
    setActive,
    setupError,
    organisationsLoad,
    userLoaded,
    userMemberships,
    userId,
  ])

  if (isReady && !setupError) return <>{children}</>

  if (setupError || organisationsLoad.status === 'error') {
    return (
      <Workspace>
        <SetupMessage title="Organisation setup failed" role="alert">
          We could not set up your organisation. Reload the page to try again.
        </SetupMessage>
      </Workspace>
    )
  }

  return (
    <Workspace>
      <SetupMessage title="Setting up your organisation" role="status">
        This only takes a moment.
      </SetupMessage>
    </Workspace>
  )
}
