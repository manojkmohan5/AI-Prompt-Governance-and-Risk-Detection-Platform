import axios from 'axios'

const api = axios.create({
  baseURL: '/api/v1',
  headers: { 'Content-Type': 'application/json' },
})

// Inject JWT on every request
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

// Redirect to login on 401
api.interceptors.response.use(
  (res) => res,
  (err) => {
    if (err.response?.status === 401) {
      localStorage.removeItem('token')
      localStorage.removeItem('user')
      window.location.href = '/login'
    }
    return Promise.reject(err)
  }
)

// ── Auth ──────────────────────────────────────────────────────────────────────
export const authApi = {
  login: (email: string, password: string) =>
    api.post('/auth/login', { email, password }),
}

// ── Prompts ───────────────────────────────────────────────────────────────────
export const promptsApi = {
  submit: (prompt: string, model = 'llama-3.3-70b-versatile', department?: string) =>
    api.post('/prompts', { prompt, model, department }),

  list: (params: {
    page?: number
    page_size?: number
    risk_level?: string
    is_blocked?: boolean
    search?: string
  }) => api.get('/prompts', { params }),

  get: (id: string) => api.get(`/prompts/${id}`),
}

// ── Analytics ─────────────────────────────────────────────────────────────────
export const analyticsApi = {
  overview: (days = 30) => api.get('/analytics/overview', { params: { days } }),
}

// ── Policies ──────────────────────────────────────────────────────────────────
export const policiesApi = {
  list: () => api.get('/policies'),
  create: (body: {
    name: string
    description?: string
    condition_type: string
    condition_value: string
    action: string
    priority?: number
    is_active?: boolean
  }) => api.post('/policies', body),
  toggle: (id: string) => api.patch(`/policies/${id}/toggle`),
  delete: (id: string) => api.delete(`/policies/${id}`),
}

// ── Knowledge Shield ──────────────────────────────────────────────────────────
export const knowledgeShieldApi = {
  listDocs: () => api.get('/knowledge-shield/documents'),
  addDoc: (body: { name: string; content: string; category?: string }) =>
    api.post('/knowledge-shield/documents', body),
  deleteDoc: (id: string) => api.delete(`/knowledge-shield/documents/${id}`),
  status: () => api.get('/knowledge-shield/status'),
}

// ── Audit ──────────────────────────────────────────────────────────────────────
export const auditApi = {
  list: (params: { page?: number; page_size?: number; event_type?: string; username?: string }) =>
    api.get('/audit', { params }),
}

export default api
