import { useEffect, useState } from 'react'
import { policiesApi } from '../services/api'
import type { PolicyRule } from '../types'
import { Plus, Trash2, ToggleLeft, ToggleRight, Settings, ShieldCheck } from 'lucide-react'
import { useAuth } from '../context/AuthContext'

const CONDITION_TYPES = [
  { value: 'risk_score_above', label: 'Risk Score Above' },
  { value: 'flag_contains', label: 'Flag Contains' },
  { value: 'department_is', label: 'Department Is' },
  { value: 'always', label: 'Always' },
]

const ACTIONS = [
  { value: 'ALLOW', label: 'Allow', color: 'text-green-400' },
  { value: 'WARN', label: 'Warn', color: 'text-yellow-400' },
  { value: 'REDACT', label: 'Redact', color: 'text-blue-400' },
  { value: 'BLOCK', label: 'Block', color: 'text-red-400' },
]

const FLAGS = ['PROMPT_INJECTION', 'PII_DETECTED', 'SENSITIVE_DATA', 'KNOWLEDGE_SHIELD', 'TOXICITY', 'EXCESSIVE_LENGTH']

export default function SettingsPage() {
  const { user } = useAuth()
  const [policies, setPolicies] = useState<PolicyRule[]>([])
  const [loading, setLoading] = useState(true)
  const [showForm, setShowForm] = useState(false)
  const [error, setError] = useState('')
  const [form, setForm] = useState({
    name: '', description: '', condition_type: 'risk_score_above',
    condition_value: '80', action: 'BLOCK', priority: 50, is_active: true,
  })
  const [submitting, setSubmitting] = useState(false)

  const isAdmin = user?.role === 'admin'

  const refresh = async () => {
    setLoading(true)
    const res = await policiesApi.list()
    setPolicies(res.data)
    setLoading(false)
  }

  useEffect(() => { refresh() }, [])

  const createPolicy = async (e: React.FormEvent) => {
    e.preventDefault()
    setSubmitting(true)
    try {
      await policiesApi.create(form)
      setShowForm(false)
      setForm({ name: '', description: '', condition_type: 'risk_score_above', condition_value: '80', action: 'BLOCK', priority: 50, is_active: true })
      await refresh()
    } catch {
      setError('Failed to create policy.')
    } finally {
      setSubmitting(false)
    }
  }

  const toggle = async (id: string) => {
    try { await policiesApi.toggle(id); await refresh() } catch { setError('Failed to toggle.') }
  }

  const remove = async (id: string) => {
    if (!confirm('Delete this policy rule?')) return
    try { await policiesApi.delete(id); await refresh() } catch { setError('Failed to delete.') }
  }

  const ACTION_COLOR: Record<string, string> = {
    BLOCK: 'text-red-400', WARN: 'text-yellow-400',
    REDACT: 'text-blue-400', ALLOW: 'text-green-400',
  }

  return (
    <div className="space-y-6 animate-fade-in">
      {/* Policy Engine */}
      <div className="card">
        <div className="flex items-center justify-between mb-4">
          <div>
            <h2 className="section-title mb-1">Policy Enforcement Rules</h2>
            <p className="text-xs text-gray-500">Rules evaluated in priority order. Strictest matching action wins.</p>
          </div>
          {isAdmin && (
            <button onClick={() => setShowForm(!showForm)} className="btn-primary flex items-center gap-2 text-sm">
              <Plus size={14} /> New Rule
            </button>
          )}
        </div>

        {error && <div className="bg-red-500/10 border border-red-500/30 text-red-400 rounded-lg px-3 py-2 text-sm mb-4">{error}</div>}

        {/* Create form */}
        {showForm && isAdmin && (
          <form onSubmit={createPolicy} className="mb-6 p-4 bg-surface-2 rounded-xl border border-surface-3 space-y-3">
            <h3 className="text-sm font-medium text-white">Create Policy Rule</h3>
            <div className="grid grid-cols-2 gap-3">
              <div className="col-span-2">
                <label className="block text-xs text-gray-400 mb-1">Rule Name</label>
                <input className="input" placeholder="e.g. Block Critical Risk" value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))} required />
              </div>
              <div>
                <label className="block text-xs text-gray-400 mb-1">Condition</label>
                <select className="input" value={form.condition_type} onChange={e => setForm(f => ({ ...f, condition_type: e.target.value }))}>
                  {CONDITION_TYPES.map(c => <option key={c.value} value={c.value}>{c.label}</option>)}
                </select>
              </div>
              <div>
                <label className="block text-xs text-gray-400 mb-1">Value</label>
                {form.condition_type === 'flag_contains' ? (
                  <select className="input" value={form.condition_value} onChange={e => setForm(f => ({ ...f, condition_value: e.target.value }))}>
                    {FLAGS.map(f => <option key={f} value={f}>{f}</option>)}
                  </select>
                ) : (
                  <input className="input" placeholder={form.condition_type === 'risk_score_above' ? '80' : 'value'} value={form.condition_value} onChange={e => setForm(f => ({ ...f, condition_value: e.target.value }))} />
                )}
              </div>
              <div>
                <label className="block text-xs text-gray-400 mb-1">Action</label>
                <select className="input" value={form.action} onChange={e => setForm(f => ({ ...f, action: e.target.value }))}>
                  {ACTIONS.map(a => <option key={a.value} value={a.value}>{a.label}</option>)}
                </select>
              </div>
              <div>
                <label className="block text-xs text-gray-400 mb-1">Priority (higher = evaluated first)</label>
                <input type="number" className="input" min={0} max={200} value={form.priority} onChange={e => setForm(f => ({ ...f, priority: +e.target.value }))} />
              </div>
            </div>
            <div className="flex gap-2">
              <button type="submit" disabled={submitting} className="btn-primary text-sm">{submitting ? 'Creating...' : 'Create Rule'}</button>
              <button type="button" onClick={() => setShowForm(false)} className="btn-ghost text-sm">Cancel</button>
            </div>
          </form>
        )}

        {loading && <div className="flex justify-center py-8"><div className="w-5 h-5 border-2 border-brand border-t-transparent rounded-full animate-spin" /></div>}

        <div className="space-y-2">
          {policies.map(p => (
            <div key={p.id} className={`flex items-center gap-3 p-3 rounded-xl border transition-opacity ${p.is_active ? 'bg-surface-2 border-surface-3' : 'bg-surface-1 border-surface-3 opacity-50'}`}>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 mb-0.5">
                  <p className="text-sm font-medium text-white">{p.name}</p>
                  <span className="text-xs text-gray-600 bg-surface-3 px-1.5 py-0.5 rounded font-mono">P{p.priority}</span>
                </div>
                <p className="text-xs text-gray-500 font-mono">
                  IF <span className="text-gray-300">{p.condition_type.replace(/_/g, ' ')}</span> = <span className="text-blue-400">{p.condition_value}</span>
                  {' '}→ <span className={`font-bold ${ACTION_COLOR[p.action]}`}>{p.action}</span>
                </p>
                {p.description && <p className="text-xs text-gray-600 mt-0.5">{p.description}</p>}
              </div>
              {isAdmin && (
                <div className="flex items-center gap-1">
                  <button onClick={() => toggle(p.id)} title={p.is_active ? 'Disable' : 'Enable'} className="btn-ghost p-1.5">
                    {p.is_active
                      ? <ToggleRight size={18} className="text-green-400" />
                      : <ToggleLeft size={18} className="text-gray-500" />}
                  </button>
                  <button onClick={() => remove(p.id)} className="btn-ghost p-1.5 text-gray-600 hover:text-red-400">
                    <Trash2 size={14} />
                  </button>
                </div>
              )}
            </div>
          ))}
          {!loading && policies.length === 0 && (
            <p className="text-gray-500 text-sm text-center py-8">No policy rules configured.</p>
          )}
        </div>
      </div>

      {/* Platform info */}
      <div className="card">
        <h2 className="section-title mb-4">Platform Configuration</h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 text-sm">
          {[
            { label: 'Risk Block Threshold', value: '> 80', desc: 'Score above which BLOCK is enforced' },
            { label: 'Risk Warn Threshold', value: '> 50', desc: 'Score above which WARN is triggered' },
            { label: 'Knowledge Shield Threshold', value: '75%', desc: 'Cosine similarity trigger level' },
            { label: 'Embedding Model', value: 'all-MiniLM-L6-v2', desc: 'SentenceTransformers model' },
            { label: 'LLM Provider', value: 'Groq', desc: 'llama-3.3-70b-versatile (default)' },
            { label: 'PII Types Monitored', value: 'Email, Phone, SSN, CC, IP', desc: 'Regex-based detection' },
          ].map(item => (
            <div key={item.label} className="p-3 bg-surface-2 rounded-lg border border-surface-3">
              <p className="text-gray-400 text-xs mb-1">{item.label}</p>
              <p className="text-white font-mono font-medium">{item.value}</p>
              <p className="text-gray-600 text-xs mt-0.5">{item.desc}</p>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
