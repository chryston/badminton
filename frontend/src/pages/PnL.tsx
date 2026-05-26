import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../lib/api'
import type { Session, PnLResult, Venue } from '../types'

// TODO: This page makes N+1 API calls (one per completed session) to fetch P&L.
// A future improvement would be a dedicated /api/v1/pnl/summary endpoint that
// returns all session P&L data in a single request.

interface SessionPnL {
  session: Session
  pnl: PnLResult
}

function SkeletonCard() {
  return (
    <div className="rounded-xl bg-gray-800 p-4 animate-pulse border border-gray-700">
      <div className="flex justify-between">
        <div className="space-y-2">
          <div className="h-4 w-36 bg-gray-700 rounded" />
          <div className="h-3 w-24 bg-gray-700 rounded" />
        </div>
        <div className="h-5 w-16 bg-gray-700 rounded" />
      </div>
    </div>
  )
}

export function PnL() {
  const navigate = useNavigate()
  const [items, setItems] = useState<SessionPnL[]>([])
  const [venues, setVenues] = useState<Record<string, string>>({})
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    async function load(signal: AbortSignal) {
      try {
        const [allSessions, venueList] = await Promise.all([
          api.get<Session[]>('/api/v1/sessions', signal),
          api.get<Venue[]>('/api/v1/venues', signal),
        ])
        const venueMap: Record<string, string> = {}
        for (const v of venueList) venueMap[v.id] = v.name
        setVenues(venueMap)

        const completed = allSessions.filter(s => s.status === 'completed')
        completed.sort((a, b) => (a.date < b.date ? 1 : -1))

        // N+1 fetch — acceptable for now, see TODO above
        const results = await Promise.allSettled(
          completed.map(async session => {
            const pnl = await api.get<PnLResult>(
              `/api/v1/sessions/${session.id}/pnl`,
              signal,
            )
            return { session, pnl }
          }),
        )
        const pnlData = results
          .filter((r): r is PromiseFulfilledResult<SessionPnL> => r.status === 'fulfilled')
          .map(r => r.value)
        setItems(pnlData)
      } catch (err) {
        if (err instanceof Error && err.name === 'AbortError') return
        setError(err instanceof Error ? err.message : 'Failed to load P&L data')
      } finally {
        setLoading(false)
      }
    }
    load(controller.signal)
    return () => controller.abort()
  }, [])

  const totalIncome = items.reduce((sum, { pnl }) => sum + pnl.total_fees_collected, 0)
  const totalCourtCost = items.reduce((sum, { pnl }) => sum + pnl.court_cost, 0)
  const totalShuttleCost = items.reduce((sum, { pnl }) => sum + pnl.shuttle_cost, 0)
  const totalNet = items.reduce((sum, { pnl }) => sum + pnl.net, 0)

  return (
    <div className="p-4">
      <h1 className="text-xl font-bold text-white mb-4">Profit &amp; Loss</h1>

      {error && (
        <p className="rounded-lg bg-red-900/50 border border-red-700 px-4 py-3 text-sm text-red-300 mb-4">
          {error}
        </p>
      )}

      {/* Overall summary card */}
      {!loading && items.length > 0 && (
        <div className="rounded-xl bg-gray-800 border border-gray-700 p-4 mb-6">
          <h2 className="text-sm font-semibold text-gray-400 mb-3 uppercase tracking-wide">
            Overall ({items.length} sessions)
          </h2>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <p className="text-xs text-gray-500">Total Income</p>
              <p className="text-lg font-bold text-white">${totalIncome.toFixed(2)}</p>
            </div>
            <div>
              <p className="text-xs text-gray-500">Net P&amp;L</p>
              <p
                className={`text-lg font-bold ${
                  totalNet >= 0 ? 'text-green-400' : 'text-red-400'
                }`}
              >
                {totalNet >= 0 ? '+' : ''}${totalNet.toFixed(2)}
              </p>
            </div>
            <div>
              <p className="text-xs text-gray-500">Court Costs</p>
              <p className="text-sm font-medium text-gray-300">${totalCourtCost.toFixed(2)}</p>
            </div>
            <div>
              <p className="text-xs text-gray-500">Shuttle Costs</p>
              <p className="text-sm font-medium text-gray-300">${totalShuttleCost.toFixed(2)}</p>
            </div>
            <div>
              <p className="text-xs text-gray-500">Total Expenses</p>
              <p className="text-sm font-medium text-gray-300">${(totalCourtCost + totalShuttleCost).toFixed(2)}</p>
            </div>
          </div>
        </div>
      )}

      {loading ? (
        <div className="space-y-3">
          {Array.from({ length: 4 }).map((_, i) => <SkeletonCard key={i} />)}
        </div>
      ) : items.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-16 text-gray-500">
          <span className="text-4xl mb-3">📊</span>
          <p className="text-sm">No completed sessions yet</p>
        </div>
      ) : (
        <div className="space-y-3">
          {items.map(({ session, pnl }) => (
            <button
              key={session.id}
              onClick={() => navigate(`/sessions/${session.id}`)}
              className="w-full rounded-xl bg-gray-800 p-4 text-left hover:bg-gray-700 active:bg-gray-600 transition-colors border border-gray-700"
            >
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <p className="font-semibold text-white">
                    {venues[session.venue_id] ? `${venues[session.venue_id]} • ` : ''}
                    {new Date(`${session.date}T00:00:00`).toLocaleDateString('en-SG', {
                      weekday: 'short',
                      day: 'numeric',
                      month: 'short',
                      year: 'numeric',
                    })}
                  </p>
                  <p className="text-xs text-gray-500 mt-0.5">
                    Income ${pnl.total_fees_collected.toFixed(2)} · Costs $
                    {(pnl.court_cost + pnl.shuttle_cost).toFixed(2)}
                  </p>
                </div>
                <span
                  className={`shrink-0 text-sm font-bold ${
                    pnl.net >= 0 ? 'text-green-400' : 'text-red-400'
                  }`}
                >
                  {pnl.net >= 0 ? '+' : ''}${pnl.net.toFixed(2)}
                </span>
              </div>
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
