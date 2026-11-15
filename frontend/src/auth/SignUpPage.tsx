import { SignUp } from '@clerk/react'
import { useSearchParams } from 'react-router'

function returnPath(redirectUrl: string | null): string {
  if (redirectUrl === null || !redirectUrl.startsWith('/')) return '/'
  // Reject protocol-relative and backslash variants so the return path cannot
  // become an external redirect.
  if (redirectUrl.startsWith('//') || redirectUrl.startsWith('/\\')) return '/'
  return redirectUrl
}

export function SignUpPage() {
  const [searchParams] = useSearchParams()
  const redirectUrl = searchParams.get('redirect_url')
  const returnTo = returnPath(redirectUrl)
  const signInUrl = `/sign-in?redirect_url=${encodeURIComponent(returnTo)}`

  return (
    <main className="auth-page">
      <div className="auth-page__inner">
        <p className="auth-page__brand">CodeCraft</p>
        <SignUp
          routing="path"
          path="/sign-up"
          signInUrl={signInUrl}
          fallbackRedirectUrl={returnTo}
        />
      </div>
    </main>
  )
}
