import { useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import {
  LayoutDashboard, Terminal, Activity, AlertTriangle,
  ShieldCheck, ClipboardList, BookLock, Settings,
  LogOut, ChevronLeft, ChevronRight, Shield, Bell
} from 'lucide-react'

const ADMIN_NAV = [
  { to: '/', icon: LayoutDashboard, label: 'Dashboard' },
  { to: '/console', icon: Terminal, label: 'Prompt Console' },
  { to: '/live-feed', icon: Activity, label: 'Live Event Feed' },
  { to: '/risk', icon: AlertTriangle, label: 'Risk Explorer' },
  { to: '/compliance', icon: ShieldCheck, label: 'Compliance' },
  { to: '/audit', icon: ClipboardList, label: 'Audit Logs' },
  { to: '/knowledge-shield', icon: BookLock, label: 'Knowledge Shield' },
  { to: '/settings', icon: Settings, label: 'Settings' },
]

const EMPLOYEE_NAV = [
  { to: '/console', icon: Terminal, label: 'Prompt Console' },
]

export function DashboardLayout({ children }: { children: React.ReactNode }) {
  const { user, logout } = useAuth()
  const location = useLocation()
  const navigate = useNavigate()
  const [collapsed, setCollapsed] = useState(false)
  const isAdmin = user?.role === 'admin'
  const NAV_ITEMS = isAdmin ? ADMIN_NAV : EMPLOYEE_NAV

  const handleLogout = () => {
    logout()
    navigate('/login')
  }

  return (
    <div className="flex h-screen overflow-hidden bg-surface-0">
      {/* Sidebar */}
      <aside
        className={`
          flex flex-col bg-surface-1 border-r border-surface-3 transition-all duration-200
          ${collapsed ? 'w-16' : 'w-60'}
        `}
      >
        {/* Logo */}
        <div className="flex items-center gap-3 px-4 py-4 border-b border-surface-3">
          <div className="flex-shrink-0 w-8 h-8 bg-brand rounded-lg flex items-center justify-center">
            <Shield size={16} className="text-white" />
          </div>
          {!collapsed && (
            <div>
              <p className="text-white font-bold text-sm leading-none">AI Govern</p>
              <p className="text-gray-500 text-xs">Risk Platform</p>
            </div>
          )}
          <button
            onClick={() => setCollapsed(!collapsed)}
            className="ml-auto text-gray-500 hover:text-white transition-colors"
          >
            {collapsed ? <ChevronRight size={14} /> : <ChevronLeft size={14} />}
          </button>
        </div>

        {/* Nav */}
        <nav className="flex-1 py-4 space-y-0.5 overflow-y-auto">
          {NAV_ITEMS.map(({ to, icon: Icon, label }) => {
            const active = location.pathname === to
            return (
              <Link
                key={to}
                to={to}
                title={collapsed ? label : undefined}
                className={`
                  flex items-center gap-3 px-4 py-2.5 text-sm transition-colors rounded-none
                  ${active
                    ? 'bg-brand/15 text-brand border-r-2 border-brand'
                    : 'text-gray-400 hover:text-white hover:bg-surface-2'
                  }
                `}
              >
                <Icon size={16} className="flex-shrink-0" />
                {!collapsed && <span>{label}</span>}
              </Link>
            )
          })}
        </nav>

        {/* User */}
        <div className="border-t border-surface-3 p-3">
          {!collapsed ? (
            <div className="flex items-center gap-2">
              <div className="w-7 h-7 rounded-full bg-brand/30 flex items-center justify-center text-xs font-bold text-brand">
                {user?.username?.[0]?.toUpperCase()}
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-xs text-white truncate">{user?.username}</p>
                <p className="text-xs text-gray-500 truncate capitalize">{user?.role}</p>
              </div>
              <button onClick={handleLogout} className="text-gray-500 hover:text-red-400 transition-colors">
                <LogOut size={14} />
              </button>
            </div>
          ) : (
            <button onClick={handleLogout} title="Logout" className="w-full flex justify-center text-gray-500 hover:text-red-400">
              <LogOut size={16} />
            </button>
          )}
        </div>
      </aside>

      {/* Main */}
      <main className="flex-1 flex flex-col overflow-hidden">
        {/* Top bar */}
        <header className="flex items-center justify-between px-6 py-3 border-b border-surface-3 bg-surface-1 flex-shrink-0">
          <div>
            <h1 className="text-white font-semibold text-base">
              {NAV_ITEMS.find(n => n.to === location.pathname)?.label ?? 'AI Governance Platform'}
            </h1>
            <p className="text-xs text-gray-500 font-mono">
              ACME Corp · {user?.department ?? 'Corporate'}
            </p>
          </div>
          <div className="flex items-center gap-3">
            <div className="flex items-center gap-1.5 px-2 py-1 bg-green-500/10 border border-green-500/20 rounded-full">
              <span className="w-1.5 h-1.5 rounded-full bg-green-400 animate-pulse" />
              <span className="text-xs text-green-400 font-medium">Governance Active</span>
            </div>
            <button className="btn-ghost p-2">
              <Bell size={16} />
            </button>
          </div>
        </header>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-6">
          {children}
        </div>
      </main>
    </div>
  )
}
