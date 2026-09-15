"""
AI router — public but IP-rate-limited.

Endpoints:
    POST /api/ai/chat
    GET  /api/ai/health
"""

from fastapi import APIRouter, Depends

from app.config import settings
from app.models.ai import AIChatRequest, AIChatResponse
from app.api.integrations.ai_service import AIService, get_ai_service
from app.api.utils.rate_limiter import ai_rate_limit


ai_router = APIRouter()


# =============================================
# ROUTES — AI (rate limited)
# =============================================
@ai_router.post("/api/ai/chat", response_model=AIChatResponse,
                dependencies=[Depends(ai_rate_limit)])
async def chat_with_ai(
    req: AIChatRequest,
    ai_service: AIService = Depends(get_ai_service),
):
    result = await ai_service.chat(req.message)
    return AIChatResponse(
        response=result["response"],
        provider=result["provider"],
        model=result["model"],
    )


@ai_router.get("/api/ai/health")
async def ai_health(ai_service: AIService = Depends(get_ai_service)):
    return {
        "groq": ai_service.groq_client is not None,
        "gemini": ai_service.genai_client is not None,
        "openai": ai_service.openai_client is not None,
        "primary": settings.AI_PRIMARY,
        "fallback": settings.AI_FALLBACK,
    }
