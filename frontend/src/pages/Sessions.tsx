import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../lib/api'
import { skillRangeLabel } from '../types'
import type { Session, Venue } from '../types'

const STATUS_BADGE: Record<string, string> = {
  internal: 'bg-gray-700 text-gray-300',
  published: 'bg-green-900/60 text-green-300',
  completed: 'bg-blue-900/60 text-blue-300',
}


function SkeletonCard() {
  return (
    <div className="rounded-xl bg-gray-800 p-4 animate-pulse border border-gray-700">
      <div className="flex justify-between">
        <div className="space-y-2 flex-1">
          <div className="h-4 w-36 bg-gray-700 rounded" />
          <div className="h-3 w-48 bg-gray-700 rounded" />
          <div className="h-3 w-32 bg-gray-700 rounded" />
        </div>
        <div className="h-6 w-20 bg-gray-700 rounded-full" />
      </div>
    </div>
  )
}

export function Sessions() {
  const navigate = useNavigate()
  const [sessions, setSessions] = useState<Session[]>([])
  const [venues, setVenues] = useState<Record<string, string>>({})
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    async function load(signal: AbortSignal) {
      try {
        const [sessionList, venueList] = await Promise.all([
          api.get<Session[]>('/api/v1/sessions', signal),
          api.get<Venue[]>('/api/v1/venues', signal),
        ])
        sessionList.sort((a, b) => (a.date < b.date ? 1 : -1))
        setSessions(sessionList)
        const venueMap: Record<string, string> = {}
        for (const v of venueList) venueMap[v.id] = v.name
        setVenues(venueMap)
      } catch (err) {
        if (err instanceof Error && err.name === 'AbortError') return
        setError(err instanceof Error ? err.message : 'Failed to load sessions')
      } finally {
        setLoading(false)
      }
    }
    load(controller.signal)
    return () => controller.abort()
  }, [])

  return (
    <div className="p-4">
      <div className="flex items-center justify-between mb-4">
        <h1 className="text-xl font-bold text-white">Sessions</h1>
        <button
          onClick={() => navigate('/sessions/new')}
          className="rounded-lg bg-brand-600 px-3 py-1.5 text-sm font-semibold text-white hover:bg-brand-700 transition-colors"
        >
          + New Session
        </button>
      </div>

      {error && (
        <p className="rounded-lg bg-red-900/50 border border-red-700 px-4 py-3 text-sm text-red-300 mb-4">
          {error}
        </p>
      )}

      {loading ? (
        <div className="space-y-3">
          {Array.from({ length: 4 }).map((_, i) => <SkeletonCard key={i} />)}
        </div>
      ) : sessions.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-16 text-gray-500">
          <span className="text-4xl mb-3">📅</span>
          <p className="text-sm">No sessions yet</p>
          <button
            onClick={() => navigate('/sessions/new')}
            className="mt-4 rounded-lg bg-brand-600 px-4 py-2 text-sm font-semibold text-white hover:bg-brand-700 transition-colors"
          >
            Create your first session
          </button>
        </div>
      ) : (
        <div className="space-y-3">
          {sessions.map(session => (
            <button
              key={session.id}
              onClick={() => navigate(`/sessions/${session.id}`)}
              className="w-full rounded-xl bg-gray-800 p-4 text-left hover:bg-gray-700 active:bg-gray-600 transition-colors border border-gray-700"
            >
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <p className="font-semibold text-white">
                    {new Date(`${session.date}T00:00:00`).toLocaleDateString('en-SG', {
                      weekday: 'short',
                      day: 'numeric',
                      month: 'short',
                      year: 'numeric',
                    })}
                  </p>
                  <p className="text-sm text-gray-400 mt-0.5">
                    {session.start_time} · {venues[session.venue_id] ?? 'Unknown Venue'}
                  </p>
                  <p className="text-xs text-gray-500 mt-1">
                    {skillRangeLabel(session.min_skill_level, session.max_skill_level)} · {session.courts_booked} · max {session.max_pax}
                  </p>
                </div>
                <span
                  className={`shrink-0 rounded-full px-2.5 py-1 text-xs font-medium capitalize ${STATUS_BADGE[session.status] ?? 'bg-gray-700 text-gray-300'}`}
                >
                  {session.status}
                </span>
              </div>
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
