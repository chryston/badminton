import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../lib/api'
import { SKILL_LEVELS, type CourtSlotCreate, type Player, type SkillLevel, type Venue } from '../types'

const INPUT_CLASS =
  'w-full rounded-lg bg-gray-800 border border-gray-700 px-4 py-3 text-white focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500'
const LABEL_CLASS = 'block text-sm font-medium text-gray-300 mb-1'

function computeDay(dateStr: string): string {
  if (!dateStr) return ''
  return new Date(dateStr + 'T00:00:00').toLocaleDateString('en-SG', { weekday: 'long' })
}

function computeEndTime(startTime: string, durationHours: number): string {
  if (!startTime) return ''
  const [h, m] = startTime.split(':').map(Number)
  const totalMinutes = h * 60 + m + Math.round(durationHours * 60)
  const endH = Math.floor(totalMinutes / 60) % 24
  const endM = totalMinutes % 60
  return `${String(endH).padStart(2, '0')}:${String(endM).padStart(2, '0')}`
}

interface SlotRow extends CourtSlotCreate {}

export function NewSession() {
  const navigate = useNavigate()
  const [venues, setVenues] = useState<Venue[]>([])
  const [internalPlayers, setInternalPlayers] = useState<Player[]>([])
  const [loadingData, setLoadingData] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const today = new Date().toISOString().split('T')[0]
  const [date, setDate] = useState(today)
  const [startTime, setStartTime] = useState('20:00')
  const [duration, setDuration] = useState(2)
  const [venueId, setVenueId] = useState('')
  const [numCourts, setNumCourts] = useState(2)
  const [courtsBooked, setCourtsBooked] = useState('')
  const [minSkill, setMinSkill] = useState<SkillLevel>('LI')
  const [maxSkill, setMaxSkill] = useState<SkillLevel>('MI')
  const [pubFee, setPubFee] = useState(0)
  const [maxPax, setMaxPax] = useState(12)
  const [maxPaxCustom, setMaxPaxCustom] = useState(false)
  const [paynowPlayerId, setPaynowPlayerId] = useState('')
  const [slots, setSlots] = useState<SlotRow[]>([
    { court_label: '', from_time: '20:00:00', to_time: '22:00:00', booker_player_id: '' },
  ])

  const day = computeDay(date)
  const endTime = computeEndTime(startTime, duration)

  useEffect(() => {
    async function load() {
      try {
        const [venueList, playerList] = await Promise.all([
          api.get<Venue[]>('/api/v1/venues'),
          api.get<Player[]>('/api/v1/players'),
        ])
        setVenues(venueList)
        const internal = playerList.filter((p) => p.is_internal)
        setInternalPlayers(internal)
        if (venueList.length > 0) {
          setVenueId(venueList[0].id)
          setPubFee(venueList[0].default_pub_fee)
        }
        const belle = internal.find((p) => p.name.toLowerCase() === 'belle')
        if (belle) setPaynowPlayerId(belle.id)
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
    const venue = venues.find((v) => v.id === id)
    if (venue) setPubFee(venue.default_pub_fee)
  }

  function handleNumCourtsChange(val: number) {
    setNumCourts(val)
    if (!maxPaxCustom) setMaxPax(val * 6)
  }

  function handleMaxPaxChange(val: number) {
    setMaxPax(val)
    setMaxPaxCustom(true)
  }

  function addSlot() {
    setSlots((prev) => [
      ...prev,
      {
        court_label: '',
        from_time: startTime + ':00',
        to_time: endTime + ':00',
        booker_player_id: '',
      },
    ])
  }

  function removeSlot(index: number) {
    setSlots((prev) => prev.filter((_, i) => i !== index))
  }

  function updateSlot(index: number, field: keyof SlotRow, value: string) {
    setSlots((prev) => prev.map((s, i) => (i === index ? { ...s, [field]: value } : s)))
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (slots.length === 0) {
      setError('At least one court slot is required')
      return
    }
    setError(null)
    setSubmitting(true)
    try {
      await api.post('/api/v1/sessions', {
        venue_id: venueId,
        date,
        start_time: startTime + ':00',
        duration_hours: duration,
        courts_booked: courtsBooked,
        num_courts: numCourts,
        min_skill_level: minSkill,
        max_skill_level: maxSkill,
        pub_fee: pubFee,
        max_pax: maxPax,
        paynow_player_id: paynowPlayerId || null,
        court_slots: slots,
      })
      navigate('/sessions')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create session')
    } finally {
      setSubmitting(false)
    }
  }

  if (loadingData) return <div className="p-8 text-gray-400">Loading…</div>

  return (
    <div className="max-w-2xl mx-auto">
      <h1 className="text-2xl font-bold text-white mb-6">New Session</h1>
      <form onSubmit={handleSubmit} className="space-y-6">

        {/* Date + Day */}
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className={LABEL_CLASS}>Date</label>
            <input
              type="date" value={date} required
              onChange={(e) => setDate(e.target.value)}
              className={INPUT_CLASS}
            />
          </div>
          <div>
            <label className={LABEL_CLASS}>Day</label>
            <input type="text" value={day} readOnly
              className={INPUT_CLASS + ' opacity-60 cursor-not-allowed'} />
          </div>
        </div>

        {/* Start Time + Duration + End Time */}
        <div className="grid grid-cols-3 gap-4">
          <div>
            <label className={LABEL_CLASS}>Start Time</label>
            <input
              type="time" value={startTime} required
              onChange={(e) => setStartTime(e.target.value)}
              className={INPUT_CLASS}
            />
          </div>
          <div>
            <label className={LABEL_CLASS}>Duration (hrs)</label>
            <input
              type="number" min="0.5" max="8" step="0.5" value={duration} required
              onChange={(e) => setDuration(parseFloat(e.target.value))}
              className={INPUT_CLASS}
            />
          </div>
          <div>
            <label className={LABEL_CLASS}>End Time</label>
            <input type="text" value={endTime} readOnly
              className={INPUT_CLASS + ' opacity-60 cursor-not-allowed'} />
          </div>
        </div>

        {/* Venue */}
        <div>
          <label className={LABEL_CLASS}>Venue</label>
          <select value={venueId} required
            onChange={(e) => handleVenueChange(e.target.value)}
            className={INPUT_CLASS}>
            {venues.map((v) => <option key={v.id} value={v.id}>{v.name}</option>)}
          </select>
        </div>

        {/* Num Courts + Courts Booked */}
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className={LABEL_CLASS}>Num Courts</label>
            <input
              type="number" min="1" value={numCourts} required
              onChange={(e) => handleNumCourtsChange(parseInt(e.target.value))}
              className={INPUT_CLASS}
            />
          </div>
          <div>
            <label className={LABEL_CLASS}>Court Number(s)</label>
            <input
              type="text" placeholder="e.g. Court 3, 4" value={courtsBooked} required
              onChange={(e) => setCourtsBooked(e.target.value)}
              className={INPUT_CLASS}
            />
          </div>
        </div>

        {/* Skill Levels */}
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className={LABEL_CLASS}>Min Skill Level</label>
            <select value={minSkill}
              onChange={(e) => setMinSkill(e.target.value as SkillLevel)}
              className={INPUT_CLASS}>
              {SKILL_LEVELS.map((l) => <option key={l} value={l}>{l}</option>)}
            </select>
          </div>
          <div>
            <label className={LABEL_CLASS}>Max Skill Level</label>
            <select value={maxSkill}
              onChange={(e) => setMaxSkill(e.target.value as SkillLevel)}
              className={INPUT_CLASS}>
              {SKILL_LEVELS.map((l) => <option key={l} value={l}>{l}</option>)}
            </select>
          </div>
        </div>

        {/* Pub Fee + Max Players */}
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className={LABEL_CLASS}>Pub Fee ($)</label>
            <input
              type="number" min="0" step="0.5" value={pubFee} required
              onChange={(e) => setPubFee(parseFloat(e.target.value))}
              className={INPUT_CLASS}
            />
          </div>
          <div>
            <label className={LABEL_CLASS}>Max Players</label>
            <input
              type="number" min="1" value={maxPax} required
              onChange={(e) => handleMaxPaxChange(parseInt(e.target.value))}
              className={INPUT_CLASS}
            />
          </div>
        </div>

        {/* PayNow */}
        <div>
          <label className={LABEL_CLASS}>PayNow Recipient</label>
          <select value={paynowPlayerId}
            onChange={(e) => setPaynowPlayerId(e.target.value)}
            className={INPUT_CLASS}>
            <option value="">None</option>
            {internalPlayers.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
          </select>
        </div>

        {/* Court Slots */}
        <div>
          <div className="flex justify-between items-center mb-2">
            <label className={LABEL_CLASS + ' mb-0'}>Court Slots</label>
            <button type="button" onClick={addSlot}
              className="text-sm text-brand-400 hover:text-brand-300">
              + Add Slot
            </button>
          </div>
          {slots.length === 0 && (
            <p className="text-red-400 text-sm mb-2">At least one court slot is required.</p>
          )}
          <div className="space-y-3">
            {slots.map((slot, i) => (
              <div key={i}
                className="grid grid-cols-4 gap-2 items-end p-3 rounded-lg bg-gray-900 border border-gray-700">
                <div>
                  <label className="block text-xs text-gray-400 mb-1">Court</label>
                  <input type="text" placeholder="Court 1" value={slot.court_label} required
                    onChange={(e) => updateSlot(i, 'court_label', e.target.value)}
                    className={INPUT_CLASS} />
                </div>
                <div>
                  <label className="block text-xs text-gray-400 mb-1">From</label>
                  <input type="time" value={slot.from_time.slice(0, 5)} required
                    onChange={(e) => updateSlot(i, 'from_time', e.target.value + ':00')}
                    className={INPUT_CLASS} />
                </div>
                <div>
                  <label className="block text-xs text-gray-400 mb-1">To</label>
                  <input type="time" value={slot.to_time.slice(0, 5)} required
                    onChange={(e) => updateSlot(i, 'to_time', e.target.value + ':00')}
                    className={INPUT_CLASS} />
                </div>
                <div>
                  <label className="block text-xs text-gray-400 mb-1">Booker</label>
                  <div className="flex gap-1">
                    <select value={slot.booker_player_id} required
                      onChange={(e) => updateSlot(i, 'booker_player_id', e.target.value)}
                      className={INPUT_CLASS}>
                      <option value="">Select</option>
                      {internalPlayers.map((p) => (
                        <option key={p.id} value={p.id}>{p.name}</option>
                      ))}
                    </select>
                    {slots.length > 1 && (
                      <button type="button" onClick={() => removeSlot(i)}
                        className="text-red-400 hover:text-red-300 px-2 shrink-0">
                        ✕
                      </button>
                    )}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>

        {error && <p className="text-red-400 text-sm">{error}</p>}

        <button
          type="submit"
          disabled={submitting || slots.length === 0}
          className="w-full bg-brand-600 hover:bg-brand-500 text-white font-semibold py-3 px-6 rounded-lg transition disabled:opacity-50">
          {submitting ? 'Creating…' : 'Create Session'}
        </button>
      </form>
    </div>
  )
}
