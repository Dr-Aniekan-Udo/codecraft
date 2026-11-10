import { ClerkProvider } from '@clerk/react'
import { useCallback, useMemo } from 'react'
import { BrowserRouter, useNavigate } from 'react-router'
import App from './App'
import { clerkAppearanceFor } from './theme/clerkAppearance'
import { useTheme } from './theme/context'

type RootProps = {
  clerkPublishableKey: string
  apiUrl: string
}

function ClerkAndApp({ clerkPublishableKey, apiUrl }: RootProps) {
  const { resolved } = useTheme()
  const navigate = useNavigate()
  const appearance = useMemo(() => clerkAppearanceFor(resolved), [resolved])

  const push = useCallback(
    (to: string) => {
      if (/^https?:\/\//.test(to)) {
        window.location.assign(to)
        return
      }
      void navigate(to)
    },
    [navigate],
  )

  const replace = useCallback(
    (to: string) => {
      if (/^https?:\/\//.test(to)) {
        window.location.replace(to)
        return
      }
      void navigate(to, { replace: true })
    },
    [navigate],
  )

  return (
    <ClerkProvider
      publishableKey={clerkPublishableKey}
      appearance={appearance}
      signInUrl="/sign-in"
      signUpUrl="/sign-up"
      afterSignOutUrl="/sign-in"
      routerPush={push}
      routerReplace={replace}
    >
      <App apiUrl={apiUrl} />
    </ClerkProvider>
  )
}

export function Root(props: RootProps) {
  return (
    <BrowserRouter>
      <ClerkAndApp {...props} />
    </BrowserRouter>
  )
}
