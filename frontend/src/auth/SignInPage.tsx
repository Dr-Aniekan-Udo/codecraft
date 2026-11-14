import { SignIn } from '@clerk/react'
import { useSearchParams } from 'react-router'

function returnPath(redirectUrl: string | null): string {
  if (redirectUrl === null || !redirectUrl.startsWith('/')) return '/'
  // Reject protocol-relative and backslash variants so the return path cannot
  // become an external redirect.
  if (redirectUrl.startsWith('//') || redirectUrl.startsWith('/\\')) return '/'
  return redirectUrl
}

export function SignInPage() {
  const [searchParams] = useSearchParams()
  const redirectUrl = searchParams.get('redirect_url')
  const returnTo = returnPath(redirectUrl)
  const signUpUrl = `/sign-up?redirect_url=${encodeURIComponent(returnTo)}`

  return (
    <main className="auth-page">
      <div className="auth-page__inner">
        <p className="auth-page__brand">CodeCraft</p>
        <SignIn
          routing="path"
          path="/sign-in"
          signUpUrl={signUpUrl}
          fallbackRedirectUrl={returnTo}
        />
      </div>
    </main>
  )
}
