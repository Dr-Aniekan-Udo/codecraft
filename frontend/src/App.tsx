import { Navigate, Route, Routes } from 'react-router'
import { ProtectedLayout } from './auth/ProtectedLayout'
import { SignInPage } from './auth/SignInPage'
import { SignUpPage } from './auth/SignUpPage'
import { AnalysisPage } from './pages/AnalysisPage'
import { InvitationsPage } from './pages/InvitationsPage'
import { ProjectPage } from './pages/ProjectPage'
import { ProjectTablePage } from './pages/ProjectTablePage'

export default function App({ apiUrl }: { apiUrl: string }) {
  return (
    <Routes>
      <Route path="/sign-in/*" element={<SignInPage />} />
      <Route path="/sign-up/*" element={<SignUpPage />} />
      <Route path="/" element={<ProtectedLayout apiUrl={apiUrl} />}>
        <Route index element={<ProjectTablePage />} />
        <Route path="projects/:projectId" element={<ProjectPage />} />
        <Route
          path="projects/:projectId/analyses/:analysisId"
          element={<AnalysisPage />}
        />
        <Route path="invitations" element={<InvitationsPage />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
