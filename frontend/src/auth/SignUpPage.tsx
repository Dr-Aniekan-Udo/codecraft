import { SignUp } from '@clerk/react'

export function SignUpPage() {
  return (
    <main className="auth-page">
      <div className="auth-page__inner">
        <p className="auth-page__brand">CodeCraft</p>
        <SignUp
          routing="path"
          path="/sign-up"
          signInUrl="/sign-in"
          fallbackRedirectUrl="/"
        />
      </div>
    </main>
  )
}
