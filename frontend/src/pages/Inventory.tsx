import { useState, useEffect } from 'react'
import { api } from '../lib/api'
import type { ShuttleBatch } from '../types'

function SkeletonCard() {
  return (
    <div className="rounded-xl bg-gray-800 p-4 animate-pulse border border-gray-700">
      <div className="flex justify-between">
        <div className="space-y-2 flex-1">
          <div className="h-4 w-40 bg-gray-700 rounded" />
          <div className="h-3 w-28 bg-gray-700 rounded" />
          <div className="h-3 w-36 bg-gray-700 rounded" />
        </div>
        <div className="h-8 w-12 bg-gray-700 rounded" />
      </div>
    </div>
  )
}

interface BatchFormData {
  batch_name: string
  brand: string
  cost_per_tube: string
  shuttles_per_tube: string
  remaining_count: string
  owner_label: string
  is_active: boolean
}

const defaultForm: BatchFormData = {
  batch_name: '',
  brand: '',
  cost_per_tube: '',
  shuttles_per_tube: '12',
  remaining_count: '',
  owner_label: '',
  is_active: true,
}

interface BatchModalProps {
  batch: ShuttleBatch | null
  onClose: () => void
  onSaved: () => void
}

function BatchModal({ batch, onClose, onSaved }: BatchModalProps) {
  const [form, setForm] = useState<BatchFormData>(
    batch
      ? {
          batch_name: batch.batch_name,
          brand: batch.brand,
          cost_per_tube: String(batch.cost_per_tube),
          shuttles_per_tube: String(batch.shuttles_per_tube),
          remaining_count: String(batch.remaining_count),
          owner_label: batch.owner_label ?? '',
          is_active: batch.is_active,
        }
      : defaultForm,
  )
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const costPerShuttle =
    form.cost_per_tube && form.shuttles_per_tube
      ? (parseFloat(form.cost_per_tube) / parseFloat(form.shuttles_per_tube)).toFixed(2)
      : '—'

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setSaving(true)
    setError(null)
    try {
      const payload = {
        batch_name: form.batch_name.trim(),
        brand: form.brand.trim(),
        cost_per_tube: parseFloat(form.cost_per_tube),
        shuttles_per_tube: parseInt(form.shuttles_per_tube, 10),
        remaining_count: parseInt(form.remaining_count, 10),
        owner_label: form.owner_label.trim() || null,
        is_active: form.is_active,
      }
      if (batch) {
        await api.patch(`/api/v1/inventory/${batch.id}`, payload)
      } else {
        await api.post('/api/v1/inventory', payload)
      }
      onSaved()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save batch')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 px-4">
      <div className="w-full max-w-md rounded-xl bg-gray-900 border border-gray-700 p-6 max-h-[90vh] overflow-y-auto">
        <h2 className="text-lg font-bold text-white mb-4">
          {batch ? 'Edit Batch' : 'Add Batch'}
        </h2>

        {error && (
          <p className="rounded-lg bg-red-900/50 border border-red-700 px-3 py-2 text-sm text-red-300 mb-4">
            {error}
          </p>
        )}

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-300 mb-1">
              Batch Name <span className="text-red-400">*</span>
            </label>
            <input
              required
              type="text"
              value={form.batch_name}
              onChange={e => setForm(f => ({ ...f, batch_name: e.target.value }))}
              className="w-full rounded-lg bg-gray-800 border border-gray-600 px-3 py-2 text-sm text-white placeholder-gray-500 focus:outline-none focus:border-brand-500"
              placeholder="e.g. Batch #12"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-300 mb-1">
              Brand <span className="text-red-400">*</span>
            </label>
            <input
              required
              type="text"
              value={form.brand}
              onChange={e => setForm(f => ({ ...f, brand: e.target.value }))}
              className="w-full rounded-lg bg-gray-800 border border-gray-600 px-3 py-2 text-sm text-white placeholder-gray-500 focus:outline-none focus:border-brand-500"
              placeholder="e.g. RSL, Yonex"
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-sm font-medium text-gray-300 mb-1">Cost / Tube ($)</label>
              <input
                type="number"
                min="0"
                step="0.01"
                value={form.cost_per_tube}
                onChange={e => setForm(f => ({ ...f, cost_per_tube: e.target.value }))}
                className="w-full rounded-lg bg-gray-800 border border-gray-600 px-3 py-2 text-sm text-white placeholder-gray-500 focus:outline-none focus:border-brand-500"
                placeholder="0.00"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-300 mb-1">Shuttles / Tube</label>
              <input
                type="number"
                min="1"
                value={form.shuttles_per_tube}
                onChange={e => setForm(f => ({ ...f, shuttles_per_tube: e.target.value }))}
                className="w-full rounded-lg bg-gray-800 border border-gray-600 px-3 py-2 text-sm text-white placeholder-gray-500 focus:outline-none focus:border-brand-500"
                placeholder="12"
              />
            </div>
          </div>

          <div className="rounded-lg bg-gray-800/50 border border-gray-700 px-3 py-2 text-sm text-gray-400">
            Cost / shuttle: <span className="text-white font-medium">${costPerShuttle}</span>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-300 mb-1">Remaining Count</label>
            <input
              type="number"
              min="0"
              value={form.remaining_count}
              onChange={e => setForm(f => ({ ...f, remaining_count: e.target.value }))}
              className="w-full rounded-lg bg-gray-800 border border-gray-600 px-3 py-2 text-sm text-white placeholder-gray-500 focus:outline-none focus:border-brand-500"
              placeholder="0"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-300 mb-1">Owner Label</label>
            <input
              type="text"
              value={form.owner_label}
              onChange={e => setForm(f => ({ ...f, owner_label: e.target.value }))}
              className="w-full rounded-lg bg-gray-800 border border-gray-600 px-3 py-2 text-sm text-white placeholder-gray-500 focus:outline-none focus:border-brand-500"
              placeholder="Optional"
            />
          </div>

          <label className="flex items-center gap-3 cursor-pointer">
            <input
              type="checkbox"
              checked={form.is_active}
              onChange={e => setForm(f => ({ ...f, is_active: e.target.checked }))}
              className="w-4 h-4 rounded accent-brand-500"
            />
            <span className="text-sm text-gray-300">Active batch</span>
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

interface AdjustCountProps {
  batch: ShuttleBatch
  onSaved: () => void
}

function AdjustCount({ batch, onSaved }: AdjustCountProps) {
  const [open, setOpen] = useState(false)
  const [value, setValue] = useState(String(batch.remaining_count))
  const [saving, setSaving] = useState(false)

  if (!open) {
    return (
      <button
        onClick={() => setOpen(true)}
        className="rounded-lg border border-gray-600 px-2 py-1 text-xs text-gray-400 hover:bg-gray-700 transition-colors"
      >
        Adjust
      </button>
    )
  }

  async function handleSave() {
    setSaving(true)
    try {
      await api.patch(`/api/v1/inventory/${batch.id}`, {
        remaining_count: parseInt(value, 10),
      })
      setOpen(false)
      onSaved()
    } catch {
      // silently swallow; user can retry
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="flex items-center gap-1 mt-2">
      <input
        type="number"
        min="0"
        value={value}
        onChange={e => setValue(e.target.value)}
        className="w-20 rounded-lg bg-gray-700 border border-gray-600 px-2 py-1 text-sm text-white focus:outline-none"
      />
      <button
        onClick={handleSave}
        disabled={saving}
        className="rounded-lg bg-brand-600 px-2 py-1 text-xs text-white hover:bg-brand-700 transition-colors disabled:opacity-50"
      >
        {saving ? '…' : 'Set'}
      </button>
      <button
        onClick={() => setOpen(false)}
        className="rounded-lg border border-gray-600 px-2 py-1 text-xs text-gray-400 hover:bg-gray-700 transition-colors"
      >
        ✕
      </button>
    </div>
  )
}

export function Inventory() {
  const [batches, setBatches] = useState<ShuttleBatch[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [modalBatch, setModalBatch] = useState<ShuttleBatch | null | 'new'>(null)

  function loadBatches(signal?: AbortSignal) {
    setLoading(true)
    setError(null)
    api
      .get<ShuttleBatch[]>('/api/v1/inventory', signal)
      .then(list => {
        // Active batches first, then sorted by name
        list.sort((a, b) => {
          if (a.is_active !== b.is_active) return a.is_active ? -1 : 1
          return a.batch_name.localeCompare(b.batch_name)
        })
        setBatches(list)
      })
      .catch(err => {
        if (err instanceof Error && err.name === 'AbortError') return
        setError(err instanceof Error ? err.message : 'Failed to load inventory')
      })
      .finally(() => setLoading(false))
  }

  useEffect(() => {
    const controller = new AbortController()
    loadBatches(controller.signal)
    return () => controller.abort()
  }, [])

  async function toggleActive(batch: ShuttleBatch) {
    try {
      await api.patch(`/api/v1/inventory/${batch.id}`, { is_active: !batch.is_active })
      loadBatches()
    } catch {
      // silently swallow; state reverts on next load
    }
  }

  return (
    <div className="p-4">
      <div className="flex items-center justify-between mb-4">
        <h1 className="text-xl font-bold text-white">Inventory</h1>
        <button
          onClick={() => setModalBatch('new')}
          className="rounded-lg bg-brand-600 px-3 py-1.5 text-sm font-semibold text-white hover:bg-brand-700 transition-colors"
        >
          + Add Batch
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
      ) : batches.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-16 text-gray-500">
          <span className="text-4xl mb-3">🏸</span>
          <p className="text-sm">No shuttle batches yet</p>
        </div>
      ) : (
        <div className="space-y-3">
          {batches.map(batch => (
            <div
              key={batch.id}
              className={`rounded-xl p-4 border ${
                batch.is_active
                  ? 'bg-teal-950/40 border-teal-700/50'
                  : 'bg-gray-800 border-gray-700'
              }`}
            >
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="font-semibold text-white">{batch.batch_name}</span>
                    <span className="text-xs text-gray-400">{batch.brand}</span>
                    {batch.is_active && (
                      <span className="rounded-full bg-teal-900/60 text-teal-300 px-2 py-0.5 text-xs font-medium">
                        Active
                      </span>
                    )}
                  </div>

                  <div className="flex gap-4 mt-1 text-xs text-gray-400">
                    <span>${batch.cost_per_tube.toFixed(2)}/tube</span>
                    <span>${batch.cost_per_shuttle.toFixed(2)}/shuttle</span>
                  </div>

                  <div className="flex items-center gap-2 mt-1">
                    <span
                      className={`text-sm font-medium ${
                        batch.remaining_count < 20 ? 'text-orange-400' : 'text-white'
                      }`}
                    >
                      {batch.remaining_count} remaining
                    </span>
                    {batch.remaining_count < 20 && (
                      <span className="text-xs text-orange-400">⚠ Low stock</span>
                    )}
                  </div>

                  {batch.owner_label && (
                    <p className="text-xs text-gray-500 mt-0.5">Owner: {batch.owner_label}</p>
                  )}

                  <AdjustCount batch={batch} onSaved={() => loadBatches()} />
                </div>

                <div className="flex flex-col items-end gap-2 shrink-0">
                  <button
                    onClick={() => setModalBatch(batch)}
                    className="rounded-lg border border-gray-600 px-3 py-1.5 text-xs text-gray-300 hover:bg-gray-700 transition-colors"
                  >
                    Edit
                  </button>
                  <button
                    onClick={() => toggleActive(batch)}
                    className={`rounded-lg px-3 py-1.5 text-xs font-medium transition-colors ${
                      batch.is_active
                        ? 'bg-teal-900/60 text-teal-300 hover:bg-teal-800/60'
                        : 'border border-gray-600 text-gray-400 hover:bg-gray-700'
                    }`}
                  >
                    {batch.is_active ? 'Active' : 'Inactive'}
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {modalBatch !== null && (
        <BatchModal
          batch={modalBatch === 'new' ? null : modalBatch}
          onClose={() => setModalBatch(null)}
          onSaved={() => {
            setModalBatch(null)
            loadBatches()
          }}
        />
      )}
    </div>
  )
}
