import { useAuth } from '@clerk/react'
import { Navigate, Outlet } from 'react-router'
import { Header } from '../components/Header'
import { TeamBootstrap } from './TeamBootstrap'

function AuthLoading() {
  return (
    <main className="status-page" role="status">
      <p>Loading CodeCraft…</p>
    </main>
  )
}

export function ProtectedLayout() {
  const { isLoaded, isSignedIn } = useAuth()

  if (!isLoaded) return <AuthLoading />
  if (!isSignedIn) return <Navigate to="/sign-in" replace />

  return (
    <div className="app-shell">
      <a className="skip-link" href="#main-content">
        Skip to content
      </a>
      <Header />
      <main id="main-content" className="app-main">
        <TeamBootstrap>
          <Outlet />
        </TeamBootstrap>
      </main>
    </div>
  )
}
