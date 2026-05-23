import { Link } from 'react-router-dom'

export function NotFound() {
  return (
    <div className="flex flex-col items-center justify-center min-h-[60vh] gap-4 p-4 text-center">
      <p className="text-6xl">🏸</p>
      <h1 className="text-3xl font-bold text-white">404</h1>
      <p className="text-gray-400">Page not found</p>
      <Link
        to="/"
        className="mt-2 rounded-lg bg-brand-600 px-6 py-2 text-sm font-semibold text-white hover:bg-brand-700 transition-colors"
      >
        Go home
      </Link>
    </div>
  )
}
