import { useEffect, useState, useRef } from 'react'
import { promptsApi } from '../services/api'
import type { PromptRecord } from '../types'
import { RiskBadge, ActionBadge, FlagChip } from '../components/RiskBadge'
import { RefreshCw, Pause, Play, Activity } from 'lucide-react'
import { formatDistanceToNow } from 'date-fns'

export default function LiveEventFeedPage() {
  const [events, setEvents] = useState<PromptRecord[]>([])
  const [loading, setLoading] = useState(true)
  const [paused, setPaused] = useState(false)
  const [filter, setFilter] = useState<string>('ALL')
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const fetchEvents = async () => {
    try {
      const res = await promptsApi.list({ page: 1, page_size: 50 })
      setEvents(res.data.items)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchEvents()
  }, [])

  useEffect(() => {
    if (!paused) {
      intervalRef.current = setInterval(fetchEvents, 5000)
    }
    return () => { if (intervalRef.current) clearInterval(intervalRef.current) }
  }, [paused])

  const filtered = filter === 'ALL' ? events :
    filter === 'BLOCKED' ? events.filter(e => e.is_blocked) :
    events.filter(e => e.risk_level === filter)

  return (
    <div className="space-y-4 animate-fade-in">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2">
            <span className={`w-2 h-2 rounded-full ${paused ? 'bg-gray-500' : 'bg-green-400 animate-pulse'}`} />
            <span className="text-sm text-gray-400">{paused ? 'Paused' : 'Live — refreshing every 5s'}</span>
          </div>
          <span className="text-xs text-gray-600">|</span>
          <span className="text-xs text-gray-500">{filtered.length} events</span>
        </div>
        <div className="flex items-center gap-2">
          {(['ALL', 'LOW', 'MEDIUM', 'HIGH', 'CRITICAL', 'BLOCKED'] as const).map(f => (
            <button
              key={f}
              onClick={() => setFilter(f)}
              className={`text-xs px-2.5 py-1 rounded-full border transition-colors ${
                filter === f
                  ? 'bg-brand/20 border-brand text-brand'
                  : 'border-surface-3 text-gray-400 hover:text-white'
              }`}
            >
              {f}
            </button>
          ))}
          <button
            onClick={() => setPaused(!paused)}
            className="btn-ghost flex items-center gap-1 text-sm"
          >
            {paused ? <Play size={14} /> : <Pause size={14} />}
            {paused ? 'Resume' : 'Pause'}
          </button>
          <button onClick={fetchEvents} className="btn-ghost p-2">
            <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
          </button>
        </div>
      </div>

      {/* Feed */}
      <div className="space-y-2">
        {loading && (
          <div className="flex items-center justify-center py-16">
            <div className="w-6 h-6 border-2 border-brand border-t-transparent rounded-full animate-spin" />
          </div>
        )}

        {!loading && filtered.length === 0 && (
          <div className="card text-center py-16">
            <Activity size={32} className="mx-auto text-gray-600 mb-3" />
            <p className="text-gray-500">No events yet. Submit prompts via the Prompt Console.</p>
          </div>
        )}

        {filtered.map((e) => (
          <div
            key={e.id}
            className={`card flex items-start gap-4 border-l-2 ${
              e.is_blocked ? 'border-l-red-500' :
              e.risk_level === 'CRITICAL' ? 'border-l-red-500' :
              e.risk_level === 'HIGH' ? 'border-l-orange-500' :
              e.risk_level === 'MEDIUM' ? 'border-l-yellow-500' :
              'border-l-green-500'
            } animate-fade-in`}
          >
            <div className="flex-shrink-0 w-8 h-8 rounded-full bg-surface-2 flex items-center justify-center text-xs font-bold text-gray-400 mt-0.5">
              {(e.username ?? 'A')[0].toUpperCase()}
            </div>
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 mb-1 flex-wrap">
                <span className="text-sm font-medium text-white">{e.username ?? 'anonymous'}</span>
                {e.department && <span className="text-xs text-gray-500">{e.department}</span>}
                <span className="text-xs text-gray-600">·</span>
                <span className="text-xs text-gray-500">
                  {formatDistanceToNow(new Date(e.created_at), { addSuffix: true })}
                </span>
              </div>
              <p className="text-sm text-gray-300 truncate font-mono">
                {e.prompt_text.slice(0, 120)}{e.prompt_text.length > 120 ? '...' : ''}
              </p>
              {e.flags && e.flags.length > 0 && (
                <div className="flex flex-wrap gap-1 mt-2">
                  {e.flags.map(f => <FlagChip key={f} flag={f} />)}
                </div>
              )}
            </div>
            <div className="flex-shrink-0 flex flex-col items-end gap-1.5">
              <RiskBadge level={e.risk_level as 'LOW'|'MEDIUM'|'HIGH'|'CRITICAL'} />
              <ActionBadge action={e.policy_action as 'ALLOW'|'WARN'|'REDACT'|'BLOCK'} />
              <span className="text-xs font-mono text-gray-600">{e.risk_score}/100</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
