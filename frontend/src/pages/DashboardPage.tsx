import { useEffect, useState } from 'react'
import {
  LineChart, Line, BarChart, Bar, PieChart, Pie, Cell,
  XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend
} from 'recharts'
import { analyticsApi } from '../services/api'
import { MetricCard } from '../components/MetricCard'
import type { AnalyticsOverview } from '../types'
import {
  Activity, ShieldX, AlertTriangle, TrendingUp,
  CheckCircle, Zap
} from 'lucide-react'

const RISK_COLORS = { LOW: '#22c55e', MEDIUM: '#f59e0b', HIGH: '#f97316', CRITICAL: '#ef4444' }
const CHART_COLORS = ['#3b82f6', '#8b5cf6', '#22c55e', '#f59e0b', '#ef4444']

function SectionHeader({ title }: { title: string }) {
  return <h2 className="section-title mb-4">{title}</h2>
}

const CustomTooltip = ({ active, payload, label }: { active?: boolean; payload?: { value: number; name: string; color: string }[]; label?: string }) => {
  if (!active || !payload?.length) return null
  return (
    <div className="bg-surface-2 border border-surface-3 rounded-lg px-3 py-2 text-xs shadow-xl">
      <p className="text-gray-400 mb-1">{label}</p>
      {payload.map((p) => (
        <p key={p.name} style={{ color: p.color }}>{p.name}: <strong>{p.value}</strong></p>
      ))}
    </div>
  )
}

export default function DashboardPage() {
  const [data, setData] = useState<AnalyticsOverview | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    analyticsApi.overview(30).then(r => { setData(r.data); setLoading(false) }).catch(() => setLoading(false))
  }, [])

  if (loading) return (
    <div className="flex items-center justify-center h-64">
      <div className="w-6 h-6 border-2 border-brand border-t-transparent rounded-full animate-spin" />
    </div>
  )

  if (!data) return <div className="text-gray-500 text-center py-20">Failed to load analytics.</div>

  const riskPieData = Object.entries(data.risk_distribution).map(([name, value]) => ({ name, value }))

  return (
    <div className="space-y-6 animate-fade-in">
      {/* KPI Row */}
      <div className="grid grid-cols-2 lg:grid-cols-3 xl:grid-cols-6 gap-4">
        <MetricCard label="Total Prompts" value={data.total_prompts.toLocaleString()} icon={<Activity size={20} />} accent="blue" />
        <MetricCard label="Blocked" value={data.blocked_prompts} icon={<ShieldX size={20} />} accent="red" />
        <MetricCard label="High Risk" value={data.high_risk_prompts} icon={<AlertTriangle size={20} />} accent="yellow" />
        <MetricCard label="Avg Risk Score" value={data.avg_risk_score} icon={<TrendingUp size={20} />} accent="purple" />
        <MetricCard label="Compliance" value={`${data.compliance_score}%`} icon={<CheckCircle size={20} />} accent="green" />
        <MetricCard label="Gov Score" value={`${data.governance_score}%`} icon={<Zap size={20} />} accent="blue" />
      </div>

      {/* Charts row 1 */}
      <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">
        {/* Prompt volume */}
        <div className="card xl:col-span-2">
          <SectionHeader title="Prompt Volume — Last 30 Days" />
          <ResponsiveContainer width="100%" height={200}>
            <LineChart data={data.prompts_over_time.slice(-14)}>
              <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
              <XAxis dataKey="date" tick={{ fill: '#6b7280', fontSize: 10 }} tickFormatter={d => d.slice(5)} />
              <YAxis tick={{ fill: '#6b7280', fontSize: 10 }} />
              <Tooltip content={<CustomTooltip />} />
              <Legend wrapperStyle={{ fontSize: 11, color: '#9ca3af' }} />
              <Line type="monotone" dataKey="total" stroke="#3b82f6" strokeWidth={2} dot={false} name="Total" />
              <Line type="monotone" dataKey="blocked" stroke="#ef4444" strokeWidth={2} dot={false} name="Blocked" />
              <Line type="monotone" dataKey="high_risk" stroke="#f59e0b" strokeWidth={2} dot={false} name="High Risk" />
            </LineChart>
          </ResponsiveContainer>
        </div>

        {/* Risk distribution */}
        <div className="card">
          <SectionHeader title="Risk Distribution" />
          <ResponsiveContainer width="100%" height={200}>
            <PieChart>
              <Pie data={riskPieData} cx="50%" cy="50%" innerRadius={50} outerRadius={80} paddingAngle={3} dataKey="value">
                {riskPieData.map((entry) => (
                  <Cell key={entry.name} fill={RISK_COLORS[entry.name as keyof typeof RISK_COLORS]} />
                ))}
              </Pie>
              <Tooltip content={<CustomTooltip />} />
            </PieChart>
          </ResponsiveContainer>
          <div className="flex flex-wrap gap-2 justify-center mt-2">
            {riskPieData.map(({ name, value }) => (
              <div key={name} className="flex items-center gap-1 text-xs">
                <span className="w-2 h-2 rounded-full" style={{ background: RISK_COLORS[name as keyof typeof RISK_COLORS] }} />
                <span className="text-gray-400">{name}: <strong className="text-white">{value}</strong></span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Charts row 2 */}
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
        {/* Top flags */}
        <div className="card">
          <SectionHeader title="Top Governance Flags" />
          <ResponsiveContainer width="100%" height={180}>
            <BarChart data={data.top_flags.slice(0, 6)} layout="vertical">
              <CartesianGrid strokeDasharray="3 3" stroke="#374151" horizontal={false} />
              <XAxis type="number" tick={{ fill: '#6b7280', fontSize: 10 }} />
              <YAxis type="category" dataKey="flag" width={130} tick={{ fill: '#9ca3af', fontSize: 10 }}
                tickFormatter={s => s.replace(/_/g, ' ')} />
              <Tooltip content={<CustomTooltip />} />
              <Bar dataKey="count" radius={[0, 4, 4, 0]}>
                {data.top_flags.slice(0, 6).map((_, i) => (
                  <Cell key={i} fill={CHART_COLORS[i % CHART_COLORS.length]} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>

        {/* Top risky users */}
        <div className="card">
          <SectionHeader title="Top Risky Users" />
          <div className="space-y-2">
            {data.top_risky_users.map((u, i) => (
              <div key={u.username} className="flex items-center gap-3 py-2 border-b border-surface-3 last:border-0">
                <span className="text-xs text-gray-600 w-4">{i + 1}</span>
                <div className="w-7 h-7 rounded-full bg-surface-3 flex items-center justify-center text-xs font-bold text-brand">
                  {u.username[0].toUpperCase()}
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-sm text-white font-medium truncate">{u.username}</p>
                  <p className="text-xs text-gray-500">{u.department} · {u.prompt_count} prompts</p>
                </div>
                <div className="text-right">
                  <p className={`text-sm font-mono font-bold ${u.avg_risk_score >= 60 ? 'text-red-400' : u.avg_risk_score >= 30 ? 'text-yellow-400' : 'text-green-400'}`}>
                    {u.avg_risk_score}
                  </p>
                  <p className="text-xs text-gray-500">{u.blocked_count} blocked</p>
                </div>
              </div>
            ))}
            {data.top_risky_users.length === 0 && (
              <p className="text-gray-500 text-sm text-center py-4">No prompt activity yet.</p>
            )}
          </div>
        </div>
      </div>

      {/* Model usage */}
      {data.model_distribution.length > 0 && (
        <div className="card">
          <SectionHeader title="Model Usage" />
          <div className="flex flex-wrap gap-4">
            {data.model_distribution.map((m, i) => (
              <div key={m.model} className="flex items-center gap-2 bg-surface-2 px-3 py-2 rounded-lg">
                <span className="w-2 h-2 rounded-full" style={{ background: CHART_COLORS[i % CHART_COLORS.length] }} />
                <span className="text-sm text-white font-mono">{m.model}</span>
                <span className="text-gray-500 text-xs">{m.count} calls</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
