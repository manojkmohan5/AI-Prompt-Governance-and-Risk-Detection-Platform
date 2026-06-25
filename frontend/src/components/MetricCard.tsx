import type { ReactNode } from 'react'

interface MetricCardProps {
  label: string
  value: string | number
  sub?: string
  icon?: ReactNode
  accent?: 'green' | 'red' | 'yellow' | 'blue' | 'purple' | 'default'
  trend?: { value: number; label: string }
}

const ACCENT_BG: Record<string, string> = {
  green: 'bg-green-500/10 border-green-500/20',
  red: 'bg-red-500/10 border-red-500/20',
  yellow: 'bg-yellow-500/10 border-yellow-500/20',
  blue: 'bg-blue-500/10 border-blue-500/20',
  purple: 'bg-purple-500/10 border-purple-500/20',
  default: 'bg-surface-2 border-surface-3',
}

const ACCENT_ICON: Record<string, string> = {
  green: 'text-green-400',
  red: 'text-red-400',
  yellow: 'text-yellow-400',
  blue: 'text-blue-400',
  purple: 'text-purple-400',
  default: 'text-gray-400',
}

export function MetricCard({ label, value, sub, icon, accent = 'default', trend }: MetricCardProps) {
  return (
    <div className={`card border ${ACCENT_BG[accent]} animate-fade-in`}>
      <div className="flex items-start justify-between">
        <div className="flex-1">
          <p className="section-title mb-2">{label}</p>
          <p className="stat-value">{value}</p>
          {sub && <p className="text-xs text-gray-500 mt-1">{sub}</p>}
          {trend && (
            <p className={`text-xs mt-1 ${trend.value >= 0 ? 'text-green-400' : 'text-red-400'}`}>
              {trend.value >= 0 ? '↑' : '↓'} {Math.abs(trend.value)}% {trend.label}
            </p>
          )}
        </div>
        {icon && (
          <div className={`text-2xl ${ACCENT_ICON[accent]} opacity-80`}>
            {icon}
          </div>
        )}
      </div>
    </div>
  )
}
