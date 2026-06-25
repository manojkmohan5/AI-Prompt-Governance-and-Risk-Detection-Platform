import { useEffect, useState } from 'react'
import { auditApi } from '../services/api'
import type { AuditLog, PaginatedResponse } from '../types'
import { Search, ClipboardList } from 'lucide-react'
import { formatDistanceToNow, format } from 'date-fns'

export default function AuditLogsPage() {
  const [data, setData] = useState<PaginatedResponse<AuditLog> | null>(null)
  const [loading, setLoading] = useState(true)
  const [page, setPage] = useState(1)
  const [username, setUsername] = useState('')
  const [expanded, setExpanded] = useState<string | null>(null)

  const fetch = async () => {
    setLoading(true)
    try {
      const res = await auditApi.list({ page, page_size: 25, username: username || undefined })
      setData(res.data)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { fetch() }, [page])

  const handleSearch = (e: React.FormEvent) => { e.preventDefault(); setPage(1); fetch() }

  const EVENT_COLORS: Record<string, string> = {
    PROMPT_PROCESSED: 'text-blue-400',
    PROMPT_BLOCKED: 'text-red-400',
    LOGIN: 'text-green-400',
    POLICY_VIOLATION: 'text-orange-400',
  }

  const totalPages = data ? Math.ceil(data.total / 25) : 1

  return (
    <div className="space-y-4 animate-fade-in">
      {/* Filter */}
      <div className="card">
        <form onSubmit={handleSearch} className="flex gap-3">
          <div className="relative flex-1">
            <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-500" />
            <input
              type="text"
              className="input pl-8"
              placeholder="Filter by username..."
              value={username}
              onChange={e => setUsername(e.target.value)}
            />
          </div>
          <button type="submit" className="btn-primary text-sm">Filter</button>
          <button type="button" onClick={() => { setUsername(''); setPage(1); setTimeout(fetch, 0) }} className="btn-ghost text-sm">Clear</button>
        </form>
        {data && <p className="text-xs text-gray-500 mt-2">{data.total} audit events</p>}
      </div>

      {/* Table */}
      <div className="card p-0 overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-surface-3">
                <th className="text-left px-4 py-3 section-title">Timestamp</th>
                <th className="text-left px-4 py-3 section-title">User</th>
                <th className="text-left px-4 py-3 section-title">Department</th>
                <th className="text-left px-4 py-3 section-title">Event</th>
                <th className="text-left px-4 py-3 section-title">Risk</th>
                <th className="text-left px-4 py-3 section-title">Action</th>
                <th className="px-4 py-3"></th>
              </tr>
            </thead>
            <tbody>
              {loading && (
                <tr><td colSpan={7} className="text-center py-10 text-gray-500">Loading audit logs...</td></tr>
              )}
              {!loading && data?.items.length === 0 && (
                <tr>
                  <td colSpan={7} className="text-center py-16">
                    <ClipboardList size={32} className="mx-auto text-gray-600 mb-2" />
                    <p className="text-gray-500">No audit logs found.</p>
                  </td>
                </tr>
              )}
              {data?.items.map((log) => (
                <>
                  <tr
                    key={log.id}
                    className="border-b border-surface-3 hover:bg-surface-2 cursor-pointer transition-colors"
                    onClick={() => setExpanded(expanded === log.id ? null : log.id)}
                  >
                    <td className="px-4 py-3">
                      <p className="text-white font-mono text-xs">{format(new Date(log.created_at), 'MMM dd HH:mm:ss')}</p>
                      <p className="text-gray-600 text-xs">{formatDistanceToNow(new Date(log.created_at), { addSuffix: true })}</p>
                    </td>
                    <td className="px-4 py-3 font-medium text-white">{log.username ?? 'system'}</td>
                    <td className="px-4 py-3 text-gray-400 text-xs">{log.department ?? '—'}</td>
                    <td className="px-4 py-3">
                      <span className={`font-mono text-xs ${EVENT_COLORS[log.event_type] ?? 'text-gray-400'}`}>
                        {log.event_type}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      {log.event_data?.risk_score != null && (
                        <span className={`text-sm font-mono font-bold ${
                          (log.event_data.risk_score as number) >= 80 ? 'text-red-400' :
                          (log.event_data.risk_score as number) >= 60 ? 'text-orange-400' :
                          (log.event_data.risk_score as number) >= 30 ? 'text-yellow-400' : 'text-green-400'
                        }`}>{String(log.event_data.risk_score)}</span>
                      )}
                    </td>
                    <td className="px-4 py-3">
                      {log.event_data?.policy_action && (
                        <span className={`text-xs font-mono font-bold ${
                          log.event_data.policy_action === 'BLOCK' ? 'text-red-400' :
                          log.event_data.policy_action === 'WARN' ? 'text-yellow-400' :
                          log.event_data.policy_action === 'REDACT' ? 'text-blue-400' : 'text-green-400'
                        }`}>{String(log.event_data.policy_action)}</span>
                      )}
                    </td>
                    <td className="px-4 py-3 text-gray-600 text-xs">{log.id.slice(0, 8)}</td>
                  </tr>
                  {expanded === log.id && (
                    <tr key={`${log.id}-detail`} className="bg-surface-2">
                      <td colSpan={7} className="px-6 py-4">
                        <div className="grid grid-cols-2 gap-4 text-xs">
                          <div>
                            <p className="section-title mb-1">Event ID</p>
                            <p className="text-gray-300 font-mono">{log.id}</p>
                          </div>
                          {log.prompt_id && (
                            <div>
                              <p className="section-title mb-1">Prompt ID</p>
                              <p className="text-gray-300 font-mono">{log.prompt_id}</p>
                            </div>
                          )}
                          {log.event_data?.flags && (Array.isArray(log.event_data.flags) && log.event_data.flags.length > 0) && (
                            <div className="col-span-2">
                              <p className="section-title mb-1">Flags</p>
                              <div className="flex gap-2 flex-wrap">
                                {(log.event_data.flags as string[]).map((f: string) => (
                                  <span key={f} className="badge bg-surface-3 text-gray-300 font-mono">{f}</span>
                                ))}
                              </div>
                            </div>
                          )}
                        </div>
                      </td>
                    </tr>
                  )}
                </>
              ))}
            </tbody>
          </table>
        </div>

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
