import { useEffect, useState } from 'react'
import {
  AreaChart, Area, BarChart, Bar, XAxis, YAxis,
  CartesianGrid, Tooltip, ResponsiveContainer, Legend
} from 'recharts'
import { analyticsApi } from '../services/api'
import type { AnalyticsOverview } from '../types'
import { MetricCard } from '../components/MetricCard'
import { ShieldCheck, CheckCircle, XCircle, AlertTriangle, TrendingDown } from 'lucide-react'

const CustomTooltip = ({ active, payload, label }: { active?: boolean; payload?: { value: number; name: string; color: string }[]; label?: string }) => {
  if (!active || !payload?.length) return null
  return (
    <div className="bg-surface-2 border border-surface-3 rounded-lg px-3 py-2 text-xs shadow-xl">
      <p className="text-gray-400 mb-1">{label}</p>
      {payload.map(p => <p key={p.name} style={{ color: p.color }}>{p.name}: <strong>{p.value}</strong></p>)}
    </div>
  )
}

export default function CompliancePage() {
  const [data, setData] = useState<AnalyticsOverview | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    analyticsApi.overview(30).then(r => { setData(r.data); setLoading(false) }).catch(() => setLoading(false))
  }, [])

  if (loading) return <div className="flex items-center justify-center h-64"><div className="w-6 h-6 border-2 border-brand border-t-transparent rounded-full animate-spin" /></div>
  if (!data) return <div className="text-gray-500 text-center py-20">Failed to load.</div>

  const complianceColor = data.compliance_score >= 90 ? 'green' : data.compliance_score >= 70 ? 'yellow' : 'red'
  const govColor = data.governance_score >= 80 ? 'green' : data.governance_score >= 60 ? 'yellow' : 'red'

  return (
    <div className="space-y-6 animate-fade-in">
      {/* KPI Row */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <MetricCard label="Compliance Score" value={`${data.compliance_score}%`} icon={<ShieldCheck size={20} />} accent={complianceColor as 'green'|'yellow'|'red'} />
        <MetricCard label="Governance Score" value={`${data.governance_score}%`} icon={<TrendingDown size={20} />} accent={govColor as 'green'|'yellow'|'red'} />
        <MetricCard label="Compliant Prompts" value={(data.total_prompts - data.blocked_prompts).toLocaleString()} icon={<CheckCircle size={20} />} accent="green" />
        <MetricCard label="Policy Violations" value={data.blocked_prompts} icon={<XCircle size={20} />} accent="red" />
      </div>

      {/* Blocked / warned trend */}
      <div className="card">
        <h2 className="section-title mb-4">Blocked & Warned Prompts — Last 30 Days</h2>
        <ResponsiveContainer width="100%" height={220}>
          <AreaChart data={data.prompts_over_time}>
            <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
            <XAxis dataKey="date" tick={{ fill: '#6b7280', fontSize: 10 }} tickFormatter={d => d.slice(5)} />
            <YAxis tick={{ fill: '#6b7280', fontSize: 10 }} />
            <Tooltip content={<CustomTooltip />} />
            <Legend wrapperStyle={{ fontSize: 11, color: '#9ca3af' }} />
            <Area type="monotone" dataKey="blocked" stroke="#ef4444" fill="#ef4444" fillOpacity={0.15} strokeWidth={2} name="Blocked" />
            <Area type="monotone" dataKey="high_risk" stroke="#f59e0b" fill="#f59e0b" fillOpacity={0.10} strokeWidth={2} name="High Risk" />
          </AreaChart>
        </ResponsiveContainer>
      </div>

      {/* Compliance checklist */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="card">
          <h2 className="section-title mb-4">Compliance Controls</h2>
          <div className="space-y-3">
            {[
              { label: 'PII Detection Active', pass: true, desc: 'All prompts scanned for PII (SSN, Email, Phone, CC)' },
              { label: 'Prompt Injection Shield', pass: true, desc: 'Rule-based + embedding injection detection' },
              { label: 'Knowledge Shield Enabled', pass: data.total_prompts > 0, desc: 'Semantic similarity against confidential docs' },
              { label: 'Audit Trail Complete', pass: true, desc: 'All events logged with user, timestamp, action' },
              { label: 'Policy Enforcement', pass: true, desc: 'ALLOW / WARN / REDACT / BLOCK rules active' },
              { label: 'Response Inspection', pass: true, desc: 'LLM responses scanned for secret leakage' },
            ].map(item => (
              <div key={item.label} className="flex items-start gap-3">
                {item.pass
                  ? <CheckCircle size={16} className="text-green-400 flex-shrink-0 mt-0.5" />
                  : <XCircle size={16} className="text-red-400 flex-shrink-0 mt-0.5" />}
                <div>
                  <p className="text-sm text-white font-medium">{item.label}</p>
                  <p className="text-xs text-gray-500">{item.desc}</p>
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="card">
          <h2 className="section-title mb-4">Risk by Category</h2>
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={[
              { name: 'LOW', value: data.risk_distribution.LOW, fill: '#22c55e' },
              { name: 'MED', value: data.risk_distribution.MEDIUM, fill: '#f59e0b' },
              { name: 'HIGH', value: data.risk_distribution.HIGH, fill: '#f97316' },
              { name: 'CRIT', value: data.risk_distribution.CRITICAL, fill: '#ef4444' },
            ]}>
              <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
              <XAxis dataKey="name" tick={{ fill: '#6b7280', fontSize: 11 }} />
              <YAxis tick={{ fill: '#6b7280', fontSize: 11 }} />
              <Tooltip content={<CustomTooltip />} />
              <Bar dataKey="value" radius={[4, 4, 0, 0]}>
                {['#22c55e', '#f59e0b', '#f97316', '#ef4444'].map((color, i) => (
                  <rect key={i} fill={color} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Warnings */}
      {data.compliance_score < 90 && (
        <div className="bg-yellow-500/10 border border-yellow-500/30 rounded-xl p-4 flex items-start gap-3">
          <AlertTriangle size={18} className="text-yellow-400 flex-shrink-0 mt-0.5" />
          <div>
            <p className="text-yellow-400 font-medium text-sm">Compliance Below Target</p>
            <p className="text-gray-400 text-xs mt-0.5">
              Compliance score is {data.compliance_score}% (target: 90%). Review blocked prompts and strengthen policies.
            </p>
          </div>
        </div>
      )}
    </div>
  )
}
