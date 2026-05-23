import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { AuthProvider } from './contexts/AuthContext'
import { ProtectedRoute } from './components/ProtectedRoute'
import { Layout } from './components/Layout'
import { Login } from './pages/Login'
import { NotFound } from './pages/NotFound'
import { Sessions } from './pages/Sessions'
import { NewSession } from './pages/NewSession'
import { SessionDetail } from './pages/SessionDetail'

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter basename="/badminton">
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="/*" element={
            <ProtectedRoute>
              <Layout>
                <Routes>
                  <Route path="/" element={<Navigate to="/sessions" replace />} />
                  <Route path="/sessions" element={<Sessions />} />
                  <Route path="/sessions/new" element={<NewSession />} />
                  <Route path="/sessions/:id" element={<SessionDetail />} />
                  <Route path="/players" element={<div className="p-4 text-white">Players — coming soon</div>} />
                  <Route path="/inventory" element={<div className="p-4 text-white">Inventory — coming soon</div>} />
                  <Route path="/pnl" element={<div className="p-4 text-white">P&L — coming soon</div>} />
                  <Route path="*" element={<NotFound />} />
                </Routes>
              </Layout>
            </ProtectedRoute>
          } />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  )
}
