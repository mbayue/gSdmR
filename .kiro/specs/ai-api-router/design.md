# Design Document

## Introduction

This document describes the architecture and design of the AI API Router system — a FastAPI backend that proxies OpenAI/Anthropic-format requests to multiple backend providers with priority-based fallback, paired with a React (Vite) dashboard for CRUD management. Storage uses SQLite for simplicity.

## Architecture Overview

The system consists of two main components:

1. **Router Backend** (FastAPI + Python) — Accepts incoming API requests, authenticates them, resolves the target model to providers by priority, and forwards requests with fallback logic.
2. **Dashboard Frontend** (React + Vite) — Provides a web UI for managing providers, models, and their priority mappings. Protected by username/password authentication.

```
┌─────────────────┐       ┌──────────────────────────────────────┐
│   API Clients   │──────▶│         FastAPI Router Backend        │
│ (OpenAI/Claude  │◀──────│                                      │
│   SDK format)   │       │  ┌──────────┐  ┌─────────────────┐  │
└─────────────────┘       │  │ Auth     │  │ Priority Router  │  │
                          │  │ Middleware│  │ (fallback chain) │  │
                          │  └──────────┘  └────────┬────────┘  │
                          │                         │            │
                          │  ┌──────────────────────▼─────────┐  │
                          │  │        Provider Clients         │  │
                          │  │ (httpx async, per-provider key) │  │
                          │  └──────────────────────────────────┘ │
                          │                                      │
                          │  ┌──────────────────────────────────┐ │
                          │  │  SQLite Database (providers,     │ │
                          │  │  models, model_providers, users) │ │
                          │  └──────────────────────────────────┘ │
                          └──────────────────────────────────────┘
                                           ▲
                          ┌────────────────┘
                          │
┌─────────────────┐       │
│   Dashboard     │───────┘
│   (React/Vite)  │  (REST API for CRUD + auth)
└─────────────────┘
```

## Components

### Backend (FastAPI)

#### Module Structure

```
backend/
├── main.py                 # FastAPI app entrypoint, CORS, startup
├── config.py               # Settings (DB path, default admin, API keys)
├── database.py             # SQLite connection, schema init, seed data
├── models/
│   ├── __init__.py
│   ├── provider.py         # Provider SQLAlchemy/Pydantic models
│   ├── model.py            # Model + ModelProvider mapping models
│   └── user.py             # User model for dashboard auth
├── routers/
│   ├── __init__.py
│   ├── proxy.py            # OpenAI + Anthropic proxy endpoints
│   ├── providers.py        # Provider CRUD API
│   ├── models.py           # Model CRUD API
│   └── auth.py             # Dashboard login/logout/session
├── services/
│   ├── __init__.py
│   ├── routing.py          # Priority-based provider resolution + fallback
│   ├── proxy_client.py     # httpx async client for forwarding requests
│   └── auth.py             # API key validation, password hashing
├── middleware/
│   ├── __init__.py
│   └── api_key.py          # API key authentication middleware
└── requirements.txt
```

#### Key Design Decisions

- **httpx** for async HTTP forwarding (supports streaming SSE passthrough)
- **SQLite** via `aiosqlite` for async database access
- **Pydantic** models for request/response validation
- **JWT tokens** for dashboard session management (stateless, simple)
- **bcrypt** for password hashing

### Frontend (React + Vite)

#### Module Structure

```
frontend/
├── index.html
├── package.json
├── vite.config.ts
├── src/
│   ├── main.tsx
│   ├── App.tsx
│   ├── api/
│   │   └── client.ts       # Axios instance with auth interceptor
│   ├── components/
│   │   ├── Layout.tsx       # App shell with nav
│   │   ├── ProtectedRoute.tsx
│   │   ├── providers/
│   │   │   ├── ProviderList.tsx
│   │   │   └── ProviderForm.tsx
│   │   └── models/
│   │       ├── ModelList.tsx
│   │       └── ModelForm.tsx
│   ├── pages/
│   │   ├── LoginPage.tsx
│   │   ├── ProvidersPage.tsx
│   │   └── ModelsPage.tsx
│   ├── hooks/
│   │   └── useAuth.ts
│   └── types/
│       └── index.ts
└── tsconfig.json
```

#### Key Design Decisions

- **React Router** for client-side routing with protected routes
- **Axios** for API calls with JWT token in headers
- **Simple CSS** (or Tailwind) — no heavy component library needed for a basic dashboard
- **Context API** for auth state management (small app, no Redux needed)

## Data Models

### SQLite Schema

```sql
CREATE TABLE providers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    base_url TEXT NOT NULL,
    api_key TEXT NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE models (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE model_providers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    model_id INTEGER NOT NULL,
    provider_id INTEGER NOT NULL,
    priority INTEGER NOT NULL,
    FOREIGN KEY (model_id) REFERENCES models(id) ON DELETE CASCADE,
    FOREIGN KEY (provider_id) REFERENCES providers(id) ON DELETE CASCADE,
    UNIQUE(model_id, provider_id),
    UNIQUE(model_id, priority)
);

CREATE TABLE users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE api_keys (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    key_value TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
```

### Pydantic Models

```python
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


class ProviderCreate(BaseModel):
    name: str = Field(..., min_length=1)
    base_url: str = Field(..., min_length=1)
    api_key: str = Field(..., min_length=1)


class ProviderUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1)
    base_url: Optional[str] = Field(None, min_length=1)
    api_key: Optional[str] = None
    is_active: Optional[bool] = None


class ProviderResponse(BaseModel):
    id: int
    name: str
    base_url: str
    api_key_masked: str  # e.g., "****abcd"
    is_active: bool
    created_at: datetime
    updated_at: datetime


class ModelProviderMapping(BaseModel):
    provider_id: int
    priority: int = Field(..., ge=1)


class ModelCreate(BaseModel):
    name: str = Field(..., min_length=1)
    providers: List[ModelProviderMapping] = Field(..., min_length=1)


class ModelUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1)
    providers: Optional[List[ModelProviderMapping]] = None


class ModelResponse(BaseModel):
    id: int
    name: str
    providers: List[dict]  # [{provider_id, provider_name, priority}]
    created_at: datetime
    updated_at: datetime


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
```

## Interfaces

### Router Proxy Endpoints

```python
# OpenAI-compatible endpoint
@router.post("/v1/chat/completions")
async def openai_chat_completions(request: Request):
    """
    Accepts OpenAI chat completion format.
    Authenticates via API key, resolves model to providers,
    forwards with priority-based fallback.
    """
    pass

# OpenAI Responses API endpoint
@router.post("/v1/responses")
async def openai_responses(request: Request):
    """
    Accepts OpenAI Responses API format.
    Request uses `input` field (string or array of items) and `model` field.
    Supports parameters: temperature, max_output_tokens, top_p, instructions,
    tools, tool_choice, stream.
    Authenticates via API key, resolves model to providers,
    forwards with priority-based fallback.
    Response format includes an `output` array with message items.
    Streaming returns SSE events when stream=true.
    """
    pass

# Anthropic-compatible endpoint
@router.post("/v1/messages")
async def anthropic_messages(request: Request):
    """
    Accepts Anthropic messages format.
    Authenticates via API key, resolves model to providers,
    forwards with priority-based fallback.
    """
    pass
```

### Provider CRUD Endpoints

```python
@router.get("/api/providers") -> List[ProviderResponse]
@router.post("/api/providers") -> ProviderResponse  # body: ProviderCreate
@router.put("/api/providers/{id}") -> ProviderResponse  # body: ProviderUpdate
@router.delete("/api/providers/{id}") -> {"message": "deleted"}
```

### Model CRUD Endpoints

```python
@router.get("/api/models") -> List[ModelResponse]
@router.post("/api/models") -> ModelResponse  # body: ModelCreate
@router.put("/api/models/{id}") -> ModelResponse  # body: ModelUpdate
@router.delete("/api/models/{id}") -> {"message": "deleted"}
```

### Dashboard Auth Endpoints

```python
@router.post("/api/auth/login") -> TokenResponse  # body: LoginRequest
@router.post("/api/auth/logout") -> {"message": "logged out"}
@router.get("/api/auth/me") -> {"username": str}  # validates current token
```

## Routing Logic

### Priority-Based Fallback Algorithm

```python
async def route_request(model_name: str, request_body: dict, headers: dict) -> Response:
    """
    1. Look up model_name in the models table
    2. Get all provider mappings ordered by priority ASC (lowest = highest priority)
    3. For each provider in order:
       a. Build the outgoing request (provider base_url + endpoint, provider API key)
       b. Forward the request with a 30-second timeout
       c. If response is 2xx: return it to the client
       d. If response is 429 or 5xx or timeout: log failure, continue to next
    4. If all providers exhausted: return 503 error
    """
    providers = get_providers_for_model(model_name)  # ordered by priority
    
    attempted = set()
    for provider in providers:
        if provider.id in attempted:
            continue
        attempted.add(provider.id)
        
        try:
            response = await forward_to_provider(provider, request_body, headers, timeout=30)
            if 200 <= response.status_code < 300:
                return response
            if response.status_code in (429,) or response.status_code >= 500:
                log_failure(provider.name, f"HTTP {response.status_code}", datetime.now())
                continue
            # Other 4xx errors (except 429) are client errors, return as-is
            return response
        except httpx.TimeoutException:
            log_failure(provider.name, "timeout", datetime.now())
            continue
        except httpx.RequestError as e:
            log_failure(provider.name, str(e), datetime.now())
            continue
    
    return JSONResponse(status_code=503, content={
        "error": {"message": "All providers failed", "type": "service_unavailable"}
    })
```

### Streaming Support

```python
async def forward_streaming(provider, request_body, headers):
    """
    Uses httpx streaming to forward SSE responses chunk by chunk.
    Returns a StreamingResponse that yields chunks as received.
    """
    async def event_generator():
        async with httpx.AsyncClient() as client:
            async with client.stream(
                "POST", url, json=request_body, headers=outgoing_headers, timeout=30
            ) as response:
                async for chunk in response.aiter_bytes():
                    yield chunk
    
    return StreamingResponse(event_generator(), media_type="text/event-stream")
```

## Authentication

### Router API Key Authentication

```python
async def validate_api_key(request: Request) -> bool:
    """
    Checks for API key in:
    1. Authorization: Bearer <key>
    2. x-api-key: <key>
    
    Validates against active keys in the api_keys table.
    Returns True if valid, raises 401 otherwise.
    """
    key = extract_key_from_headers(request.headers)
    if not key:
        raise HTTPException(status_code=401, detail="API key required")
    
    is_valid = await check_key_in_db(key)
    if not is_valid:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return True
```

### Dashboard JWT Authentication

```python
def create_access_token(username: str) -> str:
    """Creates a JWT with username claim and expiration."""
    payload = {"sub": username, "exp": datetime.utcnow() + timedelta(hours=24)}
    return jwt.encode(payload, SECRET_KEY, algorithm="HS256")

def verify_token(token: str) -> str:
    """Verifies JWT and returns username. Raises 401 on failure."""
    payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
    return payload["sub"]
```

## Error Handling

### Provider Failure Handling

| Condition | Action |
|-----------|--------|
| HTTP 429 | Log failure, try next provider |
| HTTP 5xx | Log failure, try next provider |
| Timeout (>30s) | Log failure, try next provider |
| Connection error | Log failure, try next provider |
| HTTP 4xx (not 429) | Return error to client as-is |
| All providers exhausted | Return 503 to client |

### Failure Log Entry

```python
@dataclass
class FailureLogEntry:
    provider_name: str
    error_type: str  # "timeout", "http_429", "http_5xx", "connection_error"
    timestamp: datetime
    model_name: str
    request_id: str
```

Failures are logged via Python's standard `logging` module at WARNING level.

### API Error Response Format

```python
# OpenAI-compatible error format
{
    "error": {
        "message": "All providers for model 'gpt-4' are unavailable",
        "type": "service_unavailable",
        "code": 503
    }
}
```

## API Key Masking

```python
def mask_api_key(key: str) -> str:
    """
    Shows only the last 4 characters, masks the rest with asterisks.
    For keys shorter than 5 chars, mask all but last char.
    """
    if len(key) <= 4:
        return "*" * (len(key) - 1) + key[-1:]
    return "*" * (len(key) - 4) + key[-4:]
```

## Initial Seed Data

On first startup, the database is seeded with:

```python
DEFAULT_PROVIDERS = [
    {"name": "bluesminds", "base_url": "https://api.bluesminds.com/v1/", "api_key": ""},
    {"name": "freemodel", "base_url": "https://api.freemodel.dev/v1/", "api_key": ""},
    {"name": "forge-gateway", "base_url": "https://forge-gateway-api.fly.dev/v1/", "api_key": ""},
    {"name": "iamhc", "base_url": "https://api.iamhc.cn/v1/", "api_key": ""},
]

DEFAULT_ADMIN = {"username": "admin", "password": "admin"}  # Change on first login
```

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system — essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### Property 1: Request forwarding preserves format and parameters

*For any* valid OpenAI-format, OpenAI Responses API-format, or Anthropic-format request containing any combination of parameters (model, messages/input, temperature, max_tokens/max_output_tokens, instructions, tools, tool_choice), the Router SHALL forward all parameters unchanged to the provider and return the response in the same API format as the original request.

**Validates: Requirements 1.1, 1.2, 1.3, 1.5, 1.6**

### Property 2: Highest-priority provider selected first

*For any* model with N provider mappings at distinct priorities, the Router SHALL attempt the provider with the lowest priority number first.

**Validates: Requirements 2.1**

### Property 3: Failure triggers fallback to next provider

*For any* model with multiple providers, when a provider returns HTTP 429, HTTP 5xx, or times out, the Router SHALL attempt the next provider in ascending priority order.

**Validates: Requirements 2.2, 9.2, 9.3**

### Property 4: All providers failing returns 503

*For any* model where every mapped provider fails (429, 5xx, or timeout), the Router SHALL return HTTP 503 with a descriptive error message.

**Validates: Requirements 2.3**

### Property 5: Each provider attempted at most once

*For any* request, regardless of the number of failures encountered, no provider SHALL be called more than once during the fallback chain.

**Validates: Requirements 2.4**

### Property 6: Authentication gate

*For any* request to a proxied endpoint, the request SHALL be processed if and only if it contains a valid API key in either the Authorization Bearer header or the x-api-key header; otherwise, the Router SHALL return HTTP 401.

**Validates: Requirements 3.1, 3.2**

### Property 7: Provider CRUD round-trip

*For any* valid provider data (non-empty name, non-empty base URL, non-empty API key), creating a provider and then reading it back SHALL return the same name, base URL, and a masked version of the API key. Updating any field and reading back SHALL reflect the updated value.

**Validates: Requirements 4.2, 4.3**

### Property 8: Delete provider cascades to model mappings

*For any* provider that is mapped to one or more models, deleting that provider SHALL remove the provider record and all associated entries in the model_providers table.

**Validates: Requirements 4.4**

### Property 9: Provider validation rejects empty fields

*For any* provider creation or update request where the name or base_url is empty or whitespace-only, the system SHALL reject the request with a validation error.

**Validates: Requirements 4.5**

### Property 10: Model CRUD round-trip

*For any* valid model data (non-empty name, at least one provider mapping with unique priorities), creating a model and then reading it back SHALL return the same name and provider mappings with correct priorities.

**Validates: Requirements 5.2, 5.3**

### Property 11: Delete model cascades to mappings

*For any* model with provider mappings, deleting the model SHALL remove both the model record and all its entries in the model_providers table.

**Validates: Requirements 5.4**

### Property 12: Model validation enforces constraints

*For any* model creation or update request, the system SHALL reject submissions with zero provider mappings or with duplicate priority values for the same model.

**Validates: Requirements 5.5**

### Property 13: Unauthenticated dashboard requests redirect to login

*For any* management API route, a request without a valid JWT token SHALL be rejected with HTTP 401 (triggering the frontend to redirect to the login page).

**Validates: Requirements 6.5**

### Property 14: Invalid credentials rejected

*For any* login attempt with a username or password that does not match stored credentials, the system SHALL return an authentication error without creating a session.

**Validates: Requirements 6.3**

### Property 15: Provider API key included in forwarded requests

*For any* provider with a configured API key, when the Router forwards a request to that provider, the outgoing request SHALL include the provider's API key in the Authorization header.

**Validates: Requirements 8.2**

### Property 16: API key masked in dashboard responses

*For any* API key of length N (where N >= 4), the dashboard API SHALL return a masked string showing only the last 4 characters with the rest replaced by asterisks. For keys shorter than 4 characters, all but the last character SHALL be masked.

**Validates: Requirements 8.3**

### Property 17: Failure logging contains required fields

*For any* Provider_Failure event (timeout, 429, 5xx, connection error), the Router SHALL produce a log entry containing the provider name, error type classification, and ISO-format timestamp.

**Validates: Requirements 9.4**
