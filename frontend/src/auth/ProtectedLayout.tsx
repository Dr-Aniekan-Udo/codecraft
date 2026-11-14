import { useAuth } from '@clerk/react'
import { Navigate, useLocation } from 'react-router'
import { useMembershipStatus } from '../api/useMembershipStatus'
import { Header } from '../components/Header'
import { PageLoading } from '../components/PageLoading'
import { Workspace } from '../components/Workspace'
import { OrganisationBootstrap } from './OrganisationBootstrap'
import { WorkspaceProvider } from './WorkspaceProvider'

export function ProtectedLayout({ apiUrl }: { apiUrl: string }) {
  const { isLoaded, isSignedIn, orgId } = useAuth()
  const location = useLocation()
  const { state: membership, role } = useMembershipStatus(apiUrl)

  if (isLoaded && !isSignedIn) {
    // Drop the invitation ticket from the return path. The page lists pending
    // invitations for the signed-in account and requires an explicit accept.
    const returnTo = location.pathname
    return (
      <Navigate
        to={`/sign-in?redirect_url=${encodeURIComponent(returnTo)}`}
        replace
      />
    )
  }

  return (
    <div className="app-shell">
      <a className="skip-link" href="#main-content">
        Skip to content
      </a>
      {/* The key resets the header's renamed-name override on every switch. */}
      <Header
        key={orgId ?? 'no-organisation'}
        apiUrl={apiUrl}
        membership={membership}
        role={role}
      />
      {isLoaded ? (
        <OrganisationBootstrap apiUrl={apiUrl}>
          <WorkspaceProvider
            key={orgId ?? 'no-organisation'}
            apiUrl={apiUrl}
            membership={membership}
            role={role}
          />
        </OrganisationBootstrap>
      ) : (
        <Workspace>
          <PageLoading />
        </Workspace>
      )}
    </div>
  )
}
