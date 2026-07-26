# CLAUDE.md (frontend)

Guidance for Claude Code when working inside `frontend/`. See the [root CLAUDE.md](../CLAUDE.md) for what the platform does overall and cross-cutting gotchas (including a port-mismatch note relevant to `vite.config.ts`).

## Commands

```bash
npm install
npm run dev       # http://localhost:5173
npm run build     # tsc -b && vite build
npm run preview
```

No test runner is configured — `npm run build` (via `tsc -b`) is the only automated check.

## Architecture

- `src/App.tsx` — route table; most routes are wrapped in `AdminRoute` (admin-only) except `/console` (prompt submission, available to all authenticated roles).
- `src/context/AuthContext.tsx` — JWT + user persisted to `localStorage`; `src/services/api.ts` is a single axios instance that injects the bearer token and redirects to `/login` on 401.
- `src/services/api.ts` — the only place HTTP calls are made; grouped by resource (`authApi`, `promptsApi`, `analyticsApi`, `policiesApi`, `knowledgeShieldApi`, `auditApi`). Add new endpoints here rather than calling axios directly from components.
- `src/types/index.ts` — shared TypeScript interfaces mirroring the backend Pydantic schemas/ORM models; keep these in sync when changing API response shapes.

## Accessibility

All code here must meet WCAG 2.1 AA: semantic HTML elements (`button`, `nav`, `main`, `header`) over generic `div`s with click handlers, visible focus indicators, `label` or `aria-label` on every form input, keyboard-operable interactive elements, and a minimum 4.5:1 text contrast ratio (3:1 for large text). Don't rely on color alone to convey risk level or status — pair `RiskBadge`/status colors with text or icons.
