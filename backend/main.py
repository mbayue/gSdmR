"""FastAPI application entrypoint."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: initialize database on startup, close on shutdown."""
    from database import init_db, close_db
    from services.logging import setup_logging
    from services.health import start_health_checks, stop_health_checks

    setup_logging()
    await init_db()
    start_health_checks()
    yield
    stop_health_checks()
    await close_db()


app = FastAPI(
    title="gSdm-R",
    description="""
## OpenAI / Anthropic Compatible API Router

A proxy that routes requests to multiple backend providers with priority-based fallback.

### Supported Endpoints
- **POST /v1/chat/completions** — OpenAI Chat Completions format
- **POST /v1/messages** — Anthropic Messages format
- **POST /v1/responses** — OpenAI Responses API format
- **GET /v1/models** — List available models

### Authentication
All endpoints require an API key via `Authorization: Bearer <key>` or `x-api-key` header.
""",
    version="1.0.0",
    lifespan=lifespan,
    openapi_tags=[
        {"name": "proxy", "description": "AI model proxy endpoints (OpenAI/Anthropic compatible)"},
    ],
)


def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    openapi_schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
        tags=app.openapi_tags,
    )
    # Add security scheme for Bearer API key
    openapi_schema.setdefault("components", {})
    openapi_schema["components"]["securitySchemes"] = {
        "BearerAuth": {
            "type": "http",
            "scheme": "bearer",
            "description": "Enter your API key (e.g., sk-...)",
        },
    }
    # Apply security globally to all endpoints
    openapi_schema["security"] = [
        {"BearerAuth": []},
    ]
    app.openapi_schema = openapi_schema
    return openapi_schema


app.openapi = custom_openapi

# CORS middleware — allow all origins for development (no credentials needed with Bearer tokens)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Security headers middleware
from middleware.security import SecurityHeadersMiddleware
app.add_middleware(SecurityHeadersMiddleware)

# Request body size limit (10MB)
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request as StarletteRequest
from starlette.responses import Response as StarletteResponse

class MaxBodySizeMiddleware(BaseHTTPMiddleware):
    MAX_BODY_SIZE = 10 * 1024 * 1024  # 10MB

    async def dispatch(self, request: StarletteRequest, call_next) -> StarletteResponse:
        content_length = request.headers.get("content-length")
        if content_length and int(content_length) > self.MAX_BODY_SIZE:
            from fastapi.responses import JSONResponse
            return JSONResponse(
                status_code=413,
                content={"error": {"message": "Request body too large (max 10MB)", "type": "invalid_request_error", "code": 413}},
            )
        return await call_next(request)

app.add_middleware(MaxBodySizeMiddleware)


from routers.auth import router as auth_router
from routers.providers import router as providers_router
from routers.models import router as models_router
from routers.proxy import router as proxy_router
from routers.api_keys import router as api_keys_router
from routers.backup import router as backup_router
from routers.usage import router as usage_router
from routers.status import router as status_router

app.include_router(proxy_router)
app.include_router(status_router)
app.include_router(auth_router, include_in_schema=False)
app.include_router(providers_router, include_in_schema=False)
app.include_router(models_router, include_in_schema=False)
app.include_router(api_keys_router, include_in_schema=False)
app.include_router(backup_router, include_in_schema=False)
app.include_router(usage_router, include_in_schema=False)


@app.get("/health", include_in_schema=False)
async def health_check():
    """Health check endpoint."""
    return {"status": "ok"}


from fastapi import Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    """Return consistent error format for all HTTP errors."""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "message": exc.detail if isinstance(exc.detail, str) else str(exc.detail),
                "type": _error_type_for_status(exc.status_code),
                "code": exc.status_code,
            }
        },
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Return consistent error format for validation errors."""
    errors = exc.errors()
    message = "; ".join(
        f"{'.'.join(str(l) for l in e.get('loc', []))}: {e.get('msg', '')}"
        for e in errors
    )
    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "message": message,
                "type": "invalid_request_error",
                "code": 422,
            }
        },
    )


def _error_type_for_status(status_code: int) -> str:
    """Map HTTP status code to error type string."""
    if status_code == 401:
        return "authentication_error"
    if status_code == 403:
        return "permission_denied"
    if status_code == 404:
        return "not_found"
    if status_code == 409:
        return "conflict"
    if status_code == 422 or status_code == 400:
        return "invalid_request_error"
    if status_code == 429:
        return "rate_limit_error"
    if status_code >= 500:
        return "server_error"
    return "error"
