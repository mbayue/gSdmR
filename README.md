# gSdm-R

OpenAI / Anthropic compatible API router with priority-based provider fallback, load balancing, and a management dashboard.

## What it does

- Accepts requests in OpenAI (`/v1/chat/completions`, `/v1/responses`) and Anthropic (`/v1/messages`) formats
- Routes to multiple backend providers with configurable load balancing (priority, round-robin, weighted-random)
- Automatic failover when a provider is down
- Per-key rate limiting and model access restrictions
- Dashboard for managing providers, models, API keys, and usage stats

## Quick Start

```bash
# Clone and setup
git clone <your-repo-url>
cd gsdmR

# Backend
cd backend
python -m venv venv
venv\Scripts\pip install -r requirements.txt  # Windows
# or: venv/bin/pip install -r requirements.txt  # Linux/Mac
cp .env.example .env  # edit with your values

# Frontend
cd ../frontend
npm install  # or: bun install

# Run both (Windows)
cd ..
.\start.ps1

# Or manually:
# Terminal 1: cd backend && venv\Scripts\uvicorn main:app --reload --port 8000
# Terminal 2: cd frontend && npm run dev
```

Open `http://localhost:3000` — login with `admin` / `admin`.

## Docker

```bash
# Single container (frontend + backend + nginx)
docker build -t gsdm-r .
docker run -d -p 3000:80 -v gsdm-data:/app/data --env-file backend/.env --name gsdm-r gsdm-r

# Or with docker-compose
docker compose up --build
```

## Configuration

All config via environment variables (or `backend/.env`):

| Variable | Default | Description |
|----------|---------|-------------|
| `DB_PATH` | `router.db` | SQLite database path |
| `JWT_SECRET` | `change-this-...` | JWT signing secret |
| `JWT_EXPIRATION_HOURS` | `24` | Token expiry |
| `DEFAULT_ADMIN_USERNAME` | `admin` | Initial admin user |
| `DEFAULT_ADMIN_PASSWORD` | `admin` | Initial admin password |
| `DEFAULT_API_KEY` | `sk-gsdm-default-...` | Initial router API key |

## API Endpoints

### Proxy (requires API key)

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/v1/chat/completions` | OpenAI Chat Completions |
| `POST` | `/v1/messages` | Anthropic Messages |
| `POST` | `/v1/responses` | OpenAI Responses API |
| `GET` | `/v1/models` | List available models |

### Management (requires JWT from login)

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/auth/login` | Login, get JWT |
| `GET` | `/api/providers` | List providers |
| `POST` | `/api/providers` | Add provider |
| `PUT` | `/api/providers/{id}` | Update provider |
| `DELETE` | `/api/providers/{id}` | Delete provider |
| `GET` | `/api/providers/{id}/models` | Fetch models from provider |
| `GET` | `/api/providers/health-status` | Provider health state |
| `GET` | `/api/models` | List models |
| `POST` | `/api/models` | Create model (with aliases) |
| `PUT` | `/api/models/{id}` | Update model |
| `DELETE` | `/api/models/{id}` | Delete model |
| `GET` | `/api/keys` | List API keys |
| `POST` | `/api/keys` | Generate API key |
| `PUT` | `/api/keys/{id}` | Update key |
| `DELETE` | `/api/keys/{id}` | Delete key |
| `GET` | `/api/usage` | Usage statistics |
| `GET` | `/api/backup/export` | Export config as JSON |
| `POST` | `/api/backup/import` | Import config from JSON |
| `GET` | `/api/status` | Public status page data (no auth) |
| `GET` | `/health` | Health check (no auth) |

### Authentication

```bash
# Proxy endpoints — use API key
curl -H "Authorization: Bearer sk-gsdm-your-key" \
  http://localhost:8000/v1/chat/completions \
  -d '{"model": "deepseek-v4-flash", "messages": [{"role": "user", "content": "hi"}]}'

# Management endpoints — use JWT
TOKEN=$(curl -s -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin"}' | jq -r .access_token)

curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/providers
```

## Features

### Load Balancing

Each model can be configured with one of three modes:

- **Priority** — always tries highest priority provider first, falls back in order
- **Round Robin** — rotates starting provider across requests
- **Weighted Random** — randomly selects based on priority weights, falls back to rest

### Rate Limiting

- Per-key configurable rate limits (default: 60 req/min)
- Sliding window algorithm
- Returns `429` with `Retry-After` header when exceeded
- Response headers: `X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset`

### Provider Health Checks

- Background task pings each provider every 60 seconds
- Auto-disables provider after 3 consecutive failures
- Auto-re-enables on recovery (checked every 5 minutes)
- View health status: `GET /api/providers/health-status`

### Model Aliases

A model can have multiple aliases that all route to the same provider configuration:

```json
{
  "name": "deepseek-v4-flash",
  "aliases": ["gpt4", "gpt-4-latest", "best-model"],
  "providers": [...]
}
```

Clients can use any alias name in their requests.

### API Key Restrictions

Each API key can optionally be restricted to specific models. Keys with no model restrictions can access all models.

### Export / Import

Back up and restore your entire configuration (providers, models, API keys):

```bash
# Export (requires password confirmation)
curl -H "Authorization: Bearer $TOKEN" "http://localhost:8000/api/backup/export?password=admin" > backup.json

# Import to another instance
curl -H "Authorization: Bearer $TOKEN" -F "file=@backup.json" \
  http://localhost:8000/api/backup/import
```

### Status Page

Public health dashboard at `/status` (no auth required):
- Gatus-style grid with uptime bars per provider
- Hover tooltips showing timestamp, latency, status
- Filter by health, sort by name/latency/uptime
- Configurable auto-refresh (10s to 10m)
- Provider health history stored in DB

## Error Format

All errors follow a consistent format:

```json
{
  "error": {
    "message": "Description of what went wrong",
    "type": "error_type",
    "code": 400
  }
}
```

## Swagger Docs

Available at `http://localhost:8000/docs` (shows public proxy endpoints only).

## Tech Stack

- **Backend:** Python, FastAPI, aiosqlite, httpx, PyJWT, bcrypt
- **Frontend:** React, TypeScript, Vite, Tailwind CSS, shadcn/ui, TanStack Query, Recharts
- **Database:** SQLite with WAL mode
- **Deployment:** Docker (single container with nginx)

## License

MIT

