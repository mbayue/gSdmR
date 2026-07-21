"""Pydantic models for model CRUD operations."""

from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


class ModelProviderMapping(BaseModel):
    provider_id: int
    provider_model: str = Field(..., min_length=1)  # actual model name at the provider
    priority: int = Field(..., ge=1)


class ModelCreate(BaseModel):
    name: str = Field(..., min_length=1)  # custom alias name
    providers: List[ModelProviderMapping] = Field(..., min_length=1)


class ModelUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1)
    providers: Optional[List[ModelProviderMapping]] = None


class ModelResponse(BaseModel):
    id: int
    name: str
    providers: List[dict]  # [{provider_id, provider_name, provider_model, priority}]
    created_at: datetime
    updated_at: datetime
