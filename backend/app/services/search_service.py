"""Search service for provider matching using AI embeddings with comprehensive debugging."""

import json
import logging
from typing import List, Optional, Dict, Any, Tuple
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

        # DeepInfra requires BAAI/bge-large-en-v1.5 (1024-dim), not text-embedding-3-small (OpenAI-only)
        if settings.OPENAI_API_BASE and 'deepinfra' in settings.OPENAI_API_BASE.lower():
            if self.embedding_model in ('text-embedding-3-small', 'text-embedding-ada-002', 'text-embedding-3-large'):
                self.embedding_model = 'BAAI/bge-large-en-v1.5'
                logger.info('[SEARCH SERVICE] DeepInfra detected: overriding embedding model to BAAI/bge-large-en-v1.5')
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
    """NON-FATAL: allows search even if quota check errors."""
    try:
        return await _check_search_quota_impl(db, user, ip_address)
    except Exception as exc:
        logger.error("[QUOTA] Non-fatal, allowing search: " + str(exc))
        return True, 10


async def _check_search_quota_impl(db, user=None, ip_address=None):
    """Internal impl - may raise."""
    from app.models.search import IPUsageTracking
    from app.models.user import User
    from app.models.payment import Subscription, SubscriptionType, SubscriptionStatus
    from datetime import datetime
    user_id = user.id if user else None
    current_month = datetime.utcnow().strftime("%Y-%m")
    logger.info(f"[QUOTA] user_id={user_id} ip={ip_address}")
    if user_id:
        result = await db.execute(
            select(User.monthly_search_count, User.search_count_reset_at)
            .where(User.id == user_id)
        )
        user_row = result.first()
        quota_limit = 10
        try:
            sub_res = await db.execute(
                select(Subscription).where(
                    Subscription.user_id == user_id,
                    Subscription.subscription_type.in_([
                        SubscriptionType.SEARCH_TIER_1,
                        SubscriptionType.SEARCH_TIER_2]),
                    Subscription.subscription_status == SubscriptionStatus.ACTIVE
                ).order_by(Subscription.created_at.desc())
            )
            sub = sub_res.scalars().first()
            if sub:
                if sub.subscription_type == SubscriptionType.SEARCH_TIER_1: quota_limit = 100
                elif sub.subscription_type == SubscriptionType.SEARCH_TIER_2: quota_limit = 200
        except Exception as e:
            logger.warning(f"[QUOTA] sub lookup failed (non-fatal): {e}")
        if user_row:
            used = user_row[0] or 0
            remaining = max(0, quota_limit - used)
            return remaining > 0, remaining
        return True, quota_limit
    elif ip_address:
        res = await db.execute(
            select(IPUsageTracking).where(
                IPUsageTracking.ip_address == ip_address,
                IPUsageTracking.usage_month == current_month)
        )
        tracking = res.scalar_one_or_none()
        if not tracking: return True, 3
        remaining = max(0, 3 - tracking.search_count)
        return remaining > 0, remaining
    return True, 3

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
        from sqlalchemy import update as sa_update
        await db.execute(
            sa_update(User)
            .where(User.id == user_id)
            .values(
                monthly_search_count=User.monthly_search_count + 1,
                updated_at=datetime.utcnow()
            )
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



# Standalone function for import compatibility
async def search_providers(
    db: AsyncSession,
    query: str,
    filters: dict = None,
    limit: int = 50
) -> List[Any]:
    """
    Search providers using embeddings and return ranked results.
    Returns a list of objects with .provider, .score, and .explanation attributes.
    Falls back to keyword search when no API key or no embeddings available.
    """
    from dataclasses import dataclass
    from sqlalchemy import or_, and_

    @dataclass
    class SearchResultItem:
        provider: Provider
        score: float
        explanation: str

    logger.info(f"[SEARCH] Starting search: query='{query[:100]}'..., filters={filters}, limit={limit}")

    async def keyword_fallback(reason: str, score: float = 50.0) -> List[SearchResultItem]:
        """Keyword-based fallback search with per-provider relevance scoring."""
        logger.info(f"[SEARCH FALLBACK] Reason: {reason}")
        # Filter stop words AND common generic engineering terms that match everyone
        STOP_WORDS = {
            'engineering', 'engineer', 'engineers', 'services', 'service',
            'solutions', 'solution', 'company', 'companies', 'corp', 'corporation',
            'inc', 'llc', 'ltd', 'group', 'firm', 'firms', 'design', 'designs',
            'the', 'and', 'for', 'with', 'that', 'this', 'from', 'are', 'was',
            'has', 'have', 'been', 'will', 'can', 'may', 'our', 'your', 'its',
            'all', 'any', 'new', 'use', 'used', 'using', 'project', 'projects',
            'management', 'consulting', 'consultant', 'technical', 'technology',
            'professional', 'systems', 'system', 'analysis', 'support'
        }
        raw_terms = [t.lower() for t in query.lower().split() if len(t) > 2]
        terms = [t for t in raw_terms if t not in STOP_WORDS] or raw_terms  # fallback to raw if all filtered
        logger.info(f"[SEARCH FALLBACK] Search terms: {terms}")

        eng_filter = Provider.is_engineering_service == 1

        def _build_kw_stmt(apply_eng: bool):
            conds = []
            for term in terms[:6]:
                conds.append(Provider.name.ilike(f"%{term}%"))
                conds.append(Provider.firm_name.ilike(f"%{term}%"))
                conds.append(Provider.business_description.ilike(f"%{term}%"))
                conds.append(Provider.primary_specialty.ilike(f"%{term}%"))
                conds.append(Provider.notable_clients.ilike(f"%{term}%"))
            # Wider candidate pool for Python-side re-ranking
            q = (select(Provider)
                 .order_by(Provider.business_evaluation_tier.asc().nullslast())
                 .limit(limit * 4))
            if conds and apply_eng:
                return q.where(and_(eng_filter, or_(*conds)))
            if conds:
                return q.where(or_(*conds))
            if apply_eng:
                return q.where(eng_filter)
            return q

        def _relevance_score(p: Provider) -> float:
            """Weighted term-match: name/firm 3x, specialty 2x, desc/caps 1x."""
            if not terms:
                return 20.0
            weighted_hits = 0
            name_text = ((p.name or "") + " " + (p.firm_name or "")).lower()
            spec_text  = (p.primary_specialty or "").lower()
            desc_text  = (p.business_description or "").lower()
            if p.capabilities:
                cap_text = (
                    " ".join(p.capabilities).lower()
                    if isinstance(p.capabilities, list)
                    else str(p.capabilities).lower()
                )
            else:
                cap_text = ""
            for term in terms:
                if term in name_text:  weighted_hits += 3  # name match
                if term in spec_text:  weighted_hits += 2  # specialty match
                if term in desc_text:  weighted_hits += 1  # description match
                if term in cap_text:   weighted_hits += 1  # capabilities match
            # Normalize: max possible hits per term = 3+2+1+1=7; cap at 90
            if not terms:
                return 20.0
            max_possible = len(terms) * 7
            if max_possible == 0:
                return 20.0
            pct = weighted_hits / max_possible  # 0.0 to 1.0
            return round(min(90.0, 20.0 + pct * 70.0), 1)  # 20-90 range

        # --- First pass: eng-filter + keyword match ---
        result = await db.execute(_build_kw_stmt(True))
        providers = result.scalars().all()
        logger.info(f"[SEARCH FALLBACK] kw eng-filter: {len(providers)} providers")

        # --- Second pass: no eng-filter ---
        if not providers:
            logger.warning("[SEARCH FALLBACK] eng=0, retrying without filter")
            result = await db.execute(_build_kw_stmt(False))
            providers = result.scalars().all()
            logger.info(f"[SEARCH FALLBACK] kw no-filter: {len(providers)} providers")

        # --- Last resort: return top-tier providers ---
        if not providers:
            result = await db.execute(
                select(Provider)
                .order_by(Provider.business_evaluation_tier.asc().nullslast())
                .limit(min(limit, 20))
            )
            providers = result.scalars().all()
            logger.info(f"[SEARCH FALLBACK] tier-only fallback: {len(providers)} providers")
            return [
                SearchResultItem(
                    provider=p,
                    score=20.0,
                    explanation=f"{reason} (no keyword match – tier fallback)",
                )
                for p in providers[:limit]
            ]

        # --- Score every candidate, sort descending ---
        scored: List[SearchResultItem] = []
        for p in providers:
            s = _relevance_score(p)
            scored.append(SearchResultItem(
                provider=p,
                score=s,
                explanation=f"{reason} (keyword relevance: {s:.0f}/90)",
            ))

        matching = [r for r in scored if r.score > 20.0] or scored
        matching.sort(key=lambda x: x.score, reverse=True)
        top_scores = [r.score for r in matching[:5]]
        logger.info(f"[SEARCH FALLBACK] top-5 relevance scores: {top_scores}")
        return matching[:limit]

    if not settings.OPENAI_API_KEY or settings.OPENAI_API_KEY in ("dummy-key", "", None):
        logger.info("[SEARCH] No AI key configured, using keyword fallback")
        return await keyword_fallback("Keyword search (no AI key configured)", score=50.0)

    # Generate embedding for the query
    try:
        service = SearchService()
        embedding = await service.generate_embedding(query)
        logger.info(f"[SEARCH] Generated embedding with {len(embedding)} dimensions")
    except Exception as e:
        logger.error(f"[SEARCH] Failed to generate embedding: {str(e)}")
        return await keyword_fallback("Keyword search (embedding error)", score=40.0)

    # Perform vector similarity search using pgvector
    try:
        # Build embedding string in pgvector format [x1,x2,...]
        embedding_values = ",".join(str(x) for x in embedding)
        embedding_str = f"[{embedding_values}]"

        # SOFT FILTER: eng first, relax if 0 results
        eng_sql = text("""
            SELECT id, 1 - (embedding <=> CAST(:embedding AS vector)) AS similarity
            FROM providers WHERE embedding IS NOT NULL AND is_engineering_service = 1
            ORDER BY embedding <=> CAST(:embedding AS vector) LIMIT :limit
        """)
        nofilt_sql = text("""
            SELECT id, 1 - (embedding <=> CAST(:embedding AS vector)) AS similarity
            FROM providers WHERE embedding IS NOT NULL
            ORDER BY embedding <=> CAST(:embedding AS vector) LIMIT :limit
        """)
        result = await db.execute(eng_sql, {"embedding": embedding_str, "limit": limit})
        rows = result.all()
        logger.info(f"[SEARCH] Vector eng-filter: {len(rows)} results")
        if not rows:
            logger.warning("[SEARCH] eng=0, retrying without filter")
            result = await db.execute(nofilt_sql, {"embedding": embedding_str, "limit": limit})
            rows = result.all()
            logger.info(f"[SEARCH] Vector no-filter: {len(rows)} results")
        if not rows:
            return await keyword_fallback("Keyword search (no embeddings yet)", score=35.0)


        # Fetch full provider objects
        provider_ids = [row[0] for row in rows]
        stmt = select(Provider).where(Provider.id.in_(provider_ids))
        result = await db.execute(stmt)
        providers_map = {p.id: p for p in result.scalars().all()}

        results = []
        for provider_id, similarity in rows:
            if provider_id in providers_map:
                provider = providers_map[provider_id]
                score = max(0.0, min(100.0, float(similarity) * 100))
                results.append(SearchResultItem(
                    provider=provider,
                    score=score,
                    explanation=f"AI similarity match (score: {score:.1f})"
                ))

        results.sort(key=lambda x: x.score, reverse=True)
        logger.info(f"[SEARCH] Returning {len(results)} AI-ranked results")
        return results

    except Exception as e:
        logger.error(f"[SEARCH] Vector search failed: {str(e)}", exc_info=True)
        try:
            await db.rollback()
        except Exception:
            pass
        return await keyword_fallback("Keyword search (vector error)", score=30.0)


# Standalone wrapper function for direct imports
_search_service_instance = None

