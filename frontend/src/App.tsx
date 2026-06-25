import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { AuthProvider, useAuth } from './context/AuthContext'
import { DashboardLayout } from './layouts/DashboardLayout'

import LoginPage from './pages/LoginPage'
import DashboardPage from './pages/DashboardPage'
import PromptConsolePage from './pages/PromptConsolePage'
import LiveEventFeedPage from './pages/LiveEventFeedPage'
import RiskExplorerPage from './pages/RiskExplorerPage'
import CompliancePage from './pages/CompliancePage'
import AuditLogsPage from './pages/AuditLogsPage'
import KnowledgeShieldPage from './pages/KnowledgeShieldPage'
import SettingsPage from './pages/SettingsPage'

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { isAuthenticated, isLoading } = useAuth()
  if (isLoading) return (
    <div className="h-screen flex items-center justify-center bg-surface-0">
      <div className="flex flex-col items-center gap-3">
        <div className="w-8 h-8 border-2 border-brand border-t-transparent rounded-full animate-spin" />
        <p className="text-gray-500 text-sm">Loading...</p>
      </div>
    </div>
  )
  return isAuthenticated ? <>{children}</> : <Navigate to="/login" replace />
}

function AdminRoute({ children }: { children: React.ReactNode }) {
  const { user } = useAuth()
  return user?.role === 'admin' ? <>{children}</> : <Navigate to="/console" replace />
}

function AppRoutes() {
  const { isAuthenticated } = useAuth()

  return (
    <Routes>
      <Route path="/login" element={isAuthenticated ? <Navigate to="/" replace /> : <LoginPage />} />
      <Route
        path="/*"
        element={
          <ProtectedRoute>
            <DashboardLayout>
              <Routes>
                <Route path="/" element={<AdminRoute><DashboardPage /></AdminRoute>} />
                <Route path="/console" element={<PromptConsolePage />} />
                <Route path="/live-feed" element={<AdminRoute><LiveEventFeedPage /></AdminRoute>} />
                <Route path="/risk" element={<AdminRoute><RiskExplorerPage /></AdminRoute>} />
                <Route path="/compliance" element={<AdminRoute><CompliancePage /></AdminRoute>} />
                <Route path="/audit" element={<AdminRoute><AuditLogsPage /></AdminRoute>} />
                <Route path="/knowledge-shield" element={<AdminRoute><KnowledgeShieldPage /></AdminRoute>} />
                <Route path="/settings" element={<AdminRoute><SettingsPage /></AdminRoute>} />
              </Routes>
            </DashboardLayout>
          </ProtectedRoute>
        }
      />
    </Routes>
  )
}

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <AppRoutes />
      </AuthProvider>
    </BrowserRouter>
  )
}
