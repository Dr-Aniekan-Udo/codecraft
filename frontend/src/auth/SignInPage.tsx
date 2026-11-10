import { SignIn } from '@clerk/react'

export function SignInPage() {
  return (
    <main className="auth-page">
      <div className="auth-page__inner">
        <p className="auth-page__brand">CodeCraft</p>
        <SignIn
          routing="path"
          path="/sign-in"
          signUpUrl="/sign-up"
          fallbackRedirectUrl="/"
        />
      </div>
    </main>
  )
}
