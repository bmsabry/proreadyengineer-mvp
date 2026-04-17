"""API endpoint routers.

This module contains all FastAPI APIRouter instances organized by domain.
"""

from app.api.endpoints.auth import router as auth_router
from app.api.endpoints.search import router as search_router
from app.api.endpoints.providers import router as providers_router
from app.api.endpoints.rfqs import router as rfqs_router
from app.api.endpoints.quotes import router as quotes_router
from app.api.endpoints.payments import router as payments_router
from app.api.endpoints.ads import router as ads_router
from app.api.endpoints.admin import router as admin_router
from app.api.endpoints.campaigns import router as campaigns_router

__all__ = [
    "auth_router",
    "search_router",
    "providers_router",
    "rfqs_router",
    "quotes_router",
    "payments_router",
    "ads_router",
    "admin_router",
    "campaigns_router",
]
from app.api.endpoints.support import router as support_router  # noqa: F401
from app.api.endpoints.help import router as help_router  # noqa: F401
