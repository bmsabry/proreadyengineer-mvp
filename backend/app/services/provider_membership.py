"""Shared helper for resolving a user's provider membership.

A user can belong to more than one provider firm (the add-firm flow creates an
additional ProviderMembership row for the same user). Looking that up with
``scalar_one_or_none()`` / ``scalar_one()`` raises ``MultipleResultsFound`` and
500s every provider endpoint for multi-firm users. Use this helper instead: it
returns ONE membership deterministically (lowest provider_id) or None.
"""
from __future__ import annotations


async def get_user_provider_membership(db, user_id):
    """Return one ProviderMembership for the user (lowest provider_id), or None."""
    from sqlalchemy import select
    from app.models.provider import ProviderMembership

    res = await db.execute(
        select(ProviderMembership)
        .where(ProviderMembership.user_id == user_id)
        .order_by(ProviderMembership.provider_id)
    )
    return res.scalars().first()
