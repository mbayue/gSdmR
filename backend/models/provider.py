"""Pydantic models for provider CRUD operations."""

from pydantic import BaseModel, Field
from typing import Optional
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
