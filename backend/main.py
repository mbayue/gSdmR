"""FastAPI application entrypoint."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: initialize database on startup."""
    from database import init_db

    await init_db()
    yield


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

# CORS middleware — allow all origins for development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


from routers.auth import router as auth_router
from routers.providers import router as providers_router
from routers.models import router as models_router
from routers.proxy import router as proxy_router
from routers.api_keys import router as api_keys_router
from routers.backup import router as backup_router

app.include_router(proxy_router)
app.include_router(auth_router, include_in_schema=False)
app.include_router(providers_router, include_in_schema=False)
app.include_router(models_router, include_in_schema=False)
app.include_router(api_keys_router, include_in_schema=False)
app.include_router(backup_router, include_in_schema=False)


@app.get("/health", include_in_schema=False)
async def health_check():
    """Health check endpoint."""
    return {"status": "ok"}
