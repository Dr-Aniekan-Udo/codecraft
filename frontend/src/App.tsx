import { Show, SignInButton, SignUpButton, UserButton } from '@clerk/react'

function App() {
  return (
    <header
      style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'flex-end',
        gap: '0.5rem',
        padding: '0.75rem 1rem',
      }}
    >
      <Show when="signed-out">
        <SignInButton />
        <SignUpButton />
      </Show>
      <Show when="signed-in">
        <UserButton />
      </Show>
    </header>
  )
}

export default App
