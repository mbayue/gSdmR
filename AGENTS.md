# AGENTS.md — AI Agent Instructions for gSdm-R

## Project Overview

gSdm-R is an OpenAI/Anthropic compatible API router with a React dashboard. It proxies LLM requests to multiple backend providers with load balancing, failover, rate limiting, and usage tracking.

## Quick Reference

- **Language:** Python 3.11+ (backend), TypeScript (frontend)
- **Framework:** FastAPI (backend), React 19 + Vite (frontend)
- **Database:** SQLite (aiosqlite, singleton connection, WAL mode)
- **Styling:** Tailwind CSS v4 + shadcn/ui (dark theme)
- **Testing:** pytest + pytest-asyncio (148 tests)
- **Package Manager:** pip/venv (backend), bun (frontend)

## Commands

```bash
# Run backend (with auto-reload)
cd backend && venv\Scripts\uvicorn main:app --reload --port 8000

# Run frontend (with HMR)
cd frontend && bun dev

# Run both
.\start.ps1

# Run tests
backend\venv\Scripts\python -m pytest backend\tests\ -q

# Type check frontend
cd frontend && npx tsc --noEmit

# Build frontend
cd frontend && npx vite build

# Docker
docker build -t gsdm-r .
```

## Architecture

```
Client → [API Key Auth] → [Rate Limit] → [Route Request] → [Provider Fallback] → Provider API
                                                ↓
                                        [Usage Logging]

Dashboard → [JWT Auth] → [CRUD APIs] → SQLite DB
```

## Key Design Decisions

1. **Singleton DB connection** — `get_db()` returns shared connection, closed on app shutdown
2. **All errors** — consistent `{"error": {"message", "type", "code"}}` format
3. **Proxy is transparent** — forwards body unchanged except swapping `model` field
4. **Health checks** — background task auto-disables bad providers
5. **Rate limiting** — in-memory sliding window, per-key configurable
6. **Disabled provider models** — specific provider+model combos can be deactivated via Playground; routing automatically skips them

## When Modifying Code

### Backend
- Add new endpoints in `backend/routers/`
- Register them in `backend/main.py`
- Add business logic in `backend/services/`
- Schema changes: update `SCHEMA_SQL` + add migration in `init_db()`
- Tests must patch `get_db` in every module that imports it

### Frontend
- Add pages in `frontend/src/pages/`
- Add routes in `frontend/src/App.tsx`
- Add nav links in `frontend/src/components/Layout.tsx`
- Data hooks in `frontend/src/hooks/`
- Types in `frontend/src/types/index.ts`

### Database Schema Changes
- Update `SCHEMA_SQL` in `database.py` (for new databases)
- Add `ALTER TABLE` migration in `init_db()` (for existing databases)
- Always use try/except around ALTER since column may already exist

## Don't

- Don't close `db` connections in route handlers (singleton)
- Don't use inline styles in frontend (use Tailwind)
- Don't use `useEffect` for data fetching (use TanStack Query)
- Don't commit `.env`, `*.db`, `venv/`, `node_modules/`
- Don't modify `components/ui/` files (shadcn managed)
