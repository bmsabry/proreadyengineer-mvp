"""Database base and model imports for Alembic autogenerate support.

Imports ALL models so that Base.metadata contains the complete schema.
Required for `alembic revision --autogenerate` to work correctly.
"""

from app.models.base import Base  # noqa: F401

# Import all models to populate Base.metadata
from app.models.user import User, RefreshToken, PasswordResetToken  # noqa: F401
from app.models.provider import Provider, ProviderMembership, ProviderClaimRequest  # noqa: F401
from app.models.search import IPUsageTracking, SearchRequest  # noqa: F401
from app.models.rfq import (  # noqa: F401
    RFQ, RFQFile, RFQMatch, RFQDispatchBatch, RFQDispatch, RFQUnlock
)
from app.models.quote import Quote, QuoteFile  # noqa: F401
from app.models.nda import RFQNDA  # noqa: F401
from app.models.payment import PaymentAttempt, Subscription, WebhookEvent  # noqa: F401
from app.models.advertising import AdSlot, Advertisement  # noqa: F401
from app.models.admin import TierEvaluationRequest, AuditLog  # noqa: F401

__all__ = ["Base"]

from app.models.system_config import SystemConfig  # noqa: F401
from app.models.support import SupportTicket, SupportTicketMessage, SupportTicketEvent  # noqa: F401
from app.models.help_chat import HelpChatLog  # noqa: F401
