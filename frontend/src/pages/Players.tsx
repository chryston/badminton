import { useState, useEffect } from 'react'
import { api } from '../lib/api'
import type { Player, SkillLevel } from '../types'

const SKILL_BADGE: Record<SkillLevel, string> = {
  HB: 'bg-purple-900/60 text-purple-300',
  LI: 'bg-blue-900/60 text-blue-300',
  MB: 'bg-orange-900/60 text-orange-300',
}

type FilterTab = 'all' | 'members' | 'public'

interface PlayerFormData {
  name: string
  skill_level: SkillLevel
  phone: string
  is_internal: boolean
  notes: string
}

const defaultForm: PlayerFormData = {
  name: '',
  skill_level: 'HB',
  phone: '',
  is_internal: false,
  notes: '',
}

function SkeletonCard() {
  return (
    <div className="rounded-xl bg-gray-800 p-4 animate-pulse border border-gray-700">
      <div className="flex justify-between">
        <div className="space-y-2 flex-1">
          <div className="h-4 w-36 bg-gray-700 rounded" />
          <div className="h-3 w-24 bg-gray-700 rounded" />
          <div className="h-3 w-48 bg-gray-700 rounded" />
        </div>
        <div className="h-6 w-10 bg-gray-700 rounded-full" />
      </div>
    </div>
  )
}

interface PlayerModalProps {
  player: Player | null
  onClose: () => void
  onSaved: () => void
}

function PlayerModal({ player, onClose, onSaved }: PlayerModalProps) {
  const [form, setForm] = useState<PlayerFormData>(
    player
      ? {
          name: player.name,
          skill_level: player.skill_level,
          phone: player.phone ?? '',
          is_internal: player.is_internal,
          notes: player.notes ?? '',
        }
      : defaultForm,
  )
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setSaving(true)
    setError(null)
    try {
      const payload = {
        name: form.name.trim(),
        skill_level: form.skill_level,
        phone: form.phone.trim() || null,
        is_internal: form.is_internal,
        notes: form.notes.trim() || null,
      }
      if (player) {
        await api.patch(`/api/v1/players/${player.id}`, payload)
      } else {
        await api.post('/api/v1/players', payload)
      }
      onSaved()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save player')
    } finally {
      setSaving(false)
    }
  }

  useEffect(() => {
    const handleEsc = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', handleEsc);
    return () => document.removeEventListener('keydown', handleEsc);
  }, [onClose]);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 px-4" onClick={onClose}>
      <div className="w-full max-w-md rounded-xl bg-gray-900 border border-gray-700 p-6" onClick={(e) => e.stopPropagation()}>
        <h2 className="text-lg font-bold text-white mb-4">
          {player ? 'Edit Player' : 'Add Player'}
        </h2>

        {error && (
          <p className="rounded-lg bg-red-900/50 border border-red-700 px-3 py-2 text-sm text-red-300 mb-4">
            {error}
          </p>
        )}

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-300 mb-1">
              Name <span className="text-red-400">*</span>
            </label>
            <input
              required
              type="text"
              value={form.name}
              onChange={e => setForm(f => ({ ...f, name: e.target.value }))}
              className="w-full rounded-lg bg-gray-800 border border-gray-600 px-3 py-2 text-sm text-white placeholder-gray-500 focus:outline-none focus:border-brand-500"
              placeholder="Player name"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-300 mb-1">Skill Level</label>
            <select
              value={form.skill_level}
              onChange={e => setForm(f => ({ ...f, skill_level: e.target.value as SkillLevel }))}
              className="w-full rounded-lg bg-gray-800 border border-gray-600 px-3 py-2 text-sm text-white focus:outline-none focus:border-brand-500"
            >
              <option value="HB">HB — High Beginner</option>
              <option value="LI">LI — Low Intermediate</option>
              <option value="MB">MB — Mid Beginner</option>
            </select>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-300 mb-1">Phone</label>
            <input
              type="tel"
              value={form.phone}
              onChange={e => setForm(f => ({ ...f, phone: e.target.value }))}
              className="w-full rounded-lg bg-gray-800 border border-gray-600 px-3 py-2 text-sm text-white placeholder-gray-500 focus:outline-none focus:border-brand-500"
              placeholder="+65 9xxx xxxx"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-300 mb-1">Notes</label>
            <textarea
              value={form.notes}
              onChange={e => setForm(f => ({ ...f, notes: e.target.value }))}
              rows={3}
              className="w-full rounded-lg bg-gray-800 border border-gray-600 px-3 py-2 text-sm text-white placeholder-gray-500 focus:outline-none focus:border-brand-500 resize-none"
              placeholder="Optional notes"
            />
          </div>

          <label className="flex items-center gap-3 cursor-pointer">
            <input
              type="checkbox"
              checked={form.is_internal}
              onChange={e => setForm(f => ({ ...f, is_internal: e.target.checked }))}
              className="w-4 h-4 rounded accent-brand-500"
            />
            <span className="text-sm text-gray-300">Internal member</span>
          </label>

          <div className="flex gap-3 pt-2">
            <button
              type="button"
              onClick={onClose}
              className="flex-1 rounded-lg border border-gray-600 px-4 py-2 text-sm text-gray-300 hover:bg-gray-800 transition-colors"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={saving}
              className="flex-1 rounded-lg bg-brand-600 px-4 py-2 text-sm font-semibold text-white hover:bg-brand-700 transition-colors disabled:opacity-50"
            >
              {saving ? 'Saving…' : 'Save'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

export function Players() {
  const [players, setPlayers] = useState<Player[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [filter, setFilter] = useState<FilterTab>('all')
  const [modalPlayer, setModalPlayer] = useState<Player | null | 'new'>(null)

  function loadPlayers(signal?: AbortSignal) {
    setLoading(true)
    setError(null)
    api
      .get<Player[]>('/api/v1/players', signal)
      .then(list => {
        list.sort((a, b) => a.name.localeCompare(b.name))
        setPlayers(list)
      })
      .catch(err => {
        if (err instanceof Error && err.name === 'AbortError') return
        setError(err instanceof Error ? err.message : 'Failed to load players')
      })
      .finally(() => setLoading(false))
  }

  useEffect(() => {
    const controller = new AbortController()
    loadPlayers(controller.signal)
    return () => controller.abort()
  }, [])

  const filtered = players.filter(p => {
    if (filter === 'members') return p.is_internal
    if (filter === 'public') return !p.is_internal
    return true
  })

  const filterTabs: { id: FilterTab; label: string }[] = [
    { id: 'all', label: 'All' },
    { id: 'members', label: 'Members' },
    { id: 'public', label: 'Public' },
  ]

  return (
    <div className="p-4">
      <div className="flex items-center justify-between mb-4">
        <h1 className="text-xl font-bold text-white">Players</h1>
        <button
          onClick={() => setModalPlayer('new')}
          className="rounded-lg bg-brand-600 px-3 py-1.5 text-sm font-semibold text-white hover:bg-brand-700 transition-colors"
        >
          + Add Player
        </button>
      </div>

      {/* Filter tabs */}
      <div className="flex gap-1 mb-4 bg-gray-800 rounded-lg p-1">
        {filterTabs.map(tab => (
          <button
            key={tab.id}
            onClick={() => setFilter(tab.id)}
            className={`flex-1 rounded-md py-1.5 text-sm font-medium transition-colors ${
              filter === tab.id
                ? 'bg-gray-700 text-white'
                : 'text-gray-400 hover:text-gray-200'
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {error && (
        <p className="rounded-lg bg-red-900/50 border border-red-700 px-4 py-3 text-sm text-red-300 mb-4">
          {error}
        </p>
      )}

      {loading ? (
        <div className="space-y-3">
          {Array.from({ length: 5 }).map((_, i) => <SkeletonCard key={i} />)}
        </div>
      ) : filtered.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-16 text-gray-500">
          <span className="text-4xl mb-3">👥</span>
          <p className="text-sm">No players found</p>
        </div>
      ) : (
        <div className="space-y-3">
          {filtered.map(player => (
            <div
              key={player.id}
              className="rounded-xl bg-gray-800 p-4 border border-gray-700"
            >
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="font-semibold text-white">{player.name}</span>
                    <span
                      className={`rounded-full px-2 py-0.5 text-xs font-medium ${SKILL_BADGE[player.skill_level]}`}
                    >
                      {player.skill_level}
                    </span>
                    {player.is_internal && (
                      <span className="rounded-full bg-teal-900/60 text-teal-300 px-2 py-0.5 text-xs font-medium">
                        Internal
                      </span>
                    )}
                  </div>
                  {player.phone && (
                    <p className="text-sm text-gray-400 mt-1">{player.phone}</p>
                  )}
                  {player.notes && (
                    <p className="text-xs text-gray-500 mt-1 truncate">{player.notes}</p>
                  )}
                </div>
                <button
                  onClick={() => setModalPlayer(player)}
                  className="shrink-0 rounded-lg border border-gray-600 px-3 py-1.5 text-xs text-gray-300 hover:bg-gray-700 transition-colors"
                >
                  Edit
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {modalPlayer !== null && (
        <PlayerModal
          player={modalPlayer === 'new' ? null : modalPlayer}
          onClose={() => setModalPlayer(null)}
          onSaved={() => {
            setModalPlayer(null)
            loadPlayers()
          }}
        />
      )}
    </div>
  )
}
