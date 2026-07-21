# Implementation Plan: AI API Router

## Overview

Build a FastAPI backend that proxies OpenAI/Anthropic-format requests to multiple providers with priority-based fallback, paired with a React (Vite) dashboard for CRUD management of providers and models. SQLite with aiosqlite provides storage. Implementation proceeds backend-first (database, auth, CRUD, routing logic) then frontend (auth, providers, models).

## Tasks

- [x] 1. Set up backend project structure and database
  - [x] 1.1 Initialize backend project with FastAPI and dependencies
    - Create `backend/` directory with `main.py`, `config.py`, `requirements.txt`
    - Install dependencies: fastapi, uvicorn, aiosqlite, httpx, pyjwt, bcrypt, pydantic
    - Set up FastAPI app with CORS middleware in `main.py`
    - Create `config.py` with settings (DB path, JWT secret, default admin credentials)
    - _Requirements: 1.1, 1.2_

  - [x] 1.2 Implement database schema and seed data
    - Create `backend/database.py` with async SQLite connection management
    - Implement schema creation (providers, models, model_providers, users, api_keys tables)
    - Implement seed data insertion (4 default providers, default admin user, default API key)
    - Wire database initialization to app startup event
    - _Requirements: 7.1, 7.2_

  - [x] 1.3 Define Pydantic models
    - Create `backend/models/provider.py` with ProviderCreate, ProviderUpdate, ProviderResponse
    - Create `backend/models/model.py` with ModelCreate, ModelUpdate, ModelResponse, ModelProviderMapping
    - Create `backend/models/user.py` with LoginRequest, TokenResponse
    - _Requirements: 4.2, 4.3, 5.2, 5.3_

- [x] 2. Implement backend authentication
  - [x] 2.1 Implement API key authentication middleware
    - Create `backend/middleware/api_key.py`
    - Extract API key from Authorization Bearer header or x-api-key header
    - Validate key against active keys in api_keys table
    - Return 401 if missing or invalid
    - _Requirements: 3.1, 3.2, 3.3_

  - [x] 2.2 Implement dashboard JWT authentication
    - Create `backend/services/auth.py` with password hashing (bcrypt) and JWT creation/verification
    - Create `backend/routers/auth.py` with login, logout, and /me endpoints
    - Login validates credentials, returns JWT token
    - Protected routes verify JWT and return 401 on invalid/missing token
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5_

  - [ ]* 2.3 Write property tests for authentication
    - **Property 6: Authentication gate** — verify requests without valid API key get 401, requests with valid key proceed
    - **Property 13: Unauthenticated dashboard requests rejected** — verify management routes return 401 without JWT
    - **Property 14: Invalid credentials rejected** — verify wrong password returns error without creating session
    - **Validates: Requirements 3.1, 3.2, 6.3, 6.5**

- [x] 3. Implement Provider CRUD API
  - [x] 3.1 Create provider CRUD endpoints
    - Create `backend/routers/providers.py` with GET, POST, PUT, DELETE endpoints
    - Implement list all providers (masked API keys)
    - Implement create provider with validation (non-empty name, base_url)
    - Implement update provider (partial update support)
    - Implement delete provider with cascade to model_providers
    - Protect all endpoints with JWT authentication
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 8.1, 8.3_

  - [x] 3.2 Implement API key masking utility
    - Create mask function showing only last 4 characters
    - Apply masking in all provider list/detail responses
    - _Requirements: 8.3_

  - [ ]* 3.3 Write property tests for provider CRUD
    - **Property 7: Provider CRUD round-trip** — create then read back returns same data with masked key
    - **Property 8: Delete provider cascades to model mappings** — verify cascade deletion
    - **Property 9: Provider validation rejects empty fields** — verify empty name/base_url rejected
    - **Property 16: API key masked in dashboard responses** — verify masking algorithm
    - **Validates: Requirements 4.2, 4.3, 4.4, 4.5, 8.3**

- [x] 4. Implement Model CRUD API
  - [x] 4.1 Create model CRUD endpoints
    - Create `backend/routers/models.py` with GET, POST, PUT, DELETE endpoints
    - Implement list all models with provider mappings and priorities
    - Implement create model with at least one provider mapping and unique priorities
    - Implement update model (name, add/remove/reorder provider mappings)
    - Implement delete model with cascade to model_providers
    - Protect all endpoints with JWT authentication
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5_

  - [ ]* 4.2 Write property tests for model CRUD
    - **Property 10: Model CRUD round-trip** — create then read back returns same name and mappings
    - **Property 11: Delete model cascades to mappings** — verify cascade deletion
    - **Property 12: Model validation enforces constraints** — verify zero mappings and duplicate priorities rejected
    - **Validates: Requirements 5.2, 5.3, 5.4, 5.5**

- [x] 5. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 6. Implement priority-based routing and proxy
  - [x] 6.1 Implement routing service
    - Create `backend/services/routing.py`
    - Query model_providers table ordered by priority ASC for given model name
    - Implement fallback loop: attempt each provider in order, skip on failure
    - Track attempted providers to enforce at-most-once
    - Return 503 if all providers exhausted
    - _Requirements: 2.1, 2.2, 2.3, 2.4_

  - [x] 6.2 Implement proxy client for request forwarding
    - Create `backend/services/proxy_client.py`
    - Forward request body and construct outgoing headers with provider API key
    - Handle 30-second timeout
    - Classify responses: 2xx success, 429/5xx trigger fallback, other 4xx return as-is
    - Log failures with provider name, error type, and timestamp
    - _Requirements: 8.2, 9.1, 9.2, 9.3, 9.4_

  - [x] 6.3 Implement OpenAI-compatible proxy endpoint
    - Create `backend/routers/proxy.py` with POST `/v1/chat/completions`
    - Parse request body, extract model name
    - Call routing service with fallback chain
    - Support streaming (SSE passthrough) and non-streaming responses
    - Preserve all request parameters when forwarding
    - _Requirements: 1.1, 1.3, 1.4_

  - [x] 6.4 Implement Anthropic-compatible proxy endpoint
    - Add POST `/v1/messages` endpoint to proxy router
    - Parse Anthropic-format request, extract model name
    - Call routing service with fallback chain
    - Support streaming and non-streaming responses
    - Return response in Anthropic format
    - _Requirements: 1.2, 1.3, 1.4_

  - [x] 6.5 Implement OpenAI Responses API proxy endpoint
    - Add POST `/v1/responses` endpoint to proxy router
    - Parse Responses API request body (uses `input` field instead of `messages`, `model` field)
    - Support parameters: temperature, max_output_tokens, top_p, instructions, tools, tool_choice, stream
    - Call routing service with fallback chain
    - Support streaming (SSE events) and non-streaming responses
    - Return response in OpenAI Responses API format (with `output` array)
    - Preserve all request parameters when forwarding
    - _Requirements: 1.5, 1.6, 1.4_

  - [ ]* 6.6 Write property tests for routing logic
    - **Property 1: Request forwarding preserves format and parameters** — verify OpenAI, Responses API, and Anthropic formats preserved
    - **Property 2: Highest-priority provider selected first** — verify lowest priority number attempted first
    - **Property 3: Failure triggers fallback to next provider** — verify 429/5xx/timeout triggers next
    - **Property 4: All providers failing returns 503** — verify exhaustion returns 503
    - **Property 5: Each provider attempted at most once** — verify no duplicate attempts
    - **Property 15: Provider API key included in forwarded requests** — verify outgoing auth header
    - **Property 17: Failure logging contains required fields** — verify log entries
    - **Validates: Requirements 1.1, 1.2, 1.5, 1.6, 2.1, 2.2, 2.3, 2.4, 8.2, 9.1, 9.2, 9.3, 9.4**

- [x] 7. Checkpoint - Backend complete, ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 8. Set up frontend project structure
  - [-] 8.1 Initialize React + Vite + TypeScript project
    - Create `frontend/` directory with Vite React-TS template
    - Install dependencies: react-router-dom, axios
    - Configure Vite proxy to backend API for development
    - Define TypeScript types in `src/types/index.ts` (Provider, Model, ModelProviderMapping)
    - Create Axios API client with JWT interceptor in `src/api/client.ts`
    - _Requirements: 4.1, 5.1, 6.1_

- [ ] 9. Implement frontend authentication
  - [ ] 9.1 Implement login page and auth context
    - Create `src/hooks/useAuth.ts` with AuthContext (token, login, logout)
    - Create `src/pages/LoginPage.tsx` with username/password form
    - Handle login API call, store JWT token
    - Display error message on invalid credentials
    - Create `src/components/ProtectedRoute.tsx` to redirect unauthenticated users
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5_

- [ ] 10. Implement provider management UI
  - [ ] 10.1 Build provider list and CRUD forms
    - Create `src/pages/ProvidersPage.tsx` with provider listing table
    - Display name, base URL, masked API key, and active status for each provider
    - Create `src/components/providers/ProviderForm.tsx` for add/edit
    - Implement create, update, and delete operations
    - Add client-side validation (non-empty name, base_url)
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 8.3_

- [ ] 11. Implement model management UI
  - [ ] 11.1 Build model list and CRUD forms
    - Create `src/pages/ModelsPage.tsx` with model listing
    - Display model name and provider mappings with priorities
    - Create `src/components/models/ModelForm.tsx` for add/edit with dynamic provider mapping rows
    - Implement create, update, and delete operations
    - Enforce at least one provider mapping with unique priorities
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5_

- [ ] 12. Wire frontend together
  - [ ] 12.1 Set up app layout and routing
    - Create `src/components/Layout.tsx` with navigation (Providers, Models, Logout)
    - Configure React Router with protected routes
    - Wire all pages into `src/App.tsx`
    - Ensure logout invalidates session and redirects to login
    - _Requirements: 6.4, 6.5_

- [ ] 13. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document
- Backend is implemented first to provide stable APIs before frontend development
- The 4 default providers (bluesminds, freemodel, forge-gateway, iamhc) are seeded on first startup
- Default admin credentials are admin/admin — should be changed after first login

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["1.2", "1.3"] },
    { "id": 2, "tasks": ["2.1", "2.2"] },
    { "id": 3, "tasks": ["2.3", "3.1", "3.2"] },
    { "id": 4, "tasks": ["3.3", "4.1"] },
    { "id": 5, "tasks": ["4.2", "6.1"] },
    { "id": 6, "tasks": ["6.2"] },
    { "id": 7, "tasks": ["6.3", "6.4", "6.5"] },
    { "id": 8, "tasks": ["6.6", "8.1"] },
    { "id": 9, "tasks": ["9.1"] },
    { "id": 10, "tasks": ["10.1"] },
    { "id": 11, "tasks": ["11.1"] },
    { "id": 12, "tasks": ["12.1"] }
  ]
}
```
