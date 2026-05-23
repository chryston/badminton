import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { AuthProvider } from './contexts/AuthContext'
import { ProtectedRoute } from './components/ProtectedRoute'
import { Layout } from './components/Layout'
import { Login } from './pages/Login'
import { NotFound } from './pages/NotFound'
import { Sessions } from './pages/Sessions'
import { NewSession } from './pages/NewSession'
import { SessionDetail } from './pages/SessionDetail'
import { Players } from './pages/Players'
import { Inventory } from './pages/Inventory'
import { PnL } from './pages/PnL'

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
                  <Route path="/players" element={<Players />} />
                  <Route path="/inventory" element={<Inventory />} />
                  <Route path="/pnl" element={<PnL />} />
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
