import { BrowserRouter, Routes, Route } from 'react-router-dom'
import { ProtectedRoute } from './components/ProtectedRoute'
import { Layout } from './components/Layout'
import { Login } from './pages/Login'
import { NotFound } from './pages/NotFound'

export default function App() {
  return (
    <BrowserRouter basename="/badminton">
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="/*" element={
          <ProtectedRoute>
            <Layout>
              <Routes>
                <Route path="/" element={<div className="p-4 text-white">Sessions — coming soon</div>} />
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
  )
}
