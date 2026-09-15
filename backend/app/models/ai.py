"""AI chat models."""

from typing import Any, Dict, Optional

from pydantic import BaseModel


class AIChatRequest(BaseModel):
    message: str
    context: Optional[Dict[str, Any]] = None


class AIChatResponse(BaseModel):
    response: str
    provider: str
    model: str
