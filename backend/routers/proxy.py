"""Proxy endpoints for OpenAI, Anthropic, and OpenAI Responses API requests.

Provides three proxy endpoints that authenticate via API key, resolve model to
providers, and forward requests with priority-based fallback.
"""

from typing import Any, Optional, List

from fastapi import APIRouter, Body, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from database import get_db
from middleware.api_key import validate_api_key
from middleware.rate_limit import check_rate_limit
from services.routing import route_request
from services.usage import UsageRecord, RequestTimer, log_usage, extract_token_usage

router = APIRouter(tags=["proxy"])


# --- Request/Response schemas for OpenAPI docs ---

class ChatMessage(BaseModel):
    role: str = Field(..., json_schema_extra={"example": "user"})
    content: str = Field(..., json_schema_extra={"example": "Hello!"})

class ChatCompletionRequest(BaseModel):
    model_config = {"extra": "allow"}

    model: str = Field(..., json_schema_extra={"example": "gpt"})
    messages: List[ChatMessage] = Field(..., min_length=1)
    temperature: Optional[float] = Field(None, json_schema_extra={"example": 0.7})
    max_tokens: Optional[int] = Field(None, json_schema_extra={"example": 1024})
    stream: Optional[bool] = Field(False)
    top_p: Optional[float] = None
    frequency_penalty: Optional[float] = None
    presence_penalty: Optional[float] = None

class AnthropicMessage(BaseModel):
    role: str = Field(..., json_schema_extra={"example": "user"})
    content: str = Field(..., json_schema_extra={"example": "Hello!"})

class AnthropicRequest(BaseModel):
    model_config = {"extra": "allow"}

    model: str = Field(..., json_schema_extra={"example": "gpt"})
    messages: List[AnthropicMessage] = Field(..., min_length=1)
    max_tokens: Optional[int] = Field(1024, json_schema_extra={"example": 1024})
    temperature: Optional[float] = Field(None, json_schema_extra={"example": 0.7})
    stream: Optional[bool] = Field(False)
    system: Optional[str] = None
    top_p: Optional[float] = None

class ResponsesRequest(BaseModel):
    model_config = {"extra": "allow"}

    model: str = Field(..., json_schema_extra={"example": "gpt"})
    input: Any = Field(..., json_schema_extra={"example": "Hello!"})
    temperature: Optional[float] = Field(None, json_schema_extra={"example": 0.7})
    max_output_tokens: Optional[int] = Field(None, json_schema_extra={"example": 1024})
    stream: Optional[bool] = Field(False)
    instructions: Optional[str] = None
    top_p: Optional[float] = None
    tools: Optional[List[Any]] = None
    tool_choice: Optional[Any] = None

class ModelInfo(BaseModel):
    id: str = Field(..., json_schema_extra={"example": "gpt"})
    object: str = Field("model")
    created: int = Field(..., json_schema_extra={"example": 1784641000})
    owned_by: str = Field("router")
    supported_endpoint_types: List[str] = Field(..., json_schema_extra={"example": ["openai", "anthropic", "responses"]})

class ModelListResponse(BaseModel):
    object: str = Field("list")
    data: List[ModelInfo]


# --- Helpers ---

def _check_model_access(model_name: str, key_info: dict) -> JSONResponse | None:
    """Check if the API key is allowed to access the requested model."""
    allowed = key_info.get("allowed_models")
    if allowed is None:
        return None
    if model_name not in allowed:
        return JSONResponse(
            status_code=403,
            content={
                "error": {
                    "message": f"API key does not have access to model '{model_name}'",
                    "type": "permission_denied",
                }
            },
        )
    return None


# --- Endpoints ---

@router.post("/v1/chat/completions", summary="OpenAI Chat Completions",
             description="Send a chat completion request in OpenAI format. The router resolves the model to a provider and forwards with priority-based fallback.")
async def openai_chat_completions(
    request: Request,
    body_schema: ChatCompletionRequest = Body(...),
    key_info: dict = Depends(validate_api_key),
):
    await check_rate_limit(request, key_info)
    body = body_schema.model_dump(exclude_none=True)
    model_name = body.get("model")

    if not model_name:
        return JSONResponse(
            status_code=400,
            content={"error": {"message": "model field is required", "type": "invalid_request_error"}},
        )

    denied = _check_model_access(model_name, key_info)
    if denied:
        return denied

    is_streaming = body.get("stream", False)

    with RequestTimer() as timer:
        response, provider_used = await route_request(model_name=model_name, request_body=body, endpoint_path="chat/completions", is_streaming=is_streaming)

    # Log usage in background
    status_code = response.status_code if hasattr(response, "status_code") else 200
    tokens = (0, 0, 0)
    if hasattr(response, "body"):
        import json as _json
        try:
            tokens = extract_token_usage(_json.loads(response.body))
        except Exception:
            pass

    await log_usage(UsageRecord(
        api_key_id=key_info["key_id"],
        model_name=model_name,
        provider_name=provider_used,
        endpoint="chat/completions",
        status_code=status_code,
        latency_ms=timer.elapsed_ms,
        prompt_tokens=tokens[0],
        completion_tokens=tokens[1],
        total_tokens=tokens[2],
    ))

    return response


@router.post("/v1/messages", summary="Anthropic Messages",
             description="Send a message request in Anthropic format. The router resolves the model to a provider and forwards with priority-based fallback.")
async def anthropic_messages(
    request: Request,
    body_schema: AnthropicRequest = Body(...),
    key_info: dict = Depends(validate_api_key),
):
    await check_rate_limit(request, key_info)
    body = body_schema.model_dump(exclude_none=True)
    model_name = body.get("model")

    if not model_name:
        return JSONResponse(
            status_code=400,
            content={"error": {"message": "model field is required", "type": "invalid_request_error"}},
        )

    denied = _check_model_access(model_name, key_info)
    if denied:
        return denied

    is_streaming = body.get("stream", False)

    with RequestTimer() as timer:
        response, provider_used = await route_request(model_name=model_name, request_body=body, endpoint_path="messages", is_streaming=is_streaming)

    status_code = response.status_code if hasattr(response, "status_code") else 200
    tokens = (0, 0, 0)
    if hasattr(response, "body"):
        import json as _json
        try:
            tokens = extract_token_usage(_json.loads(response.body))
        except Exception:
            pass

    await log_usage(UsageRecord(
        api_key_id=key_info["key_id"],
        model_name=model_name,
        provider_name=provider_used,
        endpoint="messages",
        status_code=status_code,
        latency_ms=timer.elapsed_ms,
        prompt_tokens=tokens[0],
        completion_tokens=tokens[1],
        total_tokens=tokens[2],
    ))

    return response


@router.post("/v1/responses", summary="OpenAI Responses",
             description="Send a request in OpenAI Responses API format. Uses `input` field instead of `messages`. The router resolves the model and forwards with fallback.")
async def openai_responses(
    request: Request,
    body_schema: ResponsesRequest = Body(...),
    key_info: dict = Depends(validate_api_key),
):
    await check_rate_limit(request, key_info)
    body = body_schema.model_dump(exclude_none=True)
    model_name = body.get("model")

    if not model_name:
        return JSONResponse(
            status_code=400,
            content={"error": {"message": "model field is required", "type": "invalid_request_error"}},
        )

    denied = _check_model_access(model_name, key_info)
    if denied:
        return denied

    is_streaming = body.get("stream", False)

    with RequestTimer() as timer:
        response, provider_used = await route_request(model_name=model_name, request_body=body, endpoint_path="responses", is_streaming=is_streaming)

    status_code = response.status_code if hasattr(response, "status_code") else 200
    tokens = (0, 0, 0)
    if hasattr(response, "body"):
        import json as _json
        try:
            tokens = extract_token_usage(_json.loads(response.body))
        except Exception:
            pass

    await log_usage(UsageRecord(
        api_key_id=key_info["key_id"],
        model_name=model_name,
        provider_name=provider_used,
        endpoint="responses",
        status_code=status_code,
        latency_ms=timer.elapsed_ms,
        prompt_tokens=tokens[0],
        completion_tokens=tokens[1],
        total_tokens=tokens[2],
    ))

    return response


@router.get("/v1/models", summary="List Models", response_model=ModelListResponse,
            description="List available models (OpenAI-compatible format). Respects per-key model restrictions.")
async def list_models(key_info: dict = Depends(validate_api_key)):
    import time

    db = await get_db()
    cursor = await db.execute("SELECT id, name FROM models ORDER BY name")
    rows = await cursor.fetchall()

    allowed = key_info.get("allowed_models")
    models = []
    for row in rows:
        if allowed is not None and row["name"] not in allowed:
            continue
        models.append({
            "id": row["name"],
            "object": "model",
            "created": int(time.time()),
            "owned_by": "gsdm-r",
            "supported_endpoint_types": ["openai", "anthropic", "responses"],
        })

    return {"object": "list", "data": models}

