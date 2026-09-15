from typing import List, Optional, Dict

from pydantic import Field
from pydantic_settings import BaseSettings
from dotenv import load_dotenv

load_dotenv()


class Settings(BaseSettings):
    # Core
    SUPABASE_URL: str = Field(..., min_length=1)
    SUPABASE_SERVICE_KEY: str = Field(..., min_length=1)
    # Deprecated: kept for backwards compatibility with existing .env files.
    # Staff/admin authentication is now JWT-based (see app/auth.py).
    ADMIN_API_KEY: Optional[str] = None

    # Email
    BREVO_API_KEY: str = Field(..., min_length=1)
    BREVO_SENDER_EMAIL: str = Field(..., min_length=1)
    BREVO_SENDER_NAME: str = "Hot Portion Grill"

    # Payments
    MONNIFY_API_KEY: str = Field(..., min_length=1)
    MONNIFY_SECRET_KEY: str = Field(..., min_length=1)
    MONNIFY_CONTRACT_CODE: str = Field(..., min_length=1)
    MONNIFY_BASE_URL: str = "https://sandbox.monnify.com"
    MONNIFY_WEBHOOK_HEADER: str = "monnify-signature"

    # AI
    GROQ_API_KEY: Optional[str] = None
    GEMINI_API_KEY: Optional[str] = None
    OPENAI_API_KEY: Optional[str] = None
    GROQ_MODEL: str = "openai/gpt-oss-120b"
    GEMINI_MODEL: str = "gemini-2.0-flash"
    OPENAI_MODEL: str = "gpt-oss-120"
    AI_PRIMARY: str = "groq"
    AI_FALLBACK: str = "gemini"
    AI_RATE_LIMIT_PER_MIN: int = 10

    # CORS
    ALLOWED_ORIGINS: List[str] = [
        "https://your-netlify-site.netlify.app",
        "http://localhost:3000",
        "http://localhost:8000",
    ]

    # AWS Location Service
    AWS_REGION: str = "af-south-1"
    AWS_ACCESS_KEY_ID: Optional[str] = None
    AWS_SECRET_ACCESS_KEY: Optional[str] = None
    AWS_LOCATION_PLACE_INDEX: str = "hotportion-place-index"
    AWS_LOCATION_ROUTE_CALCULATOR: Optional[str] = None
    AWS_LOCATION_COUNTRY_FILTER: str = "NGA"

    # Delivery tuning
    MINIMUM_DELIVERY_FEE: int = 500
    MAX_LOYALTY_DISCOUNT_PERCENT: int = 15
    VOLUME_SURCHARGE_THRESHOLDS: Dict[str, int] = {
        "large": 4, "xlarge": 6, "xxlarge": 10,
    }
    VOLUME_SURCHARGE_AMOUNTS: Dict[str, int] = {
        "large": 150, "xlarge": 300, "xxlarge": 500,
    }
    WEIGHT_THRESHOLD_KG: float = 5.0
    WEIGHT_SURCHARGE_PER_KG: int = 100
    BULKY_ITEM_SURCHARGE: int = 200
    PEAK_SURCHARGE: int = 200

    # Runtime
    MAX_DB_THREADS: int = 25
    STATS_CACHE_TTL_SECONDS: int = 10
    DEBUG: bool = False

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


settings = Settings()
