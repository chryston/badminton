import { NavLink } from 'react-router-dom'
import { useAuth } from '../hooks/useAuth'

const tabs = [
  { to: '/sessions', label: 'Sessions', icon: '📅', end: false },
  { to: '/players', label: 'Players', icon: '👥', end: false },
  { to: '/inventory', label: 'Stock', icon: '🏸', end: false },
  { to: '/pnl', label: 'P&L', icon: '📊', end: false },
]

export function Layout({ children }: { children: React.ReactNode }) {
  const { signOut } = useAuth()

  return (
    <div className="flex flex-col min-h-screen bg-gray-950">
      <header className="flex items-center justify-between px-4 py-3 bg-gray-900 border-b border-gray-800">
        <span className="font-semibold text-white">🏸 Badminton Admin</span>
        <button
          onClick={() => signOut()}
          className="text-sm text-gray-400 hover:text-white transition-colors"
        >
          Sign out
        </button>
      </header>

      <main className="flex-1 overflow-y-auto pb-20">
        {children}
      </main>

      <nav className="fixed bottom-0 left-0 right-0 bg-gray-900 border-t border-gray-800 flex">
        {tabs.map(({ to, label, icon, end }) => (
          <NavLink
            key={to}
            to={to}
            end={end}
            className={({ isActive }) =>
              `flex flex-1 flex-col items-center gap-1 py-2 text-xs transition-colors ${
                isActive ? 'text-brand-500' : 'text-gray-400 hover:text-gray-200'
              }`
            }
          >
            <span className="text-xl leading-none">{icon}</span>
            <span>{label}</span>
          </NavLink>
        ))}
      </nav>
    </div>
  )
}
