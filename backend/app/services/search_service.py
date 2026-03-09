"""Search service for provider matching using AI embeddings with comprehensive debugging."""

import json
import logging
from typing import List, Optional, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text
from openai import AsyncOpenAI

from app.core.config import settings
from app.models.provider import Provider
from app.models.search import SearchRequest
from app.schemas.search import SearchQuery, SearchResult, ProviderMatch

logger = logging.getLogger(__name__)


class SearchService:
    """Service for AI-powered provider search with debug logging."""

    def __init__(self):
        """Initialize OpenAI-compatible client."""
        client_kwargs = {
            "api_key": settings.OPENAI_API_KEY or "dummy-key",
        }

        # Support custom base URL (e.g., DeepInfra, other providers)
        if settings.OPENAI_API_BASE:
            client_kwargs["base_url"] = settings.OPENAI_API_BASE

        self.client = AsyncOpenAI(**client_kwargs)
        self.embedding_model = settings.OPENAI_EMBEDDING_MODEL
        self.llm_model = settings.OPENAI_LLM_MODEL

        logger.info(f"[SEARCH SERVICE] Initialized with embedding_model={self.embedding_model}, llm_model={self.llm_model}")
        logger.info(f"[SEARCH SERVICE] API Base: {settings.OPENAI_API_BASE or 'default (OpenAI)'}")
        logger.info(f"[SEARCH SERVICE] API Key configured: {bool(settings.OPENAI_API_KEY and settings.OPENAI_API_KEY != 'dummy-key')}")

    async def extract_search_intent(
        self, query_text: str, document_text: Optional[str] = None
    ) -> Dict[str, Any]:
        """Use LLM to extract structured intent from search query."""
        logger.info(f"[SEARCH INTENT] Starting extraction for query: '{query_text[:100]}...'")

        combined_text = query_text
        if document_text:
            combined_text += f"\n\nDocument content:\n{document_text[:4000]}"
            logger.info(f"[SEARCH INTENT] Including document text ({len(document_text)} chars)")

        prompt = f"""
        Analyze this engineering services search query and extract structured information.

        Query: {combined_text}

        Return ONLY a JSON object with these fields:
        - requires_engineering: 1 if engineering services needed, 0 otherwise
        - requires_mechanical: 1 if mechanical engineering focus, 0 otherwise
        - requires_software: 1 if software/simulation tools mentioned, 0 otherwise
        - software_mentioned: list of software tools mentioned (e.g., ["ANSYS", "SolidWorks"])
        - inferred_specialty: primary engineering specialty inferred (string)
        - capabilities_needed: list of required capabilities
        - tollgate_phases: list of tollgate phases mentioned (TG0, TG1, TG3, TG4, TG6)

        Return valid JSON only, no markdown formatting.
        """

        try:
            logger.info(f"[SEARCH INTENT] Calling LLM API (model={self.llm_model})")
            response = await self.client.chat.completions.create(
                model=self.llm_model,
                messages=[
                    {"role": "system", "content": "You are an engineering services analyzer. Return only valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,
                max_tokens=500
            )

            content = response.choices[0].message.content.strip()
            logger.info(f"[SEARCH INTENT] LLM response received: {len(content)} chars")

            # Clean up markdown if present
            if content.startswith("```json"):
                content = content[7:]
            if content.startswith("```"):
                content = content[3:]
            if content.endswith("```"):
                content = content[:-3]
            content = content.strip()

            intent = json.loads(content)
            logger.info(f"[SEARCH INTENT] Parsed intent: {json.dumps(intent)}")
            return intent

        except json.JSONDecodeError as e:
            logger.error(f"[SEARCH INTENT] Failed to parse LLM response as JSON: {str(e)}")
            logger.error(f"[SEARCH INTENT] Raw response: {content[:500]}")
            # Return default intent on parse failure
            return {
                "requires_engineering": 1,
                "requires_mechanical": 0,
                "requires_software": 0,
                "software_mentioned": [],
                "inferred_specialty": "",
                "capabilities_needed": [],
                "tollgate_phases": []
            }
        except Exception as e:
            logger.error(f"[SEARCH INTENT] LLM API error: {str(e)}", exc_info=True)
            raise

    async def generate_embedding(self, text: str) -> List[float]:
        """Generate vector embedding for text."""
        logger.info(f"[EMBEDDING] Generating embedding for text ({len(text)} chars, model={self.embedding_model})")

        if not settings.OPENAI_API_KEY or settings.OPENAI_API_KEY == "dummy-key":
            logger.error("[EMBEDDING] No API key configured!")
            raise ValueError("OpenAI API key not configured")

        try:
            response = await self.client.embeddings.create(
                model=self.embedding_model,
                input=text[:8000]  # Limit input size
            )
            embedding = response.data[0].embedding
            logger.info(f"[EMBEDDING] Generated embedding with {len(embedding)} dimensions")
            return embedding
        except Exception as e:
            logger.error(f"[EMBEDDING] Failed to generate embedding: {str(e)}", exc_info=True)
            raise

    async def search_providers(
        self,
        db: AsyncSession,
        query: str,
        filters: Optional[Dict[str, Any]] = None,
        limit: int = 50
    ) -> List[Any]:
        """Execute AI-powered provider search with detailed logging."""
        logger.info(f"[SEARCH] Starting search: query='{query[:100]}...', filters={filters}, limit={limit}")

        filters = filters or {}

        # Extract structured intent
        try:
            intent = await self.extract_search_intent(query)
            logger.info(f"[SEARCH] Intent extracted successfully")
        except Exception as e:
            logger.error(f"[SEARCH] Intent extraction failed: {str(e)}")
            intent = {"requires_engineering": 1, "requires_mechanical": 0, "inferred_specialty": "", "software_mentioned": []}

        # Generate query embedding
        try:
            query_embedding = await self.generate_embedding(query)
            logger.info(f"[SEARCH] Query embedding generated")
        except Exception as e:
            logger.error(f"[SEARCH] Embedding generation failed: {str(e)}")
            return []

        # Build and execute database query
        embedding_str = f"[{','.join(str(x) for x in query_embedding)}]"

        try:
            logger.info(f"[SEARCH] Querying database with vector similarity")
            stmt = select(
                Provider,
                (1 - Provider.embedding.cosine_distance(embedding_str)).label("similarity")
            ).where(
                Provider.embedding.isnot(None)
            ).order_by(
                Provider.embedding.cosine_distance(embedding_str)
            ).limit(limit)

            result = await db.execute(stmt)
            rows = result.all()
            logger.info(f"[SEARCH] Database returned {len(rows)} rows")

            if len(rows) == 0:
                logger.warning(f"[SEARCH] No providers found with embeddings - checking if any providers have embeddings")
                count_result = await db.execute(select(Provider).where(Provider.embedding.isnot(None)))
                with_embeddings = len(count_result.scalars().all())
                logger.warning(f"[SEARCH] Providers with embeddings: {with_embeddings}")

        except Exception as e:
            logger.error(f"[SEARCH] Database query failed: {str(e)}", exc_info=True)
            return []

        # Score and rank providers
        matches = []
        logger.info(f"[SEARCH] Scoring {len(rows)} providers")

        for idx, (provider, similarity) in enumerate(rows):
            try:
                score_result = self._calculate_score(provider, intent, similarity)

                # Create a simple match object
                match_obj = type('Match', (), {
                    'provider': provider,
                    'score': score_result["total"],
                    'explanation': score_result["explanation"]
                })()
                matches.append(match_obj)

                if idx < 3:  # Log details for top 3
                    logger.info(f"[SEARCH] Provider {idx+1}: {provider.name}, score={score_result['total']}, similarity={similarity:.3f}")
            except Exception as e:
                logger.error(f"[SEARCH] Failed to score provider {provider.id}: {str(e)}")

        # Sort by score
        matches.sort(key=lambda x: x.score, reverse=True)
        logger.info(f"[SEARCH] Returning top {min(5, len(matches))} matches from {len(matches)} total")

        return matches[:5]

    def _calculate_score(
        self,
        provider: Provider,
        intent: Dict[str, Any],
        similarity: float
    ) -> Dict[str, Any]:
        """Calculate 100-point composite score for a provider match."""

        # Base similarity score (0-50 points for capabilities match)
        capabilities_score = min(50, int(similarity * 50))

        # Specialty match (0-25 points)
        specialty_score = 0
        inferred_specialty = intent.get("inferred_specialty", "").lower()
        if provider.primary_specialty and inferred_specialty:
            if inferred_specialty in provider.primary_specialty.lower():
                specialty_score = 25
            elif provider.secondary_specialties:
                secondary_match = any(
                    inferred_specialty in s.lower()
                    for s in (provider.secondary_specialties or [])
                )
                if secondary_match:
                    specialty_score = 20

        # Tier multiplier (5-25 points)
        tier_scores = {"A": 25, "B": 20, "C": 15, "D": 10, "E": 5}
        tier_score = tier_scores.get(provider.tier, 5)

        # Software match bonus (up to 10 bonus points)
        software_bonus = 0
        mentioned_software = intent.get("software_mentioned", [])
        if mentioned_software and provider.software_tools:
            matches = sum(
                1 for sw in mentioned_software
                if any(sw.lower() in pt.lower() for pt in provider.software_tools)
            )
            software_bonus = min(10, matches * 3)

        total = min(100, capabilities_score + specialty_score + tier_score + software_bonus)

        # Generate explanation
        explanation_parts = []
        if specialty_score >= 20:
            explanation_parts.append(f"Strong specialty match in {provider.primary_specialty}")
        if capabilities_score >= 35:
            explanation_parts.append("High capability alignment")
        if software_bonus > 0:
            explanation_parts.append(f"Uses relevant software tools")
        explanation_parts.append(f"Tier {provider.tier} provider")

        return {
            "total": total,
            "specialty": specialty_score,
            "capabilities": capabilities_score,
            "tier": tier_score,
            "software_bonus": software_bonus,
            "explanation": "; ".join(explanation_parts) if explanation_parts else "General match"
        }

    async def generate_provider_embedding(
        self,
        provider: Provider
    ) -> List[float]:
        """Generate embedding for a provider's business description."""
        # Combine relevant fields for embedding
        text_parts = [
            provider.name or "",
            provider.primary_specialty or "",
            provider.business_description or "",
            " ".join(provider.capabilities or []),
            " ".join(provider.specialties or []),
        ]
        text = " ".join(filter(None, text_parts))

        return await self.generate_embedding(text)


# Global instance
search_service = SearchService()


# Standalone function wrappers for backward compatibility and imports

async def calculate_match_score(provider, intent, similarity):
    """Calculate composite match score for a provider."""
    service = SearchService()
    return service._calculate_score(provider, intent, similarity)


async def check_search_quota(db, user=None, ip_address=None):
    """Check if user has search quota remaining."""
    from app.models.search import IPUsageTracking
    from datetime import datetime

    user_id = user.id if user else None
    current_month = datetime.utcnow().strftime("%Y-%m")

    logger.info(f"[QUOTA CHECK] user_id={user_id}, ip={ip_address}")

    if user_id:
        # Check user quota
        from app.models.user import User
        result = await db.execute(
            select(User.search_quota_used, User.search_quota_limit, User.search_quota_reset_at)
            .where(User.id == user_id)
        )
        user_row = result.first()
        if user_row:
            quota_used, quota_limit, reset_at = user_row
            remaining = max(0, quota_limit - quota_used)
            logger.info(f"[QUOTA CHECK] User {user_id}: used={quota_used}, limit={quota_limit}, remaining={remaining}")
            return remaining > 0, remaining
    elif ip_address:
        # Check IP quota for anonymous users
        result = await db.execute(
            select(IPUsageTracking)
            .where(
                IPUsageTracking.ip_address == ip_address,
                IPUsageTracking.usage_month == current_month
            )
        )
        tracking = result.scalar_one_or_none()

        if not tracking:
            logger.info(f"[QUOTA CHECK] IP {ip_address}: new this month, 3 searches available")
            return True, 3

        remaining = max(0, 3 - tracking.search_count)
        logger.info(f"[QUOTA CHECK] IP {ip_address}: used={tracking.search_count}, remaining={remaining}")
        return remaining > 0, remaining

    logger.warning(f"[QUOTA CHECK] No user_id or ip_address provided")
    return False, 0


async def extract_structured_intent(query: str):
    """Extract structured intent from natural language query."""
    service = SearchService()
    return await service.extract_search_intent(query)


async def generate_embedding(text: str):
    """Generate vector embedding for text."""
    service = SearchService()
    return await service.generate_embedding(text)


async def increment_search_quota(db, user_id=None, ip_address=None):
    """Increment search quota usage."""
    from app.models.search import IPUsageTracking
    from datetime import datetime

    current_month = datetime.utcnow().strftime("%Y-%m")

    if user_id:
        from app.models.user import User
        await db.execute(
            text("""
                UPDATE users 
                SET search_quota_used = search_quota_used + 1,
                    updated_at = NOW()
                WHERE id = :user_id
            """),
            {"user_id": user_id}
        )
        logger.info(f"[QUOTA] Incremented user {user_id} search count")
    elif ip_address:
        # Upsert IP usage tracking
        result = await db.execute(
            select(IPUsageTracking)
            .where(
                IPUsageTracking.ip_address == ip_address,
                IPUsageTracking.usage_month == current_month
            )
        )
        tracking = result.scalar_one_or_none()

        if tracking:
            tracking.search_count += 1
            tracking.updated_at = datetime.utcnow()
            logger.info(f"[QUOTA] Incremented IP {ip_address} search count to {tracking.search_count}")
        else:
            tracking = IPUsageTracking(
                ip_address=ip_address,
                usage_month=current_month,
                search_count=1
            )
            db.add(tracking)
            logger.info(f"[QUOTA] Created new IP tracking for {ip_address}")

    await db.commit()
