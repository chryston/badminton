import { useState, useEffect, useCallback } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { api } from '../lib/api'
import { skillRangeLabel, SKILL_LEVELS } from '../types'
import type {
  Session,
  RosterEntry,
  Player,
  ShuttleBatch,
  PnLResult,
  Venue,
  SessionStatus,
  PaymentStatus,
  CourtSlot,
  SkillLevel,
} from '../types'

// ─── helpers ─────────────────────────────────────────────────────────────────

const STATUS_BADGE: Record<SessionStatus, string> = {
  internal: 'bg-gray-700 text-gray-300',
  published: 'bg-green-900/60 text-green-300',
  completed: 'bg-blue-900/60 text-blue-300',
  cancelled: 'bg-red-900/60 text-red-300',
}

const PAYMENT_BADGE: Record<PaymentStatus, string> = {
  unpaid: 'bg-red-900/60 text-red-300',
  pending_verification: 'bg-yellow-900/60 text-yellow-300',
  verified_paid: 'bg-green-900/60 text-green-300',
}

const PAYMENT_LABEL: Record<PaymentStatus, string> = {
  unpaid: 'Unpaid',
  pending_verification: 'Pending',
  verified_paid: 'Paid ✓',
}


function playerDisplayName(entry: RosterEntry, playersById: Record<string, Player>): string {
  if (entry.player_type === 'guest') return entry.guest_name ?? 'Guest'
  if (entry.player_id) return playersById[entry.player_id]?.name ?? 'Unknown'
  return 'Unknown'
}

function playerTypeBadge(entry: RosterEntry, playersById: Record<string, Player>): string {
  if (entry.player_type === 'guest') return 'Guest'
  if (entry.player_id) {
    const player = playersById[entry.player_id]
    if (player?.is_internal) return 'Member'
    return 'Public'
  }
  return 'Member'
}

// ─── sub-components ───────────────────────────────────────────────────────────

function Spinner() {
  return <span className="inline-block animate-spin text-xl">⟳</span>
}

interface ShuttleModalProps {
  batches: ShuttleBatch[]
  onClose: () => void
  onConfirm: (usages: { batch_id: string; count_used: number }[]) => Promise<void>
}

function ShuttleModal({ batches, onClose, onConfirm }: ShuttleModalProps) {
  const [quantities, setQuantities] = useState<Record<string, number>>(() => {
    const init: Record<string, number> = {}
    for (const b of batches) init[b.id] = 0
    return init
  })
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    setSubmitting(true)
    const usages = Object.entries(quantities)
      .filter(([, qty]) => qty > 0)
      .map(([batch_id, qty]) => ({ batch_id, count_used: qty }))
    try {
      await onConfirm(usages)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to complete session')
      setSubmitting(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/70 px-4 pb-4">
      <div className="w-full max-w-md rounded-2xl bg-gray-900 border border-gray-700 p-5">
        <h2 className="text-lg font-bold text-white mb-1">Complete Session</h2>
        <p className="text-sm text-gray-400 mb-4">Enter shuttles used from each batch.</p>

        {error && (
          <p className="rounded-lg bg-red-900/50 border border-red-700 px-3 py-2 text-sm text-red-300 mb-3">
            {error}
          </p>
        )}

        <form onSubmit={handleSubmit} className="space-y-3">
          {batches.length === 0 && (
            <p className="text-sm text-gray-400">No active shuttle batches found.</p>
          )}
          {batches.map(batch => (
            <div key={batch.id} className="flex items-center gap-3">
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium text-white truncate">{batch.batch_name}</p>
                <p className="text-xs text-gray-500">{batch.brand} · {batch.remaining_count} remaining</p>
              </div>
              <input
                type="number"
                value={quantities[batch.id] ?? 0}
                min={0}
                max={batch.remaining_count}
                onChange={e => setQuantities(prev => ({ ...prev, [batch.id]: Number(e.target.value) }))}
                className="w-20 rounded-lg bg-gray-800 border border-gray-700 px-3 py-2 text-white text-center focus:border-brand-500 focus:outline-none"
              />
            </div>
          ))}

          <div className="flex gap-3 pt-2">
            <button
              type="button"
              onClick={onClose}
              disabled={submitting}
              className="flex-1 rounded-lg border border-gray-700 px-4 py-2.5 text-sm font-semibold text-gray-300 hover:bg-gray-800 transition-colors disabled:opacity-50"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={submitting}
              className="flex-1 rounded-lg bg-brand-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-brand-700 transition-colors disabled:opacity-50"
            >
              {submitting ? 'Completing…' : 'Complete'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

// ─── main component ───────────────────────────────────────────────────────────

export function SessionDetail() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()

  const [session, setSession] = useState<Session | null>(null)
  const [venueName, setVenueName] = useState<string>('')
  const [roster, setRoster] = useState<RosterEntry[]>([])
  const [playersById, setPlayersById] = useState<Record<string, Player>>({})
  const [pnl, setPnl] = useState<PnLResult | null>(null)
  const [courtSlots, setCourtSlots] = useState<CourtSlot[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // action states
  const [editing, setEditing] = useState(false)
  const [editError, setEditError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [editForm, setEditForm] = useState<Partial<Session>>({})
  const [venues, setVenues] = useState<Venue[]>([])

  // action states
  const [publishing, setPublishing] = useState(false)
  const [showCompleteModal, setShowCompleteModal] = useState(false)
  const [activeBatches, setActiveBatches] = useState<ShuttleBatch[]>([])
  const [verifyingId, setVerifyingId] = useState<string | null>(null)
  const [removingId, setRemovingId] = useState<string | null>(null)
  const [guestName, setGuestName] = useState('')
  const [addingGuest, setAddingGuest] = useState(false)
  const [actionError, setActionError] = useState<string | null>(null)

  const [showCancelModal, setShowCancelModal] = useState(false)
  const [cancelReason, setCancelReason] = useState('')
  const [cancelling, setCancelling] = useState(false)
  const [cancelError, setCancelError] = useState<string | null>(null)

  const loadRoster = useCallback(async () => {
    if (!id) return
    const entries = await api.get<RosterEntry[]>(`/api/v1/sessions/${id}/roster`)
    setRoster(entries)
  }, [id])

  const loadPnl = useCallback(async () => {
    if (!id) return
    const result = await api.get<PnLResult>(`/api/v1/sessions/${id}/pnl`)
    setPnl(result)
  }, [id])

  useEffect(() => {
    if (!id) return
    setLoading(true)
    setSession(null)
    setError(null)
    const controller = new AbortController()
    async function load(signal: AbortSignal) {
      try {
        const [sess, venueList, rosterEntries, playerList, courtSlotData] = await Promise.all([
          api.get<Session>(`/api/v1/sessions/${id}`, signal),
          api.get<Venue[]>('/api/v1/venues', signal),
          api.get<RosterEntry[]>(`/api/v1/sessions/${id}/roster`, signal),
          api.get<Player[]>('/api/v1/players', signal),
          api.get<CourtSlot[]>(`/api/v1/sessions/${id}/court-slots`, signal),
        ])
        setSession(sess)
        const venue = venueList.find(v => v.id === sess.venue_id)
        setVenueName(venue?.name ?? 'Unknown Venue')
        setVenues(venueList)
        setRoster(rosterEntries)
        setCourtSlots(courtSlotData)
        const map: Record<string, Player> = {}
        for (const p of playerList) map[p.id] = p
        setPlayersById(map)
        if (sess.status === 'completed') {
          const result = await api.get<PnLResult>(`/api/v1/sessions/${id}/pnl`, signal)
          setPnl(result)
        }
      } catch (err) {
        if (err instanceof Error && err.name === 'AbortError') return
        setError(err instanceof Error ? err.message : 'Failed to load session')
      } finally {
        setLoading(false)
      }
    }
    load(controller.signal)
    return () => controller.abort()
  }, [id])

  async function handlePublish() {
    if (!id) return
    setActionError(null)
    setPublishing(true)
    try {
      const updated = await api.post<Session>(`/api/v1/sessions/${id}/publish`, {})
      setSession(updated)
    } catch (err) {
      setActionError(err instanceof Error ? err.message : 'Failed to publish session')
    } finally {
      setPublishing(false)
    }
  }

  async function handleOpenCompleteModal() {
    setActionError(null)
    try {
      const batches = await api.get<ShuttleBatch[]>('/api/v1/inventory')
      setActiveBatches(batches.filter(b => b.is_active))
      setShowCompleteModal(true)
    } catch (err) {
      setActionError(err instanceof Error ? err.message : 'Failed to load inventory')
    }
  }

  async function handleComplete(usages: { batch_id: string; count_used: number }[]) {
    if (!id) return
    const updated = await api.post<Session>(`/api/v1/sessions/${id}/complete`, usages)
    setSession(updated)
    setShowCompleteModal(false)
    try {
      await loadPnl()
    } catch (err) {
      // P&L fetch failed but session was completed — show warning not error
      setError('Session completed but P&L could not be loaded. Please refresh.')
    }
  }

  async function handleCancel() {
    if (!id || !cancelReason.trim()) return
    setCancelling(true)
    setCancelError(null)
    try {
      const updated = await api.post<Session>(`/api/v1/sessions/${id}/cancel`, { reason: cancelReason })
      setSession(updated)
      setShowCancelModal(false)
      setCancelReason('')
    } catch (err) {
      setCancelError(err instanceof Error ? err.message : 'Failed to cancel session')
    } finally {
      setCancelling(false)
    }
  }

  async function handleVerify(entryId: string) {
    if (!id) return
    setActionError(null)
    setVerifyingId(entryId)
    // optimistic update
    setRoster(prev =>
      prev.map(e => e.id === entryId ? { ...e, payment_status: 'verified_paid' as PaymentStatus } : e)
    )
    try {
      await api.post(`/api/v1/sessions/${id}/roster/${entryId}/verify`, {})
    } catch (err) {
      // revert
      setRoster(prev =>
        prev.map(e => e.id === entryId ? { ...e, payment_status: 'pending_verification' as PaymentStatus } : e)
      )
      setActionError(err instanceof Error ? err.message : 'Failed to verify payment')
    } finally {
      setVerifyingId(null)
    }
  }

  async function handleRemove(entryId: string) {
    if (!id) return
    if (!window.confirm('Remove this player from the session?')) return
    setActionError(null)
    setRemovingId(entryId)
    try {
      await api.delete(`/api/v1/sessions/${id}/roster/${entryId}`)
      await loadRoster()
    } catch (err) {
      setActionError(err instanceof Error ? err.message : 'Failed to remove player')
    } finally {
      setRemovingId(null)
    }
  }

  async function handleAddGuest(e: React.FormEvent) {
    e.preventDefault()
    if (!id || !guestName.trim()) return
    setActionError(null)
    setAddingGuest(true)
    try {
      await api.post(`/api/v1/sessions/${id}/roster/guest`, { guest_name: guestName.trim() })
      setGuestName('')
      await loadRoster()
    } catch (err) {
      setActionError(err instanceof Error ? err.message : 'Failed to add guest')
    } finally {
      setAddingGuest(false)
    }
  }

  function openEdit() {
    if (!session) return
    setEditForm(session)
    setEditing(true)
  }

  async function handleSaveEdit() {
    if (!id) return
    setSaving(true)
    setEditError(null)
    try {
      const payload: Record<string, unknown> = {
        venue_id: editForm.venue_id || undefined,
        date: editForm.date,
        start_time: editForm.start_time,
        duration_hours: editForm.duration_hours,
        courts_booked: editForm.courts_booked,
        num_courts: editForm.num_courts,
        min_skill_level: editForm.min_skill_level,
        max_skill_level: editForm.max_skill_level,
        pub_fee: editForm.pub_fee,
        max_pax: editForm.max_pax,
        paynow_player_id: editForm.paynow_player_id || null,
      }
      const updated = await api.patch<Session>(`/api/v1/sessions/${id}`, payload)
      setSession(updated)
      const newVenue = venues.find(v => v.id === updated.venue_id)
      if (newVenue) setVenueName(newVenue.name)
      setEditing(false)
    } catch (err) {
      setEditError(err instanceof Error ? err.message : 'Failed to save')
    } finally {
      setSaving(false)
    }
  }

  // ─── render states ──────────────────────────────────────────────────────────

  if (loading) {
    return (
      <div className="p-4 space-y-4 animate-pulse">
        <div className="flex items-center gap-3 mb-6">
          <div className="h-6 w-6 bg-gray-700 rounded" />
          <div className="h-6 w-40 bg-gray-700 rounded" />
        </div>
        <div className="h-32 bg-gray-800 rounded-xl" />
        <div className="h-20 bg-gray-800 rounded-xl" />
        <div className="h-48 bg-gray-800 rounded-xl" />
      </div>
    )
  }

  if (error || !session) {
    return (
      <div className="p-4">
        <button onClick={() => navigate(-1)} className="text-gray-400 hover:text-white mb-4 text-2xl">‹</button>
        <p className="rounded-lg bg-red-900/50 border border-red-700 px-4 py-3 text-sm text-red-300">
          {error ?? 'Session not found'}
        </p>
      </div>
    )
  }

  const activeRoster = roster.filter(e => !e.is_waitlisted).sort((a, b) => a.position - b.position)
  const waitlist = roster.filter(e => e.is_waitlisted).sort((a, b) => a.position - b.position)

  const sessionDate = new Date(`${session.date}T00:00:00`).toLocaleDateString('en-SG', {
    weekday: 'long', day: 'numeric', month: 'short', year: 'numeric',
  })

  return (
    <div className="p-4 pb-8">
      {/* Header */}
      <div className="flex items-center gap-3 mb-4">
        <button
          onClick={() => navigate(-1)}
          className="text-2xl text-gray-400 hover:text-white leading-none"
          aria-label="Go back"
        >
          ‹
        </button>
        <h1 className="text-xl font-bold text-white truncate">{sessionDate}</h1>
      </div>

      {/* Action error */}
      {actionError && (
        <p className="rounded-lg bg-red-900/50 border border-red-700 px-4 py-3 text-sm text-red-300 mb-4">
          {actionError}
        </p>
      )}

      {/* Edit form panel */}
      {editing && (
        <div className="rounded-xl bg-gray-800 border border-brand-600 p-4 mb-4 space-y-3">
          <h2 className="font-semibold text-white">Edit Session</h2>
          {editError && (
            <p className="text-sm text-red-300 bg-red-900/40 border border-red-700 rounded-lg px-3 py-2">{editError}</p>
          )}

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-xs text-gray-400">Date</label>
              <input type="date" value={editForm.date ?? ''} onChange={e => setEditForm(prev => ({...prev, date: e.target.value}))}
                className="w-full rounded-lg bg-gray-900 border border-gray-700 px-3 py-2 text-sm text-white" />
            </div>
            <div>
              <label className="text-xs text-gray-400">Start Time</label>
              <input type="time" value={(editForm.start_time ?? '').slice(0, 5)} onChange={e => setEditForm(prev => ({...prev, start_time: e.target.value + ':00'}))}
                className="w-full rounded-lg bg-gray-900 border border-gray-700 px-3 py-2 text-sm text-white" />
            </div>
            <div>
              <label className="text-xs text-gray-400">Duration (hours)</label>
              <input type="number" step="0.5" min="0.5" value={editForm.duration_hours ?? 2} onChange={e => { const v = parseFloat(e.target.value); if (!isNaN(v)) setEditForm(prev => ({...prev, duration_hours: v})) }}
                className="w-full rounded-lg bg-gray-900 border border-gray-700 px-3 py-2 text-sm text-white" />
            </div>
            <div>
              <label className="text-xs text-gray-400">Venue</label>
              <select value={editForm.venue_id ?? ''} onChange={e => setEditForm(prev => ({...prev, venue_id: e.target.value}))}
                className="w-full rounded-lg bg-gray-900 border border-gray-700 px-3 py-2 text-sm text-white">
                {venues.map(v => <option key={v.id} value={v.id}>{v.name}</option>)}
              </select>
            </div>
            <div>
              <label className="text-xs text-gray-400">Courts Booked</label>
              <input type="text" value={editForm.courts_booked ?? ''} onChange={e => setEditForm(prev => ({...prev, courts_booked: e.target.value}))}
                className="w-full rounded-lg bg-gray-900 border border-gray-700 px-3 py-2 text-sm text-white" />
            </div>
            <div>
              <label className="text-xs text-gray-400">Num Courts</label>
              <input type="number" min="1" value={editForm.num_courts ?? 1} onChange={e => { const v = parseInt(e.target.value); if (!isNaN(v)) setEditForm(prev => ({...prev, num_courts: v})) }}
                className="w-full rounded-lg bg-gray-900 border border-gray-700 px-3 py-2 text-sm text-white" />
            </div>
            <div>
              <label className="text-xs text-gray-400">Min Skill</label>
              <select value={editForm.min_skill_level ?? 'HB'} onChange={e => setEditForm(prev => ({...prev, min_skill_level: e.target.value as SkillLevel}))}
                className="w-full rounded-lg bg-gray-900 border border-gray-700 px-3 py-2 text-sm text-white">
                {SKILL_LEVELS.map(s => <option key={s} value={s}>{s}</option>)}
              </select>
            </div>
            <div>
              <label className="text-xs text-gray-400">Max Skill</label>
              <select value={editForm.max_skill_level ?? 'LI'} onChange={e => setEditForm(prev => ({...prev, max_skill_level: e.target.value as SkillLevel}))}
                className="w-full rounded-lg bg-gray-900 border border-gray-700 px-3 py-2 text-sm text-white">
                {SKILL_LEVELS.map(s => <option key={s} value={s}>{s}</option>)}
              </select>
            </div>
            <div>
              <label className="text-xs text-gray-400">Pub Fee ($)</label>
              <input type="number" step="0.5" min="0" value={editForm.pub_fee ?? 0} onChange={e => { const v = parseFloat(e.target.value); if (!isNaN(v)) setEditForm(prev => ({...prev, pub_fee: v})) }}
                className="w-full rounded-lg bg-gray-900 border border-gray-700 px-3 py-2 text-sm text-white" />
            </div>
            <div>
              <label className="text-xs text-gray-400">Max Players</label>
              <input type="number" min="1" value={editForm.max_pax ?? 12} onChange={e => { const v = parseInt(e.target.value); if (!isNaN(v)) setEditForm(prev => ({...prev, max_pax: v})) }}
                className="w-full rounded-lg bg-gray-900 border border-gray-700 px-3 py-2 text-sm text-white" />
            </div>
          </div>

          <div>
            <label className="text-xs text-gray-400">PayNow Player ID (UUID)</label>
            <input type="text" value={editForm.paynow_player_id ?? ''} onChange={e => setEditForm(prev => ({...prev, paynow_player_id: e.target.value || undefined}))}
              placeholder="leave blank for default"
              className="w-full rounded-lg bg-gray-900 border border-gray-700 px-3 py-2 text-sm text-white" />
          </div>

          <div className="flex gap-2 pt-1">
            <button onClick={handleSaveEdit} disabled={saving}
              className="flex-1 rounded-lg bg-brand-600 px-4 py-2 text-sm font-semibold text-white hover:bg-brand-700 disabled:opacity-50">
              {saving ? 'Saving…' : 'Save Changes'}
            </button>
            <button onClick={() => { setEditing(false); setEditError(null) }}
              className="rounded-lg border border-gray-600 px-4 py-2 text-sm text-gray-300 hover:bg-gray-700">
              Cancel
            </button>
          </div>
        </div>
      )}

      {/* Session info card */}
      <div className="rounded-xl bg-gray-800 border border-gray-700 p-4 mb-4 space-y-2">
        <div className="flex items-center justify-between">
          <p className="text-white font-semibold">{session.start_time} · {venueName}</p>
          <span className={`rounded-full px-2.5 py-1 text-xs font-medium capitalize ${STATUS_BADGE[session.status]}`}>
            {session.status}
          </span>
        </div>
        <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-sm text-gray-400">
          <span>Courts: <span className="text-gray-200">{session.courts_booked}</span></span>
          <span>Level: <span className="text-gray-200">{skillRangeLabel(session.min_skill_level, session.max_skill_level)}</span></span>
          <span>Pub fee: <span className="text-gray-200">${session.pub_fee.toFixed(2)}</span></span>
          <span>Max pax: <span className="text-gray-200">{session.max_pax}</span></span>
        </div>
      </div>

      {/* Action buttons */}
      <div className="mb-4 space-y-2">
        {session.status !== 'completed' && session.status !== 'cancelled' && (
          <button
            onClick={openEdit}
            className="rounded-lg border border-gray-600 px-3 py-1.5 text-sm text-gray-300 hover:bg-gray-700"
          >
            ✏️ Edit
          </button>
        )}
        {session.status === 'internal' && (
          <button
            onClick={handlePublish}
            disabled={publishing}
            className="w-full rounded-lg bg-green-700 px-4 py-3 font-semibold text-white hover:bg-green-600 disabled:opacity-50 disabled:cursor-not-allowed transition-colors flex items-center justify-center gap-2"
          >
            {publishing ? <><Spinner /> Publishing…</> : '📢 Publish to Telegram'}
          </button>
        )}
        {session.status === 'published' && (
          <button
            onClick={handleOpenCompleteModal}
            className="w-full rounded-lg bg-blue-700 px-4 py-3 font-semibold text-white hover:bg-blue-600 transition-colors"
          >
            ✅ Complete Session
          </button>
        )}
        {(session.status === 'internal' || session.status === 'published') && (
          <button
            onClick={() => setShowCancelModal(true)}
            className="rounded-lg border border-red-700 px-3 py-1.5 text-sm font-medium text-red-300 hover:bg-red-900/30"
          >
            🚫 Cancel Session
          </button>
        )}
        {session.status === 'completed' && pnl && (
          <div className="rounded-xl bg-gray-800 border border-gray-700 p-4">
            <h2 className="text-white font-semibold mb-3">P&amp;L Summary</h2>
            <div className="space-y-1.5 text-sm">
              <div className="flex justify-between">
                <span className="text-gray-400">Income</span>
                <span className="text-white">${pnl.total_fees_collected.toFixed(2)}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-400">Court cost</span>
                <span className="text-white">−${pnl.court_cost.toFixed(2)}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-400">Shuttle cost</span>
                <span className="text-white">−${pnl.shuttle_cost.toFixed(2)}</span>
              </div>
              <div className="flex justify-between border-t border-gray-700 pt-1.5 font-semibold">
                <span className="text-gray-300">Net</span>
                <span className={pnl.net >= 0 ? 'text-green-400' : 'text-red-400'}>
                  {pnl.net >= 0 ? '+' : ''}${pnl.net.toFixed(2)}
                </span>
              </div>
              <div className="flex justify-between text-xs text-gray-500 pt-1">
                <span>Total players: {pnl.total_roster_count}</span>
                <span>Ext. paid: {pnl.external_paid_count}</span>
              </div>
              {pnl.booker_breakdown.length > 0 && (
                <div className="mt-3 border-t border-gray-700 pt-3">
                  <p className="text-xs font-medium text-gray-400 mb-1">Court reimbursements</p>
                  {pnl.booker_breakdown.map((b) => (
                    <div key={b.player_id} className="flex justify-between text-sm text-gray-300">
                      <span>{b.player_name}</span>
                      <span>${b.amount.toFixed(2)}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}
      </div>

      {/* Court Slots */}
      <section className="rounded-xl bg-gray-800 p-4 border border-gray-700 mb-4">
        <h2 className="text-lg font-semibold text-white mb-3">Court Slots</h2>
        {courtSlots.length === 0 ? (
          <p className="text-gray-500 text-sm">No court slots recorded.</p>
        ) : (
          <table className="w-full text-sm text-gray-300">
            <thead>
              <tr className="text-gray-500 text-xs border-b border-gray-700">
                <th className="text-left pb-2">Court</th>
                <th className="text-left pb-2">From</th>
                <th className="text-left pb-2">To</th>
                <th className="text-left pb-2">Booker</th>
              </tr>
            </thead>
            <tbody>
              {courtSlots.map((slot) => (
                <tr key={slot.id} className="border-b border-gray-700/50">
                  <td className="py-1.5">{slot.court_label}</td>
                  <td className="py-1.5">{slot.from_time.slice(0, 5)}</td>
                  <td className="py-1.5">{slot.to_time.slice(0, 5)}</td>
                  <td className="py-1.5">{playersById[slot.booker_player_id]?.name ?? slot.booker_player_id.slice(0, 8)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      {/* Roster */}
      <div className="rounded-xl bg-gray-800 border border-gray-700 p-4 mb-4">
        <div className="flex items-center justify-between mb-3">
          <h2 className="font-semibold text-white">
            Roster
            <span className="ml-2 text-sm font-normal text-gray-400">
              {activeRoster.length} / {session.max_pax}
            </span>
          </h2>
        </div>

        {/* Add Guest */}
        <form onSubmit={handleAddGuest} className="flex gap-2 mb-4">
          <input
            type="text"
            placeholder="Guest name…"
            value={guestName}
            onChange={e => setGuestName(e.target.value)}
            className="flex-1 rounded-lg bg-gray-700 border border-gray-600 px-3 py-2 text-sm text-white placeholder-gray-500 focus:border-brand-500 focus:outline-none"
          />
          <button
            type="submit"
            disabled={addingGuest || !guestName.trim()}
            className="rounded-lg bg-brand-600 px-3 py-2 text-sm font-semibold text-white hover:bg-brand-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            {addingGuest ? '…' : '+ Add'}
          </button>
        </form>

        {/* Active players */}
        {activeRoster.length === 0 ? (
          <p className="text-sm text-gray-500 text-center py-3">No players yet</p>
        ) : (
          <div className="space-y-2">
            {activeRoster.map(entry => (
              <RosterRow
                key={entry.id}
                entry={entry}
                name={playerDisplayName(entry, playersById)}
                typeBadge={playerTypeBadge(entry, playersById)}
                onVerify={handleVerify}
                onRemove={handleRemove}
                verifying={verifyingId === entry.id}
                removing={removingId === entry.id}
              />
            ))}
          </div>
        )}

        {/* Waitlist */}
        {waitlist.length > 0 && (
          <>
            <div className="mt-4 mb-2 flex items-center gap-2">
              <div className="flex-1 h-px bg-gray-700" />
              <span className="text-xs text-gray-500 font-medium">Waitlist ({waitlist.length})</span>
              <div className="flex-1 h-px bg-gray-700" />
            </div>
            <div className="space-y-2">
              {waitlist.map(entry => (
                <RosterRow
                  key={entry.id}
                  entry={entry}
                  name={playerDisplayName(entry, playersById)}
                  typeBadge={playerTypeBadge(entry, playersById)}
                  onVerify={handleVerify}
                  onRemove={handleRemove}
                  verifying={verifyingId === entry.id}
                  removing={removingId === entry.id}
                  waitlisted
                />
              ))}
            </div>
          </>
        )}
      </div>

      {/* Complete Session Modal */}
      {showCompleteModal && (
        <ShuttleModal
          batches={activeBatches}
          onClose={() => setShowCompleteModal(false)}
          onConfirm={handleComplete}
        />
      )}

      {/* Cancel Session Modal */}
      {showCancelModal && (
        <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/70 px-4 pb-4">
          <div className="w-full max-w-md rounded-2xl bg-gray-900 border border-gray-700 p-5">
            <h2 className="text-lg font-bold text-white mb-1">Cancel Session</h2>
            <p className="text-sm text-gray-400 mb-4">
              This will notify all players via Telegram. Please provide a reason.
            </p>
            {cancelError && (
              <p className="rounded-lg bg-red-900/50 border border-red-700 px-3 py-2 text-sm text-red-300 mb-3">
                {cancelError}
              </p>
            )}
            <textarea
              value={cancelReason}
              onChange={e => setCancelReason(e.target.value)}
              rows={3}
              placeholder="e.g. Not enough players signed up"
              className="w-full rounded-lg bg-gray-800 border border-gray-700 px-3 py-2 text-sm text-white resize-none mb-4"
            />
            <div className="flex gap-2">
              <button
                onClick={handleCancel}
                disabled={cancelling || !cancelReason.trim()}
                className="flex-1 rounded-lg bg-red-700 px-4 py-2 text-sm font-semibold text-white hover:bg-red-600 disabled:opacity-50"
              >
                {cancelling ? 'Cancelling…' : 'Confirm Cancel'}
              </button>
              <button
                onClick={() => { setShowCancelModal(false); setCancelError(null) }}
                className="rounded-lg border border-gray-600 px-4 py-2 text-sm text-gray-300 hover:bg-gray-700"
              >
                Back
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

// ─── RosterRow sub-component ──────────────────────────────────────────────────

interface RosterRowProps {
  entry: RosterEntry
  name: string
  typeBadge: string
  onVerify: (id: string) => void
  onRemove: (id: string) => void
  verifying: boolean
  removing: boolean
  waitlisted?: boolean
}

function RosterRow({ entry, name, typeBadge, onVerify, onRemove, verifying, removing, waitlisted }: RosterRowProps) {
  return (
    <div className={`flex items-center gap-2 py-2 border-b border-gray-700 last:border-0 ${waitlisted ? 'opacity-60' : ''}`}>
      <span className="text-xs text-gray-500 w-5 text-right shrink-0">{entry.position}.</span>
      <span className="flex-1 min-w-0 text-sm text-white truncate">{name}</span>
      <span className="shrink-0 rounded-full px-2 py-0.5 text-xs bg-gray-700 text-gray-300">
        {typeBadge}
      </span>
      <span className={`shrink-0 rounded-full px-2 py-0.5 text-xs ${PAYMENT_BADGE[entry.payment_status]}`}>
        {PAYMENT_LABEL[entry.payment_status]}
      </span>
      {entry.payment_status !== 'verified_paid' && (
        <button
          onClick={() => onVerify(entry.id)}
          disabled={verifying}
          title="Verify payment"
          className="shrink-0 rounded-lg bg-green-800 px-2 py-1 text-xs font-medium text-green-200 hover:bg-green-700 disabled:opacity-50"
        >
          Verify ✓
        </button>
      )}
      <button
        onClick={() => onRemove(entry.id)}
        disabled={removing}
        title="Remove player"
        className="shrink-0 text-gray-600 hover:text-red-400 disabled:opacity-50 transition-colors text-sm px-1"
      >
        {removing ? '…' : '✕'}
      </button>
    </div>
  )
}
