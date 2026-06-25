import type { RiskLevel, PolicyAction } from '../types'

const RISK_STYLES: Record<RiskLevel, string> = {
  LOW: 'bg-green-500/15 text-green-400 border border-green-500/30',
  MEDIUM: 'bg-yellow-500/15 text-yellow-400 border border-yellow-500/30',
  HIGH: 'bg-orange-500/15 text-orange-400 border border-orange-500/30',
  CRITICAL: 'bg-red-500/15 text-red-400 border border-red-500/30',
}

const ACTION_STYLES: Record<PolicyAction, string> = {
  ALLOW: 'bg-green-500/15 text-green-400 border border-green-500/30',
  WARN: 'bg-yellow-500/15 text-yellow-400 border border-yellow-500/30',
  REDACT: 'bg-blue-500/15 text-blue-400 border border-blue-500/30',
  BLOCK: 'bg-red-500/15 text-red-400 border border-red-500/30',
}

const RISK_DOTS: Record<RiskLevel, string> = {
  LOW: 'bg-green-400',
  MEDIUM: 'bg-yellow-400',
  HIGH: 'bg-orange-400',
  CRITICAL: 'bg-red-400',
}

export function RiskBadge({ level }: { level: RiskLevel }) {
  return (
    <span className={`badge ${RISK_STYLES[level]}`}>
      <span className={`w-1.5 h-1.5 rounded-full ${RISK_DOTS[level]}`} />
      {level}
    </span>
  )
}

export function ActionBadge({ action }: { action: PolicyAction }) {
  return (
    <span className={`badge ${ACTION_STYLES[action]}`}>
      {action}
    </span>
  )
}

export function RiskScore({ score }: { score: number }) {
  const color =
    score >= 80 ? 'text-red-400' :
    score >= 60 ? 'text-orange-400' :
    score >= 30 ? 'text-yellow-400' :
    'text-green-400'
  return <span className={`font-mono font-bold ${color}`}>{score}</span>
}

export function FlagChip({ flag }: { flag: string }) {
  const styles: Record<string, string> = {
    PROMPT_INJECTION: 'bg-red-500/20 text-red-300 border-red-500/30',
    PII_DETECTED: 'bg-orange-500/20 text-orange-300 border-orange-500/30',
    SENSITIVE_DATA: 'bg-yellow-500/20 text-yellow-300 border-yellow-500/30',
    KNOWLEDGE_SHIELD: 'bg-purple-500/20 text-purple-300 border-purple-500/30',
    TOXICITY: 'bg-red-600/20 text-red-400 border-red-600/30',
    EXCESSIVE_LENGTH: 'bg-gray-500/20 text-gray-400 border-gray-500/30',
    NER_ENTITY: 'bg-blue-500/20 text-blue-300 border-blue-500/30',
    RESPONSE_SECRET_LEAK: 'bg-red-600/20 text-red-400 border-red-600/30',
    RESPONSE_UNSAFE_CONTENT: 'bg-red-500/20 text-red-300 border-red-500/30',
  }
  const cls = styles[flag] ?? 'bg-gray-500/20 text-gray-300 border-gray-500/30'
  return (
    <span className={`badge border ${cls} font-mono`}>
      {flag.replace(/_/g, ' ')}
    </span>
  )
}
