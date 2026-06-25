import { useEffect, useState } from 'react'
import { knowledgeShieldApi } from '../services/api'
import type { ConfidentialDoc } from '../types'
import { BookLock, Plus, Trash2, CheckCircle, XCircle, RefreshCw, ChevronDown } from 'lucide-react'
import { formatDistanceToNow } from 'date-fns'

interface ShieldStatus {
  encoder_available: boolean
  index_ready: boolean
  initialized: boolean
}

const CATEGORIES = ['general', 'pricing', 'hr', 'technical', 'legal', 'financial', 'mergers']

export default function KnowledgeShieldPage() {
  const [docs, setDocs] = useState<ConfidentialDoc[]>([])
  const [status, setStatus] = useState<ShieldStatus | null>(null)
  const [loading, setLoading] = useState(true)
  const [showForm, setShowForm] = useState(false)
  const [form, setForm] = useState({ name: '', content: '', category: 'general' })
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')

  const refresh = async () => {
    setLoading(true)
    try {
      const [docsRes, statusRes] = await Promise.all([
        knowledgeShieldApi.listDocs(),
        knowledgeShieldApi.status(),
      ])
      setDocs(docsRes.data)
      setStatus(statusRes.data)
    } catch {
      setError('Failed to load.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { refresh() }, [])

  const addDoc = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!form.name.trim() || !form.content.trim()) return
    setSubmitting(true)
    try {
      await knowledgeShieldApi.addDoc(form)
      setForm({ name: '', content: '', category: 'general' })
      setShowForm(false)
      await refresh()
    } catch {
      setError('Failed to add document.')
    } finally {
      setSubmitting(false)
    }
  }

  const deleteDoc = async (id: string) => {
    if (!confirm('Remove this document from the Knowledge Shield?')) return
    try {
      await knowledgeShieldApi.deleteDoc(id)
      await refresh()
    } catch {
      setError('Failed to delete.')
    }
  }

  const CATEGORY_COLORS: Record<string, string> = {
    pricing: 'bg-green-500/15 text-green-400',
    hr: 'bg-blue-500/15 text-blue-400',
    technical: 'bg-purple-500/15 text-purple-400',
    legal: 'bg-yellow-500/15 text-yellow-400',
    financial: 'bg-orange-500/15 text-orange-400',
    mergers: 'bg-red-500/15 text-red-400',
    general: 'bg-gray-500/15 text-gray-400',
  }

  return (
    <div className="space-y-5 animate-fade-in">
      {/* Status */}
      <div className="card">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="section-title mb-1">Shield Status</h2>
            <p className="text-xs text-gray-500">Semantic IP leakage detection powered by SentenceTransformers + FAISS</p>
          </div>
          <button onClick={refresh} className="btn-ghost p-2"><RefreshCw size={14} className={loading ? 'animate-spin' : ''} /></button>
        </div>
        {status && (
          <div className="flex flex-wrap gap-4 mt-4">
            {[
              { label: 'Encoder (SentenceTransformers)', ok: status.encoder_available },
              { label: 'Vector Index (FAISS)', ok: status.index_ready },
              { label: 'Shield Initialized', ok: status.initialized },
            ].map(({ label, ok }) => (
              <div key={label} className="flex items-center gap-2">
                {ok ? <CheckCircle size={14} className="text-green-400" /> : <XCircle size={14} className="text-red-400" />}
                <span className="text-sm text-gray-300">{label}</span>
              </div>
            ))}
            <div className="flex items-center gap-2">
              <BookLock size={14} className="text-purple-400" />
              <span className="text-sm text-gray-300">{docs.length} protected documents</span>
            </div>
          </div>
        )}
        {!status?.encoder_available && (
          <div className="mt-3 bg-yellow-500/10 border border-yellow-500/30 rounded-lg px-3 py-2 text-xs text-yellow-400">
            SentenceTransformers not available. Install with: <code className="font-mono">pip install sentence-transformers faiss-cpu</code>. The shield will be inactive until the encoder loads.
          </div>
        )}
      </div>

      {error && <div className="bg-red-500/10 border border-red-500/30 text-red-400 rounded-xl px-4 py-3 text-sm">{error}</div>}

      {/* Documents */}
      <div className="card">
        <div className="flex items-center justify-between mb-4">
          <h2 className="section-title">Protected Documents ({docs.length})</h2>
          <button onClick={() => setShowForm(!showForm)} className="btn-primary flex items-center gap-2 text-sm">
            <Plus size={14} />Add Document
          </button>
        </div>

        {/* Add form */}
        {showForm && (
          <form onSubmit={addDoc} className="mb-6 p-4 bg-surface-2 rounded-xl border border-surface-3 space-y-3">
            <h3 className="text-sm font-medium text-white">Add Confidential Document</h3>
            <input
              className="input"
              placeholder="Document name (e.g. Q4 Pricing Strategy)"
              value={form.name}
              onChange={e => setForm(f => ({ ...f, name: e.target.value }))}
              required
            />
            <select className="input" value={form.category} onChange={e => setForm(f => ({ ...f, category: e.target.value }))}>
              {CATEGORIES.map(c => <option key={c} value={c}>{c}</option>)}
            </select>
            <textarea
              className="input min-h-[120px] font-mono text-xs"
              placeholder="Paste the confidential document content here. It will be converted to embeddings for semantic matching."
              value={form.content}
              onChange={e => setForm(f => ({ ...f, content: e.target.value }))}
              required
            />
            <div className="flex gap-2">
              <button type="submit" disabled={submitting} className="btn-primary text-sm">
                {submitting ? 'Indexing...' : 'Add & Index'}
              </button>
              <button type="button" onClick={() => setShowForm(false)} className="btn-ghost text-sm">Cancel</button>
            </div>
          </form>
        )}

        {loading && <div className="flex justify-center py-8"><div className="w-5 h-5 border-2 border-brand border-t-transparent rounded-full animate-spin" /></div>}

        {!loading && docs.length === 0 && (
          <div className="text-center py-12">
            <BookLock size={32} className="mx-auto text-gray-600 mb-3" />
            <p className="text-gray-500 text-sm">No protected documents yet.</p>
            <p className="text-gray-600 text-xs mt-1">Add confidential documents to enable semantic IP leakage detection.</p>
          </div>
        )}

        <div className="space-y-2">
          {docs.map(doc => (
            <div key={doc.id} className="flex items-center gap-3 p-3 bg-surface-2 rounded-lg border border-surface-3">
              <div className="flex-shrink-0 w-9 h-9 rounded-lg bg-purple-500/15 flex items-center justify-center">
                <BookLock size={16} className="text-purple-400" />
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium text-white truncate">{doc.name}</p>
                <p className="text-xs text-gray-500 mt-0.5">
                  Added {formatDistanceToNow(new Date(doc.created_at), { addSuffix: true })}
                </p>
              </div>
              <span className={`badge ${CATEGORY_COLORS[doc.category] ?? CATEGORY_COLORS.general}`}>
                {doc.category}
              </span>
              <button
                onClick={() => deleteDoc(doc.id)}
                className="text-gray-600 hover:text-red-400 transition-colors p-1"
              >
                <Trash2 size={14} />
              </button>
            </div>
          ))}
        </div>
      </div>

      {/* How it works */}
      <div className="card border border-purple-500/20 bg-purple-500/5">
        <h2 className="section-title mb-3">How Knowledge Shield Works</h2>
        <ol className="space-y-2 text-sm text-gray-400">
          {[
            'Confidential documents are encoded into dense vector embeddings using SentenceTransformers.',
            'Embeddings are stored in a FAISS vector index for fast cosine similarity search.',
            'Every incoming user prompt is also encoded into an embedding.',
            'The prompt embedding is searched against the document index.',
            'If similarity exceeds the threshold (default: 75%), the prompt is flagged as KNOWLEDGE_SHIELD.',
            'The policy engine can then block or warn based on the flag.',
          ].map((step, i) => (
            <li key={i} className="flex items-start gap-2">
              <span className="flex-shrink-0 w-5 h-5 rounded-full bg-purple-500/20 text-purple-400 text-xs flex items-center justify-center font-bold">{i + 1}</span>
              {step}
            </li>
          ))}
        </ol>
      </div>
    </div>
  )
}
