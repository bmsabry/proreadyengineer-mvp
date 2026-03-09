"""Search and discovery service with OpenAI embeddings and pgvector similarity."""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any, Optional

import openai
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models import IPUsageTracking, Provider, SearchRequest, User
from app.schemas.search import LLMStructuredOutput, SearchResultItem

if TYPE_CHECKING:
    from app.models import Provider


async def generate_embedding(text: str) -> list[float]:
    """Generate embedding vector using OpenAI API.

    Args:
        text: Text to embed (normalized query or provider description).

    Returns:
        list[float]: 1536-dimensional embedding vector.

    Raises:
        RuntimeError: If OpenAI API call fails.
    """
    if not settings.OPENAI_API_KEY:
        raise RuntimeError("OpenAI API key not configured")

    try:
        client = openai.AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        response = await client.embeddings.create(
            model=settings.OPENAI_EMBEDDING_MODEL,
            input=text[:8000],  # Truncate to safe limit
        )
        return response.data[0].embedding
    except Exception as e:
        raise RuntimeError(f"Failed to generate embedding: {e}")


async def extract_structured_intent(query: str) -> Optional[LLMStructuredOutput]:
    """Use LLM to extract structured search intent from natural language query.

    Args:
        query: Natural language search query.

    Returns:
        LLMStructuredOutput | None: Structured intent or None if extraction fails.
    """
    if not settings.OPENAI_API_KEY:
        return None

    try:
        client = openai.AsyncOpenAI(api_key=settings.OPENAI_API_KEY)

        system_prompt = """You are an engineering services search analyzer.
Extract structured information from the user's search query about engineering needs.
Return ONLY valid JSON matching the schema."""

        user_prompt = f"""Analyze this engineering services search query:
"{query}"

Extract and return JSON with these fields:
- requires_engineering: 1 if query is for engineering services, 0 otherwise
- requires_mechanical: 1 if query involves mechanical/physical engineering, 0 otherwise
- software_mentioned: list of CAD/CAE software mentioned (e.g., ["ANSYS", "SolidWorks"])
- inferred_specialty: string describing the engineering specialty needed
- capabilities_needed: list of specific capabilities mentioned

Example output:
{{
    "requires_engineering": 1,
    "requires_mechanical": 1,
    "software_mentioned": ["ANSYS", "SolidWorks"],
    "inferred_specialty": "structural fatigue analysis",
    "capabilities_needed": ["FEA", "stress analysis", "fatigue testing"]
}}"""

        response = await client.chat.completions.create(
            model=settings.OPENAI_LLM_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            response_format={"type": "json_object"},
            max_tokens=500,
            temperature=0.1,
        )

        import json
        result = json.loads(response.choices[0].message.content)
        return LLMStructuredOutput(**result)
    except Exception:
        # Fail gracefully - return None to trigger fallback logic
        return None


def _normalize_query(query: str) -> str:
    """Normalize search query for better matching.

    Args:
        query: Raw search query.

    Returns:
        str: Normalized query.
    """
    # Basic normalization
    normalized = query.lower().strip()
    # Remove extra whitespace
    normalized = " ".join(normalized.split())
    return normalized


def _calculate_tier_score(tier: Optional[str]) -> int:
    """Calculate tier multiplier score.

    Args:
        tier: Provider tier (A, B, C, D, E).

    Returns:
        int: Tier score (25, 20, 15, 10, 5 or 0).
    """
    tier_scores = {"A": 25, "B": 20, "C": 15, "D": 10, "E": 5}
    return tier_scores.get(tier.upper() if tier else "", 0)


def _calculate_specialty_score(
    provider: Provider, intent: LLMStructuredOutput
) -> int:
    """Calculate specialty match score (0-25).

    Args:
        provider: Provider record.
        intent: Extracted search intent.

    Returns:
        int: Specialty match score.
    """
    score = 0

    if not intent or not intent.inferred_specialty:
        # No structured intent - give partial credit
        return 15

    # Check primary specialty match
    if provider.primary_specialty:
        primary_lower = provider.primary_specialty.lower()
        intent_specialty_lower = intent.inferred_specialty.lower()

        # Direct match or significant overlap
        if intent_specialty_lower in primary_lower or primary_lower in intent_specialty_lower:
            score += 15
        # Partial match - check keywords
        elif any(word in primary_lower for word in intent_specialty_lower.split() if len(word) > 3):
            score += 8

    # Check secondary specialties
    if provider.secondary_specialties and intent.inferred_specialty:
        for specialty in provider.secondary_specialties:
            if intent.inferred_specialty.lower() in specialty.lower():
                score += 5
                break

    # Check inferred specialty against specialties array
    if provider.specialties and intent.inferred_specialty:
        for spec in provider.specialties:
            if intent.inferred_specialty.lower() in spec.lower():
                score += 5
                break

    return min(score, 25)


def _calculate_capabilities_score(
    provider: Provider, intent: LLMStructuredOutput
) -> int:
    """Calculate capabilities match score (0-50).

    Args:
        provider: Provider record.
        intent: Extracted search intent.

    Returns:
        int: Capabilities match score.
    """
    score = 0

    if not intent or not intent.capabilities_needed:
        return 25  # Neutral score if no capabilities specified

    provider_capabilities = provider.capabilities or []
    provider_software = provider.software_tools or []

    # Check software mentions
    if intent.software_mentioned:
        for software in intent.software_mentioned:
            software_lower = software.lower()
            # Check in software_tools
            if any(software_lower in s.lower() for s in provider_software):
                score += 10
            # Check in capabilities
            if any(software_lower in c.lower() for c in provider_capabilities):
                score += 5

    # Check capability keywords
    for needed in intent.capabilities_needed:
        needed_lower = needed.lower()
        if any(needed_lower in c.lower() for c in provider_capabilities):
            score += 8
        elif provider.business_description and needed_lower in provider.business_description.lower():
            score += 4

    return min(score, 50)


async def calculate_match_score(
    provider: Provider, query_intent: LLMStructuredOutput
) -> dict[str, Any]:
    """Calculate composite match score for a provider.

    Args:
        provider: Provider to score.
        query_intent: Extracted structured intent.

    Returns:
        dict: Scoring breakdown with specialty, capabilities, tier, and total.
    """
    specialty_score = _calculate_specialty_score(provider, query_intent)
    capabilities_score = _calculate_capabilities_score(provider, query_intent)
    tier_score = _calculate_tier_score(provider.business_evaluation_tier)

    composite_score = specialty_score + capabilities_score + tier_score

    return {
        "composite_score": composite_score,
        "specialty_score": specialty_score,
        "capabilities_score": capabilities_score,
        "tier_score": tier_score,
        "scoring_inputs": {
            "primary_specialty": provider.primary_specialty,
            "capabilities": provider.capabilities,
            "tier": provider.business_evaluation_tier,
            "intent_specialty": query_intent.inferred_specialty if query_intent else None,
            "intent_capabilities": query_intent.capabilities_needed if query_intent else None,
        },
    }


async def search_providers(
    db: AsyncSession,
    query: str,
    filters: dict[str, Any],
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Search providers using vector similarity with hard filters.

    Args:
        db: Database session.
        query: Search query text.
        filters: Hard filters to apply (is_engineering_service, is_mechanical_focus, etc.).
        limit: Maximum results to return.

    Returns:
        list: Provider matches with scores.
    """
    # Normalize query
    normalized_query = _normalize_query(query)

    # Extract structured intent
    structured_intent = await extract_structured_intent(query)

    # Generate query embedding
    try:
        query_embedding = await generate_embedding(normalized_query)
    except RuntimeError:
        # Fallback: use keyword search only
        query_embedding = None

    # Build base query with hard filters
    stmt = select(Provider).where(Provider.is_engineering_service == 1)

    # Apply hard filters
    if filters.get("is_mechanical_focus"):
        stmt = stmt.where(Provider.is_mechanical_focus == 1)

    if filters.get("software_mentioned") and query_embedding:
        # Software filtering will be done post-vector similarity
        pass

    if query_embedding:
        # Use pgvector cosine similarity
        # Embedding model produces 1536-dim vectors
        embedding_param = "[" + ",".join(str(x) for x in query_embedding) + "]"

        stmt = stmt.where(Provider.embedding.isnot(None))
        stmt = stmt.order_by(
            Provider.embedding.cosine_distance(query_embedding)
        )
        stmt = stmt.limit(limit * 2)  # Get extra for filtering
    else:
        # Fallback: order by tier and rating
        stmt = stmt.order_by(
            func.coalesce(Provider.business_evaluation_tier, "Z"),
            Provider.rating.desc().nullslast(),
        )
        stmt = stmt.limit(limit * 2)

    result = await db.execute(stmt)
    providers = result.scalars().all()

    # Apply software filter if needed
    if filters.get("software_mentioned") and structured_intent:
        software_list = [s.lower() for s in structured_intent.software_mentioned]
        filtered_providers = []

        for provider in providers:
            provider_software = [s.lower() for s in (provider.software_tools or [])]
            # Check if any required software matches
            if any(req in ps for req in software_list for ps in provider_software):
                filtered_providers.append(provider)

        # If no matches after filter, include all (fallback)
        if not filtered_providers and providers:
            fallback_reason = "software_filter_relaxed"
            filtered_providers = list(providers)
        else:
            fallback_reason = None

        providers = filtered_providers
    else:
        fallback_reason = None

    # Calculate scores for all candidates
    scored_results = []
    for provider in providers:
        score_data = await calculate_match_score(provider, structured_intent)
        scored_results.append({
            "provider": provider,
            **score_data,
        })

    # Sort by composite score descending
    scored_results.sort(key=lambda x: x["composite_score"], reverse=True)

    # Take top results
    top_results = scored_results[:limit]

    # Add fallback reason if applicable
    for result in top_results:
        result["fallback_reason"] = fallback_reason

    return top_results


async def check_search_quota(
    db: AsyncSession, user: Optional[User], ip: str
) -> tuple[bool, int, Optional[int], Optional[datetime]]:
    """Check if user has remaining search quota.

    Args:
        db: Database session.
        user: Authenticated user or None for anonymous.
        ip: Client IP address.

    Returns:
        tuple: (has_quota, quota_used, quota_limit, reset_at)
    """
    current_month = datetime.utcnow().strftime("%Y-%m")

    if user:
        # Check user's monthly search count
        # Reset if needed
        if (user.search_count_reset_at is None or 
            user.search_count_reset_at.strftime("%Y-%m") != current_month):
            user.monthly_search_count = 0
            user.search_count_reset_at = datetime.utcnow()

        # Check active subscriptions for paid tiers
        from app.models import Subscription, SubscriptionStatus, SubscriptionType

        result = await db.execute(
            select(Subscription).where(
                Subscription.user_id == user.id,
                Subscription.subscription_status == SubscriptionStatus.ACTIVE,
                Subscription.subscription_type.in_([
                    SubscriptionType.SEARCH_TIER_1,
                    SubscriptionType.SEARCH_TIER_2,
                ]),
            )
        )
        subscription = result.scalar_one_or_none()

        if subscription:
            # Paid tier
            if subscription.subscription_type == SubscriptionType.SEARCH_TIER_1:
                quota_limit = settings.SEARCH_TIER_1_LIMIT
            else:
                quota_limit = settings.SEARCH_TIER_2_LIMIT
        else:
            # Free tier
            quota_limit = settings.REGISTERED_SEARCH_LIMIT_PER_MONTH

        has_quota = user.monthly_search_count < quota_limit
        reset_at = (user.search_count_reset_at + timedelta(days=30)) if user.search_count_reset_at else None

        return has_quota, user.monthly_search_count, quota_limit, reset_at

    else:
        # Anonymous - track by IP
        result = await db.execute(
            select(IPUsageTracking).where(
                IPUsageTracking.ip_address == ip,
                IPUsageTracking.usage_month == current_month,
            )
        )
        tracking = result.scalar_one_or_none()

        if not tracking:
            # First search from this IP this month
            return True, 0, settings.ANONYMOUS_SEARCH_LIMIT_PER_MONTH, None

        has_quota = tracking.search_count < settings.ANONYMOUS_SEARCH_LIMIT_PER_MONTH

        # Reset is start of next month
        next_month = datetime.utcnow().replace(day=1) + timedelta(days=32)
        next_month = next_month.replace(day=1)

        return has_quota, tracking.search_count, settings.ANONYMOUS_SEARCH_LIMIT_PER_MONTH, next_month


async def increment_search_quota(
    db: AsyncSession, user: Optional[User], ip: str
) -> None:
    """Increment search quota usage.

    Args:
        db: Database session.
        user: Authenticated user or None for anonymous.
        ip: Client IP address.
    """
    if user:
        user.monthly_search_count += 1
    else:
        current_month = datetime.utcnow().strftime("%Y-%m")

        result = await db.execute(
            select(IPUsageTracking).where(
                IPUsageTracking.ip_address == ip,
                IPUsageTracking.usage_month == current_month,
            )
        )
        tracking = result.scalar_one_or_none()

        if tracking:
            tracking.search_count += 1
        else:
            tracking = IPUsageTracking(
                ip_address=ip,
                usage_month=current_month,
                search_count=1,
            )
            db.add(tracking)

    await db.commit()


async def log_search_request(
    db: AsyncSession,
    query: str,
    user: Optional[User],
    ip: str,
    structured_intent: Optional[LLMStructuredOutput],
    results_count: int,
    fallback_reason: Optional[str] = None,
) -> SearchRequest:
    """Log search request for audit and analytics.

    Args:
        db: Database session.
        query: Original search query.
        user: Authenticated user or None.
        ip: Client IP address.
        structured_intent: Extracted structured intent.
        results_count: Number of results returned.
        fallback_reason: Reason for fallback logic if applicable.

    Returns:
        SearchRequest: Created log record.
    """
    import json

    search_request = SearchRequest(
        user_id=user.id if user else None,
        ip_address=ip,
        raw_query_text=query,
        normalized_query_text=_normalize_query(query),
        llm_structured_output=structured_intent.model_dump() if structured_intent else None,
        llm_model=settings.OPENAI_LLM_MODEL if structured_intent else None,
        search_status="completed",
        fallback_reason=fallback_reason,
        results_count=results_count,
    )

    db.add(search_request)
    await db.commit()
    await db.refresh(search_request)

    return search_request
