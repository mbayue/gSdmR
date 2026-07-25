"""Playground API routes: disabled models CRUD and direct/route testing."""

import time

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from database import get_db
from services.auth import get_current_user

router = APIRouter(prefix="/api/playground", tags=["playground"])


# --- Pydantic models ---


class DisabledModelRequest(BaseModel):
    provider_id: int
    model_name: str


class DisabledModelResponse(BaseModel):
    id: int
    provider_id: int
    provider_name: str
    model_name: str
    created_at: str


class TestRequest(BaseModel):
    provider_id: int
    model_name: str


class TestResponse(BaseModel):
    success: bool
    latency_ms: int
    response_text: str | None = None
    error: str | None = None
    provider_name: str
    model_name: str


# --- Disabled models CRUD ---


@router.get("/disabled-models", response_model=list[DisabledModelResponse])
async def list_disabled_models(username: str = Depends(get_current_user)):
    """List all disabled provider+model combinations."""
    db = await get_db()
    cursor = await db.execute(
        """
        SELECT dpm.id, dpm.provider_id, p.name as provider_name,
               dpm.model_name, dpm.created_at
        FROM disabled_provider_models dpm
        JOIN providers p ON p.id = dpm.provider_id
        ORDER BY p.name, dpm.model_name
        """
    )
    rows = await cursor.fetchall()
    return [
        DisabledModelResponse(
            id=row["id"],
            provider_id=row["provider_id"],
            provider_name=row["provider_name"],
            model_name=row["model_name"],
            created_at=row["created_at"],
        )
        for row in rows
    ]


@router.post("/disabled-models", response_model=DisabledModelResponse, status_code=201)
async def deactivate_model(
    body: DisabledModelRequest, username: str = Depends(get_current_user)
):
    """Deactivate a provider+model combination (skip during routing)."""
    db = await get_db()

    # Validate provider exists
    cursor = await db.execute(
        "SELECT id, name FROM providers WHERE id = ?", (body.provider_id,)
    )
    provider = await cursor.fetchone()
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")

    # Insert (idempotent — ignore if already exists)
    await db.execute(
        """
        INSERT OR IGNORE INTO disabled_provider_models (provider_id, model_name)
        VALUES (?, ?)
        """,
        (body.provider_id, body.model_name),
    )
    await db.commit()

    # Fetch the row (may have already existed)
    cursor = await db.execute(
        """
        SELECT id, provider_id, model_name, created_at
        FROM disabled_provider_models
        WHERE provider_id = ? AND model_name = ?
        """,
        (body.provider_id, body.model_name),
    )
    row = await cursor.fetchone()

    return DisabledModelResponse(
        id=row["id"],
        provider_id=row["provider_id"],
        provider_name=provider["name"],
        model_name=row["model_name"],
        created_at=row["created_at"],
    )


@router.delete("/disabled-models", status_code=200)
async def activate_model(
    body: DisabledModelRequest, username: str = Depends(get_current_user)
):
    """Re-activate a provider+model combination (include in routing again)."""
    db = await get_db()

    # Validate provider exists
    cursor = await db.execute(
        "SELECT id FROM providers WHERE id = ?", (body.provider_id,)
    )
    if not await cursor.fetchone():
        raise HTTPException(status_code=404, detail="Provider not found")

    # Delete the disabled entry
    cursor = await db.execute(
        """
        DELETE FROM disabled_provider_models
        WHERE provider_id = ? AND model_name = ?
        """,
        (body.provider_id, body.model_name),
    )
    await db.commit()

    if cursor.rowcount == 0:
        raise HTTPException(
            status_code=404, detail="Model is not currently deactivated"
        )

    return {"message": "Model re-activated successfully"}



# --- Direct test endpoint ---


@router.post("/test", response_model=TestResponse)
async def test_model(
    body: TestRequest, username: str = Depends(get_current_user)
):
    """Send a fixed prompt directly to a specific provider+model to test connectivity."""
    db = await get_db()

    # Lookup provider
    cursor = await db.execute(
        "SELECT id, name, base_url, api_key FROM providers WHERE id = ?",
        (body.provider_id,),
    )
    provider = await cursor.fetchone()
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")

    if not provider["api_key"]:
        return TestResponse(
            success=False,
            latency_ms=0,
            error="Provider API key not configured",
            provider_name=provider["name"],
            model_name=body.model_name,
        )

    # Build request
    request_body = {
        "model": body.model_name,
        "messages": [{"role": "user", "content": "Say hello in one word"}],
        "max_tokens": 50,
    }

    url = f"{provider['base_url'].rstrip('/')}/chat/completions"

    start = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                url,
                json=request_body,
                headers={
                    "Authorization": f"Bearer {provider['api_key']}",
                    "Content-Type": "application/json",
                },
            )
        latency_ms = int((time.perf_counter() - start) * 1000)

        if response.status_code == 200:
            data = response.json()
            text = None
            try:
                text = data["choices"][0]["message"]["content"]
            except (KeyError, IndexError, TypeError):
                text = str(data)[:200]

            return TestResponse(
                success=True,
                latency_ms=latency_ms,
                response_text=text,
                provider_name=provider["name"],
                model_name=body.model_name,
            )
        else:
            error_msg = f"HTTP {response.status_code}"
            try:
                err_data = response.json()
                if "error" in err_data:
                    if isinstance(err_data["error"], dict):
                        error_msg = err_data["error"].get("message", error_msg)
                    else:
                        error_msg = str(err_data["error"])
            except Exception:
                error_msg = f"HTTP {response.status_code}: {response.text[:200]}"

            return TestResponse(
                success=False,
                latency_ms=latency_ms,
                error=error_msg,
                provider_name=provider["name"],
                model_name=body.model_name,
            )

    except httpx.TimeoutException:
        latency_ms = int((time.perf_counter() - start) * 1000)
        return TestResponse(
            success=False,
            latency_ms=latency_ms,
            error="Request timed out (15s)",
            provider_name=provider["name"],
            model_name=body.model_name,
        )
    except httpx.RequestError as e:
        latency_ms = int((time.perf_counter() - start) * 1000)
        return TestResponse(
            success=False,
            latency_ms=latency_ms,
            error=f"Connection error: {str(e)}",
            provider_name=provider["name"],
            model_name=body.model_name,
        )



# --- Route test endpoint ---


class RouteTestRequest(BaseModel):
    model_name: str


@router.post("/route-test", response_model=TestResponse)
async def route_test(
    body: RouteTestRequest, username: str = Depends(get_current_user)
):
    """Test a configured model alias through the full routing logic."""
    from services.routing import route_request

    request_body = {
        "model": body.model_name,
        "messages": [{"role": "user", "content": "Say hello in one word"}],
        "max_tokens": 50,
    }

    start = time.perf_counter()
    try:
        result, provider_name = await route_request(
            model_name=body.model_name,
            request_body=request_body,
            endpoint_path="chat/completions",
            is_streaming=False,
        )
        latency_ms = int((time.perf_counter() - start) * 1000)

        # Parse the JSONResponse
        response_body = result.body.decode("utf-8")
        import json
        data = json.loads(response_body)

        if result.status_code == 200:
            text = None
            try:
                text = data["choices"][0]["message"]["content"]
            except (KeyError, IndexError, TypeError):
                text = str(data)[:200]

            return TestResponse(
                success=True,
                latency_ms=latency_ms,
                response_text=text,
                provider_name=provider_name or "unknown",
                model_name=body.model_name,
            )
        else:
            error_msg = "Request failed"
            if "error" in data:
                if isinstance(data["error"], dict):
                    error_msg = data["error"].get("message", error_msg)
                else:
                    error_msg = str(data["error"])

            return TestResponse(
                success=False,
                latency_ms=latency_ms,
                error=error_msg,
                provider_name=provider_name or "unknown",
                model_name=body.model_name,
            )

    except Exception as e:
        latency_ms = int((time.perf_counter() - start) * 1000)
        return TestResponse(
            success=False,
            latency_ms=latency_ms,
            error=f"Routing error: {str(e)}",
            provider_name="unknown",
            model_name=body.model_name,
        )
