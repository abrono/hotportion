"""
Shared dependency re-exports.

Central import point so routes can do `from app.dependencies import ...`.
"""

from app.database import get_supabase, execute_db
from app.api.integrations.brevo import get_brevo, BrevoIntegration
from app.api.integrations.monnify import get_monnify, MonnifyIntegration
from app.api.integrations.aws_location import get_aws_location, AWSLocationService
from app.api.integrations.ai_service import get_ai_service, AIService
from app.auth import (
    get_current_customer, require_role, require_admin,
    _staff_profile,
)


__all__ = [
    "get_supabase", "execute_db",
    "get_brevo", "BrevoIntegration",
    "get_monnify", "MonnifyIntegration",
    "get_aws_location", "AWSLocationService",
    "get_ai_service", "AIService",
    "get_current_customer", "require_role", "require_admin",
    "_staff_profile",
]
