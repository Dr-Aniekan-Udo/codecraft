import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { Root } from './Root'
import { ThemeProvider } from './theme/ThemeProvider'
import './index.css'

function requiredEnvironmentValue(name: string, value: string | undefined): string {
  if (typeof value !== 'string' || value.trim().length === 0) {
    throw new Error(`CodeCraft cannot start: ${name} is missing.`)
  }
  return value.trim()
}

const clerkPublishableKey = requiredEnvironmentValue(
  'VITE_CLERK_PUBLISHABLE_KEY',
  import.meta.env.VITE_CLERK_PUBLISHABLE_KEY,
)
const apiUrl = requiredEnvironmentValue('VITE_API_URL', import.meta.env.VITE_API_URL).replace(
  /\/+$/,
  '',
)

const rootElement = document.getElementById('root')
if (!rootElement) {
  throw new Error('CodeCraft cannot start: the root element is missing.')
}

createRoot(rootElement).render(
  <StrictMode>
    <ThemeProvider>
      <Root clerkPublishableKey={clerkPublishableKey} apiUrl={apiUrl} />
    </ThemeProvider>
  </StrictMode>,
)
