import { useAuth, useOrganizationList, useUser } from '@clerk/react'
import { useEffect, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import { teamNameForAccount } from '../lib/identity'

const teamSetupRuns = new Map<string, Promise<void>>()

function runTeamSetupOnce(userId: string, run: () => Promise<void>): Promise<void> {
  const existing = teamSetupRuns.get(userId)
  if (existing) return existing

  const promise = run().finally(() => {
    if (teamSetupRuns.get(userId) === promise) {
      teamSetupRuns.delete(userId)
    }
  })

  teamSetupRuns.set(userId, promise)
  return promise
}

function mostRecentlyJoined<T extends { createdAt: Date }>(memberships: T[]): T {
  return memberships.reduce((newest, membership) =>
    membership.createdAt.getTime() > newest.createdAt.getTime() ? membership : newest,
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

/**
 * The identity provider's create-team screen is never rendered. This component
 * creates or activates a team quietly and shows static status text until it has.
 */
export function TeamBootstrap({ children }: { children: ReactNode }) {
  const { isLoaded, isSignedIn, orgId, userId } = useAuth()
  const { isLoaded: userLoaded, user } = useUser()
  const { isLoaded: organizationsLoaded, createOrganization, setActive, userMemberships } =
    useOrganizationList({
      userMemberships: { infinite: true, pageSize: 100 },
    })

  const [setupError, setSetupError] = useState(false)
  const setupFinished = useRef(false)
  const isReady = orgId != null && organizationsLoaded && userLoaded

  useEffect(() => {
    if (isReady || setupError || setupFinished.current) return
    if (!isLoaded || !isSignedIn || !userLoaded || !organizationsLoaded) return
    if (!userId || !user || orgId) return
    if (userMemberships.isLoading || userMemberships.isError) return

    const memberships = userMemberships.data ?? []
    const setup = async () => {
      if (memberships.length > 0) {
        const newest = mostRecentlyJoined(memberships)
        await setActive({ organization: newest.organization.id })
        return
      }

      const organization = await createOrganization({ name: teamNameForAccount(user) })
      await setActive({ organization: organization.id })
    }

    void runTeamSetupOnce(userId, setup)
      .then(() => {
        setupFinished.current = true
      })
      .catch((error: unknown) => {
        console.error('Could not prepare the team.', error)
        setSetupError(true)
      })
  }, [
    createOrganization,
    isLoaded,
    isReady,
    isSignedIn,
    orgId,
    organizationsLoaded,
    setActive,
    setupError,
    user,
    userLoaded,
    userId,
    userMemberships.data,
    userMemberships.isError,
    userMemberships.isLoading,
  ])

  if (isReady) return <>{children}</>

  if (setupError || userMemberships.isError) {
    return (
      <SetupMessage title="Team setup failed" role="alert">
        We could not set up your team. Reload the page to try again.
      </SetupMessage>
    )
  }

  return (
    <SetupMessage title="Setting up your team" role="status">
      This only takes a moment.
    </SetupMessage>
  )
}
