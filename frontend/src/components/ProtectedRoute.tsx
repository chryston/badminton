import { Navigate } from 'react-router-dom'
import { useAuth } from '../hooks/useAuth'

export function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { session, loading } = useAuth()
  if (loading) return <div className="flex h-screen items-center justify-center text-gray-400">Loading...</div>
  if (!session) return <Navigate to="/login" replace />
  return <>{children}</>
}
