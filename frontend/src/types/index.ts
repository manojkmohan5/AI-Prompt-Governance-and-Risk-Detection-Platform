export type RiskLevel = 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL'
export type PolicyAction = 'ALLOW' | 'WARN' | 'REDACT' | 'BLOCK'
export type UserRole = 'admin' | 'employee'

export interface User {
  id: string
  email: string
  username: string
  role: UserRole
  department?: string
  is_active: boolean
  created_at: string
}

export interface PromptRecord {
  id: string
  user_id?: string
  prompt_text: string
  redacted_prompt?: string
  response_text?: string
  model_used: string
  department?: string
  username?: string
  risk_score: number
  risk_level: RiskLevel
  flags: string[]
  policy_action: PolicyAction
  is_blocked: boolean
  tokens_used?: number
  latency_ms?: number
  knowledge_shield_score?: number
  ml_risk_category?: string
  ml_confidence?: number
  compliance_tags?: string[]
  anomaly_detected?: boolean
  anomaly_z_score?: number
  created_at: string
}

export interface AuditLog {
  id: string
  prompt_id?: string
  user_id?: string
  event_type: string
  event_data?: Record<string, unknown>
  username?: string
  department?: string
  ip_address?: string
  created_at: string
}

export interface PolicyRule {
  id: string
  name: string
  description?: string
  condition_type: string
  condition_value: string
  action: PolicyAction
  priority: number
  is_active: boolean
  created_at: string
}

export interface ConfidentialDoc {
  id: string
  name: string
  category: string
  created_at: string
}

export interface RiskDistribution {
  LOW: number
  MEDIUM: number
  HIGH: number
  CRITICAL: number
}

export interface TimeSeriesPoint {
  date: string
  total: number
  blocked: number
  high_risk: number
}

export interface FlagCount {
  flag: string
  count: number
}

export interface ModelUsage {
  model: string
  count: number
}

export interface TopRiskyUser {
  username: string
  department: string
  prompt_count: number
  avg_risk_score: number
  blocked_count: number
}

export interface AnalyticsOverview {
  total_prompts: number
  blocked_prompts: number
  warned_prompts: number
  high_risk_prompts: number
  avg_risk_score: number
  compliance_score: number
  governance_score: number
  risk_distribution: RiskDistribution
  prompts_over_time: TimeSeriesPoint[]
  top_flags: FlagCount[]
  model_distribution: ModelUsage[]
  top_risky_users: TopRiskyUser[]
}

export interface PaginatedResponse<T> {
  items: T[]
  total: number
  page: number
  page_size: number
}
