import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../lib/api'
import type { Venue, Player, SkillLevel, Session } from '../types'

const INPUT_CLASS =
  'w-full rounded-lg bg-gray-800 border border-gray-700 px-4 py-3 text-white focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500'
const LABEL_CLASS = 'block text-sm font-medium text-gray-300 mb-1'

export function NewSession() {
  const navigate = useNavigate()
  const [venues, setVenues] = useState<Venue[]>([])
  const [players, setPlayers] = useState<Player[]>([])
  const [loadingData, setLoadingData] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const today = new Date().toISOString().split('T')[0]
  const [date, setDate] = useState(today)
  const [time, setTime] = useState('20:00')
  const [venueId, setVenueId] = useState('')
  const [courtsBooked, setCourtsBooked] = useState(2)
  const [skillLevel, setSkillLevel] = useState<SkillLevel>('LI')
  const [pubFee, setPubFee] = useState(0)
  const [maxPax, setMaxPax] = useState(12)
  const [paynowPlayerId, setPaynowPlayerId] = useState('')

  useEffect(() => {
    async function load() {
      try {
        const [venueList, playerList] = await Promise.all([
          api.get<Venue[]>('/api/v1/venues'),
          api.get<Player[]>('/api/v1/players'),
        ])
        setVenues(venueList)
        if (venueList.length > 0) {
          setVenueId(venueList[0].id)
          setPubFee(venueList[0].default_pub_fee)
        }
        setPlayers(playerList.filter(p => p.is_internal))
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load data')
      } finally {
        setLoadingData(false)
      }
    }
    load()
  }, [])

  function handleVenueChange(id: string) {
    setVenueId(id)
    const venue = venues.find(v => v.id === id)
    if (venue) setPubFee(venue.default_pub_fee)
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    setSubmitting(true)
    try {
      const session = await api.post<Session>('/api/v1/sessions', {
        date,
        time,
        venue_id: venueId,
        courts_booked: courtsBooked,
        skill_level: skillLevel,
        pub_fee: pubFee,
        max_pax: maxPax,
        paynow_player_id: paynowPlayerId || null,
      })
      navigate(`/sessions/${session.id}`)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create session')
    } finally {
      setSubmitting(false)
    }
  }

  if (loadingData) {
    return (
      <div className="flex items-center justify-center py-16">
        <span className="text-gray-400 animate-pulse">Loading…</span>
      </div>
    )
  }

  return (
    <div className="p-4 pb-8">
      <div className="flex items-center gap-3 mb-6">
        <button
          onClick={() => navigate(-1)}
          className="text-2xl text-gray-400 hover:text-white leading-none"
          aria-label="Go back"
        >
          ‹
        </button>
        <h1 className="text-xl font-bold text-white">New Session</h1>
      </div>

      {error && (
        <p className="rounded-lg bg-red-900/50 border border-red-700 px-4 py-3 text-sm text-red-300 mb-4">
          {error}
        </p>
      )}

      <form onSubmit={handleSubmit} className="space-y-4">
        <div>
          <label className={LABEL_CLASS}>Date</label>
          <input
            type="date"
            value={date}
            onChange={e => setDate(e.target.value)}
            required
            className={INPUT_CLASS}
          />
        </div>

        <div>
          <label className={LABEL_CLASS}>Time</label>
          <input
            type="time"
            value={time}
            onChange={e => setTime(e.target.value)}
            required
            className={INPUT_CLASS}
          />
        </div>

        <div>
          <label className={LABEL_CLASS}>Venue</label>
          <select
            value={venueId}
            onChange={e => handleVenueChange(e.target.value)}
            required
            className={INPUT_CLASS}
          >
            {venues.map(v => (
              <option key={v.id} value={v.id}>{v.name}</option>
            ))}
          </select>
        </div>

        <div>
          <label className={LABEL_CLASS}>Courts Booked</label>
          <input
            type="number"
            value={courtsBooked}
            min={1}
            max={10}
            onChange={e => setCourtsBooked(Number(e.target.value))}
            required
            className={INPUT_CLASS}
          />
        </div>

        <div>
          <label className={LABEL_CLASS}>Skill Level</label>
          <select
            value={skillLevel}
            onChange={e => setSkillLevel(e.target.value as SkillLevel)}
            required
            className={INPUT_CLASS}
          >
            <option value="HB">High Beginner (HB)</option>
            <option value="LI">Low Intermediate (LI)</option>
            <option value="MB">Mid Beginner (MB)</option>
          </select>
        </div>

        <div>
          <label className={LABEL_CLASS}>Pub Fee ($)</label>
          <input
            type="number"
            value={pubFee}
            min={0}
            step={0.01}
            onChange={e => setPubFee(Number(e.target.value))}
            required
            className={INPUT_CLASS}
          />
        </div>

        <div>
          <label className={LABEL_CLASS}>Max Players</label>
          <input
            type="number"
            value={maxPax}
            min={1}
            max={100}
            onChange={e => setMaxPax(Number(e.target.value))}
            required
            className={INPUT_CLASS}
          />
        </div>

        <div>
          <label className={LABEL_CLASS}>PayNow Player <span className="text-gray-500">(optional)</span></label>
          <select
            value={paynowPlayerId}
            onChange={e => setPaynowPlayerId(e.target.value)}
            className={INPUT_CLASS}
          >
            <option value="">— None —</option>
            {players.map(p => (
              <option key={p.id} value={p.id}>{p.name}</option>
            ))}
          </select>
        </div>

        <button
          type="submit"
          disabled={submitting}
          className="w-full rounded-lg bg-brand-600 px-4 py-3 font-semibold text-white hover:bg-brand-700 focus:outline-none focus:ring-2 focus:ring-brand-500 focus:ring-offset-2 focus:ring-offset-gray-950 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        >
          {submitting ? 'Creating…' : 'Create Session'}
        </button>
      </form>
    </div>
  )
}
