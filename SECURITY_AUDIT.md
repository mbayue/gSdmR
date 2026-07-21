# Security Audit — gSdm-R

**Date:** 2026-07-21
**Scope:** Full backend source code review

---

## Critical

- [x] **#1** Default JWT secret is predictable (`config.py:16`)
  - Default `"change-this-secret-in-production"` allows token forgery if env var not set
  - Fix: Generates random ephemeral secret if not set, prints warning

- [x] **#2** Hardcoded provider API keys in source (`database.py:89-94`)
  - Real third-party keys committed in DEFAULT_PROVIDERS
  - Fix: Seeded with empty keys, admins configure via dashboard/import

- [x] **#3** Default admin credentials admin/admin (`config.py:20-21`)
  - Combined with #1, gives full admin access with zero effort
  - Fix: Generates random password if not set, prints to console

---

## High

- [x] **#4** CORS allows all origins with credentials (`main.py:79-84`)
  - `allow_origins=["*"]` + `allow_credentials=True` is insecure
  - Fix: Set allow_credentials=False (Bearer tokens don't need it)

- [x] **#5** TLS verification disabled on provider connections (`proxy_client.py:77,109`, `providers.py:119`)
  - `verify=False` enables MITM attacks
  - Fix: Removed verify=False (default True now)

- [x] **#6** SQL f-string in usage router (`usage.py:29`)
  - `days` interpolated via f-string into SQL
  - Fix: Changed to parameterized query with ?

- [x] **#7** Backup export exposes all API keys in cleartext (`backup.py:26-36`)
  - Admin JWT gives access to all provider secrets
  - Fix: Added password re-confirmation required for export

- [x] **#8** No JWT token revocation — logout is no-op (`auth.py:26-28`)
  - Compromised tokens valid for full 24h
  - Fix: Added in-memory token blocklist, logout revokes token

---

## Medium

- [x] **#9** Rate limiter memory grows unbounded (`rate_limit.py`)
  - `_windows` dict never pruned
  - Fix: Added eviction when >10k keys, removes entries stale >2x window

- [x] **#10** Request body parsed twice (`proxy.py:98-100`)
  - Pydantic + request.json() could diverge
  - Fix: Use body_schema.model_dump() only

- [x] **#11** No request body size limit (`proxy.py`)
  - Large payloads can exhaust memory
  - Fix: Added MaxBodySizeMiddleware (10MB limit, returns 413)

- [x] **#12** Health check re-enables manually disabled providers (`health.py:82-88`)
  - No distinction between admin-disabled and auto-disabled
  - Fix: Added `auto_disabled` column, only re-enables auto-disabled providers

- [x] **#13** Timing-based username enumeration (`auth.py:14-19`)
  - Missing user skips bcrypt, response is faster
  - Fix: Always run bcrypt against dummy hash when user not found

- [x] **#14** No brute-force protection on login (`auth.py:12-21`)
  - No rate limiting on login endpoint
  - Fix: Added per-IP rate limit (5 attempts/min) on login

- [x] **#15** Import file read with no size limit (`backup.py:68`)
  - Large uploads can OOM
  - Fix: Capped to 5MB, returns 413 if exceeded

---

## Low

- [x] **#16** X-Request-ID trusted from client (`security.py:22`)
  - Could inject misleading IDs into logs
  - Fix: Validate alphanumeric + dashes, max 64 chars, otherwise generate new

- [x] **#17** Round-robin state not synchronized (`routing.py:10`)
  - Dict modified without lock under concurrency
  - Fix: Added asyncio.Lock around read-modify-write

- [x] **#18** Provider model fetch disables TLS (`providers.py:119`)
  - Same as #5, specific to model list endpoint
  - Fix: Already fixed by #5 (removed all verify=False)
