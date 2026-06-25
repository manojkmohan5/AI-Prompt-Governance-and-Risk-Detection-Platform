import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Shield, Eye, EyeOff, AlertCircle } from 'lucide-react'
import { authApi } from '../services/api'
import { useAuth } from '../context/AuthContext'
import type { User } from '../types'

export default function LoginPage() {
  const navigate = useNavigate()
  const { login } = useAuth()
  const [email, setEmail] = useState('admin@acme.corp')
  const [password, setPassword] = useState('Admin@1234')
  const [showPw, setShowPw] = useState(false)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      const res = await authApi.login(email, password)
      login(res.data.user as User, res.data.access_token)
      navigate('/')
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      setError(msg ?? 'Login failed. Check your credentials.')
    } finally {
      setLoading(false)
    }
  }

  const DEMO_ACCOUNTS = [
    { label: 'Admin',       email: 'admin@acme.corp',      password: 'Admin@1234', role: 'Admin',    dept: 'Security',     desc: 'Full access — policies, analytics, audit' },
    { label: 'James Wong',  email: 'james.wong@acme.corp', password: 'User@1234',  role: 'Employee', dept: 'Engineering',  desc: 'Prompt Console only' },
    { label: 'Lisa Park',   email: 'lisa.park@acme.corp',  password: 'User@1234',  role: 'Employee', dept: 'Sales',        desc: 'Prompt Console only' },
    { label: 'Mark Chen',   email: 'mark.chen@acme.corp',  password: 'User@1234',  role: 'Employee', dept: 'Finance',      desc: 'Prompt Console only' },
  ]

  return (
    <div className="min-h-screen bg-surface-0 flex">
      {/* Left panel */}
      <div className="hidden lg:flex lg:w-1/2 bg-surface-1 border-r border-surface-3 flex-col justify-between p-12">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 bg-brand rounded-xl flex items-center justify-center">
            <Shield size={20} className="text-white" />
          </div>
          <div>
            <p className="text-white font-bold">AI Governance Platform</p>
            <p className="text-gray-500 text-xs">Enterprise AI Risk & Compliance</p>
          </div>
        </div>

        <div className="space-y-6">
          <h2 className="text-3xl font-bold text-white leading-tight">
            Govern Every<br />
            <span className="text-brand">AI Interaction</span>
          </h2>
          <p className="text-gray-400">
            Enterprise-grade AI middleware for prompt inspection, risk scoring, policy enforcement, and compliance analytics.
          </p>
          <div className="grid grid-cols-2 gap-3 text-sm">
            {[
              'Prompt Injection Detection',
              'PII Redaction',
              'Knowledge Shield',
              'Compliance Audit Trail',
              'Real-time Risk Scoring',
              'Policy Enforcement',
            ].map((f) => (
              <div key={f} className="flex items-center gap-2 text-gray-300">
                <span className="w-1.5 h-1.5 rounded-full bg-brand flex-shrink-0" />
                {f}
              </div>
            ))}
          </div>
        </div>

        <div className="flex items-center gap-6 text-xs text-gray-600">
          <span>SOC 2 Ready</span>
          <span>GDPR Compliant</span>
          <span>HIPAA Aware</span>
        </div>
      </div>

      {/* Right panel */}
      <div className="flex-1 flex items-center justify-center p-8">
        <div className="w-full max-w-md">
          <div className="lg:hidden flex items-center gap-2 mb-8">
            <Shield size={20} className="text-brand" />
            <span className="text-white font-bold">AI Governance Platform</span>
          </div>

          <h1 className="text-2xl font-bold text-white mb-1">Sign in</h1>
          <p className="text-gray-500 text-sm mb-8">Access the governance dashboard</p>

          {error && (
            <div className="flex items-center gap-2 bg-red-500/10 border border-red-500/30 text-red-400 rounded-lg px-4 py-3 mb-6 text-sm">
              <AlertCircle size={16} />
              {error}
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="block text-xs text-gray-400 mb-1.5">Email</label>
              <input
                type="email"
                className="input"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@company.com"
                required
              />
            </div>
            <div>
              <label className="block text-xs text-gray-400 mb-1.5">Password</label>
              <div className="relative">
                <input
                  type={showPw ? 'text' : 'password'}
                  className="input pr-10"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="••••••••"
                  required
                />
                <button
                  type="button"
                  onClick={() => setShowPw(!showPw)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-500 hover:text-gray-300"
                >
                  {showPw ? <EyeOff size={16} /> : <Eye size={16} />}
                </button>
              </div>
            </div>
            <button type="submit" className="btn-primary w-full mt-6" disabled={loading}>
              {loading ? 'Signing in...' : 'Sign in'}
            </button>
          </form>

          {/* Demo accounts */}
          <div className="mt-8 border-t border-surface-3 pt-6">
            <p className="text-xs text-gray-500 mb-3">Demo accounts — click to fill</p>
            <div className="space-y-2">
              {DEMO_ACCOUNTS.map((a) => (
                <button
                  key={a.email}
                  onClick={() => { setEmail(a.email); setPassword(a.password) }}
                  className="w-full flex items-center justify-between px-3 py-2.5 bg-surface-2 hover:bg-surface-3 rounded-lg transition-colors text-xs text-left"
                >
                  <div className="min-w-0">
                    <div className="flex items-center gap-2 mb-0.5">
                      <span className="text-gray-200 font-medium">{a.label}</span>
                      <span className={`text-[10px] px-1.5 py-0.5 rounded font-medium ${a.role === 'Admin' ? 'bg-brand/20 text-brand' : 'bg-surface-3 text-gray-400'}`}>
                        {a.role}
                      </span>
                      <span className="text-gray-600">{a.dept}</span>
                    </div>
                    <span className="text-gray-500 font-mono">{a.email}</span>
                  </div>
                  <span className="text-gray-600 font-mono ml-3 shrink-0">{a.password}</span>
                </button>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
