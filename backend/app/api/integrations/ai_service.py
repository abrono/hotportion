"""
Multi-provider AI service with guardrails, context caching, and provider fallback.

Providers: Groq (primary), Gemini, OpenAI (fallbacks).
"""

import asyncio
import re
import time
from typing import Any, Dict, Optional

from supabase import create_client, Client
from tenacity import retry, stop_after_attempt, wait_exponential

from app.config import settings
from app.api.utils.logging_setup import logger

try:
    import groq
except ImportError:
    groq = None
try:
    import google.generativeai as genai
except ImportError:
    genai = None
try:
    import openai
except ImportError:
    openai = None


# =============================================
# AI SERVICE
# =============================================
class AIService:
    def __init__(self):
        self.groq_client = None
        self.genai_client = None
        self.openai_client = None
        self.supabase_client: Optional[Client] = None
        self._context_cache: Optional[str] = None
        self._cache_timestamp: float = 0
        self._cache_ttl: int = 3600
        self._init_clients()
        self.banned_words = {
            "kill", "murder", "hate", "racist", "sex", "porn", "assault",
            "terror", "bomb", "shoot", "stab", "rape", "slave", "abuse",
            "harass",
        }
        self.base_system_prompt = (
            "You are an AI assistant for 'Hot Portion Grill', a Nigerian restaurant. "
            "Help customers with menu, prices, orders, special offers, and food queries. "
            "Answer strictly based on the provided PRODUCTS and KNOWLEDGE BASE below. "
            "If an item or answer is not in the provided information, state politely that it is unavailable. "
            "Do not answer questions completely unrelated to food, restaurants, or ordering. "
            "Keep responses concise, friendly, and professional. "
            "When a user asks for the 'menu', 'what do you have', or 'list all items', "
            "respond with a clear list of all available products from the PRODUCTS section, "
            "including name and price. If the list is long, provide a summary and offer to give more details. "
            "Format: use hyphens for lists, **bold** for item names, ₦X,XXX for prices, "
            "and group menu items by category. Use emojis sparingly."
        )

    def _init_clients(self):
        supabase_url = getattr(settings, "SUPABASE_URL", None)
        supabase_key = getattr(settings, "SUPABASE_SERVICE_KEY", None)
        if supabase_url and supabase_key:
            try:
                self.supabase_client = create_client(supabase_url, supabase_key)
            except Exception as e:
                logger.error(f"Failed to init Supabase client: {e}")

        if settings.GROQ_API_KEY and groq is not None:
            self.groq_client = groq.Groq(api_key=settings.GROQ_API_KEY)
        if settings.GEMINI_API_KEY and genai is not None:
            genai.configure(api_key=settings.GEMINI_API_KEY)
            self.genai_client = genai.GenerativeModel(settings.GEMINI_MODEL)
        if settings.OPENAI_API_KEY and openai is not None:
            self.openai_client = openai.OpenAI(api_key=settings.OPENAI_API_KEY)

    def _get_context(self) -> str:
        now = time.time()
        if self._context_cache and (now - self._cache_timestamp < self._cache_ttl):
            return self._context_cache

        if not self.supabase_client:
            return ""

        try:
            products_res = self.supabase_client.table("products").select("*").execute()
            products = products_res.data or []
            knowledge_res = self.supabase_client.table("knowledge").select("*").execute()
            knowledge = knowledge_res.data or []

            ctx = "\n\n=== PRODUCTS / MENU ===\n"
            for p in products:
                ctx += (
                    f"- {p.get('name','Item')}: {p.get('price','N/A')} | "
                    f"Desc: {p.get('description','N/A')} | "
                    f"Status: {p.get('status','available')}\n"
                )

            ctx += "\n=== KNOWLEDGE BASE & STORE INFO ===\n"
            for k in knowledge:
                ctx += f"- {k.get('topic','Information')}: {k.get('content','')}\n"

            self._context_cache = ctx
            self._cache_timestamp = now
            return ctx
        except Exception as e:
            logger.error(f"Error fetching AI context: {e}")
            return self._context_cache or ""

    def _build_system_prompt(self) -> str:
        return f"{self.base_system_prompt}{self._get_context()}"

    def _normalize(self, text: str) -> str:
        text = text.lower()
        for old, new in {
            "3": "e", "4": "a", "0": "o", "@": "a", "$": "s", "5": "s",
        }.items():
            text = text.replace(old, new)
        return text

    def _guard_input(self, text: str) -> bool:
        patterns = [
            r"ignore (?:all )?previous instructions",
            r"forget (?:all )?previous (?:instructions|context)",
            r"you are (?:now )?a (?:new )?ai",
            r"system prompt",
            r"override (?:the )?system",
        ]
        for p in patterns:
            if re.search(p, text, re.IGNORECASE):
                return False
        words = set(re.findall(r"\b\w+\b", self._normalize(text)))
        if words.intersection(self.banned_words):
            return False
        return True

    def _guard_output(self, text: str) -> bool:
        words = set(re.findall(r"\b\w+\b", self._normalize(text)))
        if words.intersection(self.banned_words):
            return False
        return 2 <= len(text) <= 2000

    @retry(stop=stop_after_attempt(2), wait=wait_exponential(multiplier=1, min=1, max=3))
    async def query_groq(self, msg, system_prompt, history) -> Optional[str]:
        if not self.groq_client:
            raise ValueError("Groq unavailable")
        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(history)
        messages.append({"role": "user", "content": msg})
        resp = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: self.groq_client.chat.completions.create(
                model=settings.GROQ_MODEL,
                messages=messages,
                temperature=0.3,
                max_tokens=700,
                timeout=10.0,
            ),
        )
        return resp.choices[0].message.content

    @retry(stop=stop_after_attempt(2), wait=wait_exponential(multiplier=1, min=1, max=3))
    async def query_gemini(self, msg, system_prompt, history) -> Optional[str]:
        if not self.genai_client:
            raise ValueError("Gemini unavailable")
        formatted = ""
        for h in history:
            role = "User" if h.get("role") == "user" else "Assistant"
            formatted += f"\n{role}: {h.get('content','')}"
        full = f"{system_prompt}\n{formatted}\nUser: {msg}\nAssistant:"
        response = await asyncio.get_event_loop().run_in_executor(
            None, self.genai_client.generate_content, full
        )
        return response.text

    @retry(stop=stop_after_attempt(2), wait=wait_exponential(multiplier=1, min=1, max=3))
    async def query_openai(self, msg, system_prompt, history) -> Optional[str]:
        if not self.openai_client:
            raise ValueError("OpenAI unavailable")
        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(history)
        messages.append({"role": "user", "content": msg})
        resp = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: self.openai_client.chat.completions.create(
                model=settings.OPENAI_MODEL,
                messages=messages,
                temperature=0.3,
                max_tokens=700,
                timeout=10.0,
            ),
        )
        return resp.choices[0].message.content

    async def chat(self, msg: str, history=None) -> Dict[str, Any]:
        if not self._guard_input(msg):
            return {
                "response": "I cannot process that request.",
                "provider": "guardrail",
                "model": "blocked",
            }

        conversation = history[-6:] if history else []
        system_prompt = self._build_system_prompt()

        available = []
        if self.groq_client:
            available.append(("groq", self.query_groq, settings.GROQ_MODEL))
        if self.genai_client:
            available.append(("gemini", self.query_gemini, settings.GEMINI_MODEL))
        if self.openai_client:
            available.append(("openai", self.query_openai, settings.OPENAI_MODEL))

        if not available:
            return {"response": "No AI provider available.",
                    "provider": "error", "model": "none"}

        ordered = []
        for p in available:
            if p[0] == settings.AI_PRIMARY:
                ordered.append(p)
                break
        if settings.AI_FALLBACK != settings.AI_PRIMARY:
            for p in available:
                if p[0] == settings.AI_FALLBACK and p not in ordered:
                    ordered.append(p)
                    break
        for p in available:
            if p not in ordered:
                ordered.append(p)

        for name, func, model in ordered:
            try:
                content = await func(msg, system_prompt, conversation)
                if content and self._guard_output(content):
                    return {"response": content, "provider": name, "model": model}
            except Exception as e:
                logger.warning(f"Provider {name} failed: {e}")
                continue

        return {"response": "I'm currently unable to respond.",
                "provider": "error", "model": "none"}


_ai_service: Optional[AIService] = None


def get_ai_service() -> AIService:
    global _ai_service
    if _ai_service is None:
        _ai_service = AIService()
    return _ai_service
