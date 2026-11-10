import { Navigate, Route, Routes } from 'react-router'
import { ProtectedLayout } from './auth/ProtectedLayout'
import { SignInPage } from './auth/SignInPage'
import { SignUpPage } from './auth/SignUpPage'
import { HomePage } from './pages/HomePage'

export default function App({ apiUrl }: { apiUrl: string }) {
  return (
    <Routes>
      <Route path="/sign-in/*" element={<SignInPage />} />
      <Route path="/sign-up/*" element={<SignUpPage />} />
      <Route path="/" element={<ProtectedLayout />}>
        <Route index element={<HomePage apiUrl={apiUrl} />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
