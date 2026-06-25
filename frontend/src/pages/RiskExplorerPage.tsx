import { useEffect, useState } from 'react'
import { promptsApi } from '../services/api'
import type { PromptRecord, PaginatedResponse } from '../types'
import { RiskBadge, ActionBadge, RiskScore, FlagChip } from '../components/RiskBadge'
import { Search, ChevronDown, ChevronUp, Filter } from 'lucide-react'
import { formatDistanceToNow } from 'date-fns'

export default function RiskExplorerPage() {
  const [data, setData] = useState<PaginatedResponse<PromptRecord> | null>(null)
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState('')
  const [riskFilter, setRiskFilter] = useState('')
  const [blockedFilter, setBlockedFilter] = useState<boolean | undefined>(undefined)
  const [page, setPage] = useState(1)
  const [expanded, setExpanded] = useState<string | null>(null)

  const fetch = async () => {
    setLoading(true)
    try {
      const res = await promptsApi.list({
        page,
        page_size: 20,
        risk_level: riskFilter || undefined,
        is_blocked: blockedFilter,
        search: search || undefined,
      })
      setData(res.data)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { fetch() }, [page, riskFilter, blockedFilter])

  const handleSearch = (e: React.FormEvent) => { e.preventDefault(); setPage(1); fetch() }

  const totalPages = data ? Math.ceil(data.total / 20) : 1

  return (
    <div className="space-y-4 animate-fade-in">
      {/* Filters */}
      <div className="card flex flex-wrap gap-3 items-center">
        <form onSubmit={handleSearch} className="flex gap-2 flex-1 min-w-[200px]">
          <div className="relative flex-1">
            <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-500" />
            <input
              type="text"
              className="input pl-8"
              placeholder="Search prompts..."
              value={search}
              onChange={e => setSearch(e.target.value)}
            />
          </div>
          <button type="submit" className="btn-primary text-sm">Search</button>
        </form>

        <div className="flex gap-2 flex-wrap">
          {['', 'LOW', 'MEDIUM', 'HIGH', 'CRITICAL'].map(r => (
            <button
              key={r || 'ALL'}
              onClick={() => { setRiskFilter(r); setPage(1) }}
              className={`text-xs px-3 py-1.5 rounded-lg border transition-colors ${
                riskFilter === r ? 'bg-brand/20 border-brand text-brand' : 'border-surface-3 text-gray-400 hover:text-white'
              }`}
            >
              {r || 'All Risk'}
            </button>
          ))}
          <button
            onClick={() => { setBlockedFilter(blockedFilter === true ? undefined : true); setPage(1) }}
            className={`text-xs px-3 py-1.5 rounded-lg border transition-colors ${
              blockedFilter === true ? 'bg-red-500/20 border-red-500 text-red-400' : 'border-surface-3 text-gray-400 hover:text-white'
            }`}
          >
            Blocked Only
          </button>
        </div>

        {data && (
          <span className="text-xs text-gray-500 ml-auto">{data.total} results</span>
        )}
      </div>

      {/* Table */}
      <div className="card p-0 overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-surface-3">
                <th className="text-left px-4 py-3 section-title">User</th>
                <th className="text-left px-4 py-3 section-title">Prompt</th>
                <th className="text-left px-4 py-3 section-title">Risk</th>
                <th className="text-left px-4 py-3 section-title">Action</th>
                <th className="text-left px-4 py-3 section-title">Score</th>
                <th className="text-left px-4 py-3 section-title">Time</th>
                <th className="px-4 py-3"></th>
              </tr>
            </thead>
            <tbody>
              {loading && (
                <tr><td colSpan={7} className="text-center py-10 text-gray-500">Loading...</td></tr>
              )}
              {!loading && data?.items.length === 0 && (
                <tr><td colSpan={7} className="text-center py-10 text-gray-500">No prompts found.</td></tr>
              )}
              {data?.items.map(p => (
                <>
                  <tr
                    key={p.id}
                    className="border-b border-surface-3 hover:bg-surface-2 cursor-pointer transition-colors"
                    onClick={() => setExpanded(expanded === p.id ? null : p.id)}
                  >
                    <td className="px-4 py-3">
                      <div className="font-medium text-white">{p.username ?? '—'}</div>
                      <div className="text-xs text-gray-500">{p.department ?? '—'}</div>
                    </td>
                    <td className="px-4 py-3 max-w-xs">
                      <p className="text-gray-300 truncate">{p.prompt_text}</p>
                      {p.flags && p.flags.length > 0 && (
                        <div className="flex gap-1 mt-1 flex-wrap">
                          {p.flags.slice(0, 2).map(f => <FlagChip key={f} flag={f} />)}
                          {p.flags.length > 2 && <span className="text-xs text-gray-600">+{p.flags.length - 2}</span>}
                        </div>
                      )}
                    </td>
                    <td className="px-4 py-3"><RiskBadge level={p.risk_level as 'LOW'|'MEDIUM'|'HIGH'|'CRITICAL'} /></td>
                    <td className="px-4 py-3"><ActionBadge action={p.policy_action as 'ALLOW'|'WARN'|'REDACT'|'BLOCK'} /></td>
                    <td className="px-4 py-3"><RiskScore score={p.risk_score} /></td>
                    <td className="px-4 py-3 text-xs text-gray-500 whitespace-nowrap">
                      {formatDistanceToNow(new Date(p.created_at), { addSuffix: true })}
                    </td>
                    <td className="px-4 py-3 text-gray-500">
                      {expanded === p.id ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
                    </td>
                  </tr>
                  {expanded === p.id && (
                    <tr key={`${p.id}-expanded`} className="bg-surface-2">
                      <td colSpan={7} className="px-6 py-4 space-y-3">
                        <div>
                          <p className="section-title mb-1">Full Prompt</p>
                          <p className="text-sm text-gray-300 font-mono whitespace-pre-wrap">{p.prompt_text}</p>
                        </div>
                        {p.redacted_prompt && (
                          <div>
                            <p className="section-title mb-1 text-blue-400">Redacted (sent to LLM)</p>
                            <p className="text-sm text-gray-300 font-mono whitespace-pre-wrap">{p.redacted_prompt}</p>
                          </div>
                        )}
                        {p.response_text && (
                          <div>
                            <p className="section-title mb-1">LLM Response</p>
                            <p className="text-sm text-gray-300">{p.response_text}</p>
                          </div>
                        )}
                        {p.knowledge_shield_score != null && (
                          <div>
                            <p className="section-title mb-1">Knowledge Shield Score</p>
                            <p className="text-sm text-purple-400 font-mono">{(p.knowledge_shield_score * 100).toFixed(1)}% similarity</p>
                          </div>
                        )}
                      </td>
                    </tr>
                  )}
                </>
              ))}
            </tbody>
          </table>
        </div>

        {/* Pagination */}
        {totalPages > 1 && (
          <div className="flex items-center justify-between px-4 py-3 border-t border-surface-3">
            <button onClick={() => setPage(p => Math.max(1, p - 1))} disabled={page === 1} className="btn-ghost text-sm disabled:opacity-50">← Prev</button>
            <span className="text-xs text-gray-500">Page {page} of {totalPages}</span>
            <button onClick={() => setPage(p => Math.min(totalPages, p + 1))} disabled={page === totalPages} className="btn-ghost text-sm disabled:opacity-50">Next →</button>
          </div>
        )}
      </div>
    </div>
  )
}
