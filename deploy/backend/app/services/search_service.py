"""Search service for ProReadyEngineer.

Spec pipeline (Section 11):
 1. Normalize input
 2. LLM structured intent extraction
 3. Hard filters
 4. Embed query
 5. pgvector cosine pre-filter top-50
 6. 100-point score: Specialty(25) + Capabilities(50) + Tier(5-25) + SoftwareBonus(0-10)
 7. Return top-5
 8. Record diagnostics
"""
import json
import logging
import math
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession
from openai import AsyncOpenAI

from app.core.config import settings
from app.models.provider import Provider

logger = logging.getLogger(__name__)


@dataclass
class SearchResultItem:
    """Returned by search_providers."""
    provider: Any
    score: float
    explanation: str
    specialty_score: float = 0.0
    capabilities_score: float = 0.0
    tier_score: float = 0.0
    software_bonus: float = 0.0
    similarity: float = 0.0
    fallback_reason: Optional[str] = None


def _has_api_key() -> bool:
    key = getattr(settings, 'OPENAI_API_KEY', '') or ''
    return bool(key) and key not in ('dummy-key', '')


def _get_client() -> AsyncOpenAI:
    kwargs: Dict[str, Any] = {'api_key': getattr(settings, 'OPENAI_API_KEY', 'dummy-key') or 'dummy-key'}
    base = getattr(settings, 'OPENAI_API_BASE', '') or ''
    if base:
        kwargs['base_url'] = base
    return AsyncOpenAI(**kwargs)


def _embedding_model() -> str:
    model = getattr(settings, 'OPENAI_EMBEDDING_MODEL', 'text-embedding-3-small') or 'text-embedding-3-small'
    base = getattr(settings, 'OPENAI_API_BASE', '') or ''
    openai_only = {'text-embedding-3-small', 'text-embedding-ada-002', 'text-embedding-3-large'}
    if 'deepinfra' in base.lower() and model in openai_only:
        return 'BAAI/bge-large-en-v1.5'
    return model


def _llm_model() -> str:
    return getattr(settings, 'OPENAI_LLM_MODEL', None) or 'moonshotai/kimi-k2.5'


def _safe_list(val: Any) -> List[str]:
    if val is None:
        return []
    if isinstance(val, list):
        return [str(v) for v in val]
    if isinstance(val, str):
        try:
            parsed = json.loads(val)
            if isinstance(parsed, list):
                return [str(v) for v in parsed]
        except Exception:
            pass
        return [val] if val.strip() else []
    return [str(val)]


def _safe_str(val: Any) -> str:
    if val is None:
        return ''
    if isinstance(val, list):
        return ' '.join(str(v) for v in val)
    return str(val)


def _display_name(p) -> str:
    return (_safe_str(getattr(p, 'firm_name', ''))
            or _safe_str(getattr(p, 'name', ''))
            or f'Provider #{p.id}')


def _normalize_query(query: str) -> str:
    return re.sub(r'\s+', ' ', query.strip())


_DEFAULT_INTENT: Dict[str, Any] = {
    'requires_engineering': 1,
    'requires_mechanical': 0,
    'software_mentioned': [],
    'inferred_specialty': '',
    'capabilities_needed': [],
    'inferred_keywords': [],
}


def _simple_keywords(query: str) -> List[str]:
    STOP = {
        'the', 'a', 'an', 'and', 'or', 'for', 'of', 'in', 'on', 'at', 'to', 'with',
        'that', 'this', 'from', 'are', 'was', 'has', 'have', 'been', 'will', 'can',
        'may', 'our', 'its', 'all', 'any', 'use', 'using', 'how', 'what', 'which',
        'is', 'it', 'as', 'by', 'be', 'do', 'if', 'we', 'my', 'so', 'up', 'no',
    }
    words = re.findall(r'[a-z0-9]+', query.lower())
    return [w for w in words if w not in STOP and len(w) > 2][:10]


async def extract_structured_intent(
    query: str,
    document_text: Optional[str] = None,
) -> Dict[str, Any]:
    """Step 2: LLM structured intent. Falls back to keywords on any failure."""
    if not _has_api_key():
        logger.info('[INTENT] No API key - using keyword extraction')
        return {**_DEFAULT_INTENT, 'inferred_keywords': _simple_keywords(query)}

    norm = _normalize_query(query)
    combined = norm
    if document_text:
        combined = norm + '\n\nDocument:\n' + document_text[:4000]

    prompt_parts = [
        'Analyze this engineering services search query and extract structured information.',
        '',
        'Query: ' + combined,
        '',
        'Return ONLY a JSON object with exactly these fields:',
        '{',
        '  "requires_engineering": 1 if engineering services needed ELSE 0,',
        '  "requires_mechanical": 1 if mechanical engineering focus ELSE 0,',
        '  "software_mentioned": [list of software/simulation tools explicitly named],',
        '  "inferred_specialty": "primary engineering specialty as short phrase",',
        '  "capabilities_needed": [list of specific technical capabilities required],',
        '  "inferred_keywords": [5-10 important domain keywords for text matching]',
        '}',
        '',
        'Return valid JSON only. No markdown. No explanation.',
    ]
    prompt = '\n'.join(prompt_parts)

    try:
        client = _get_client()
        model  = _llm_model()
        logger.info(f'[INTENT] Calling LLM model={model} query={query[:80]}')
        response = await client.chat.completions.create(
            model=model,
            messages=[
                {'role': 'system', 'content': 'You are an engineering services analyzer. Return only valid JSON.'},
                {'role': 'user',   'content': prompt},
            ],
            temperature=0.1,
            max_tokens=600,
        )
        raw = response.choices[0].message.content.strip()
        raw = re.sub(r'^```(?:json)?\s*', '', raw)
        raw = re.sub(r'\s*```$', '', raw).strip()
        intent = json.loads(raw)
        for k, v in _DEFAULT_INTENT.items():
            intent.setdefault(k, v)
        logger.info(
            '[INTENT] specialty=%s kw=%s',
            str(intent.get('inferred_specialty', ''))[:60],
            intent.get('inferred_keywords', [])[:5],
        )
        return intent
    except json.JSONDecodeError as exc:
        logger.warning(f'[INTENT] JSON parse error ({exc}) - using keyword fallback')
    except Exception as exc:
        logger.warning(f'[INTENT] LLM error ({exc}) - using keyword fallback')

    return {**_DEFAULT_INTENT, 'inferred_keywords': _simple_keywords(query)}


async def generate_embedding(text_input: str) -> List[float]:
    """Step 4: Generate vector embedding. Raises ValueError if no API key."""
    if not _has_api_key():
        raise ValueError('No AI API key configured - embeddings unavailable')
    client = _get_client()
    model  = _embedding_model()
    logger.info(f'[EMBED] model={model}, input_len={len(text_input)}')
    try:
        resp = await client.embeddings.create(model=model, input=text_input[:8000])
        vec  = resp.data[0].embedding
        logger.info(f'[EMBED] Generated {len(vec)}-dim vector')
        return vec
    except Exception as exc:
        logger.error(f'[EMBED] Failed: {exc}', exc_info=True)
        raise


def _provider_embed_text(p) -> str:
    """Canonical provider text for embedding."""
    parts = [
        _safe_str(getattr(p, 'firm_name', '') or getattr(p, 'name', '')),
        _safe_str(getattr(p, 'primary_specialty', '')),
        _safe_str(getattr(p, 'business_description', '')),
        ' '.join(_safe_list(getattr(p, 'capabilities', []))),
        ' '.join(_safe_list(getattr(p, 'specialties', []))),
        ' '.join(_safe_list(getattr(p, 'software_tools', []))),
        _safe_str(getattr(p, 'notable_clients', '')),
    ]
    return ' '.join(x for x in parts if x).strip()


def _tier_score(provider) -> float:
    tier_map = {'A': 25.0, 'B': 20.0, 'C': 15.0, 'D': 10.0, 'E': 5.0}
    tier = (
        getattr(provider, 'business_evaluation_tier', None)
        or getattr(provider, 'tier', None)
    )
    if tier:
        return tier_map.get(str(tier).strip().upper(), 5.0)
    return 5.0


def _specialty_score(provider, intent: Dict[str, Any]) -> float:
    """Specialty Match 0-25 pts."""
    inferred   = _safe_str(intent.get('inferred_specialty', '')).lower()
    cap_needed = [c.lower() for c in _safe_list(intent.get('capabilities_needed', []))]
    if not inferred and not cap_needed:
        return 0.0
    primary   = _safe_str(getattr(provider, 'primary_specialty', '')).lower()
    secondary = ' '.join(_safe_list(getattr(provider, 'secondary_specialties', []))).lower()
    combined  = primary + ' ' + secondary
    score = 0.0
    if inferred:
        words = [w for w in re.findall(r'[a-z0-9]+', inferred) if len(w) > 3]
        if words:
            hits  = sum(1 for w in words if w in combined)
            ratio = hits / len(words)
            if ratio >= 0.8:
                score = max(score, 25.0)
            elif ratio >= 0.5:
                score = max(score, 20.0)
            elif ratio >= 0.25:
                score = max(score, 10.0)
    if cap_needed:
        cap_words = []
        for cap in cap_needed:
            cap_words.extend(w for w in re.findall(r'[a-z0-9]+', cap) if len(w) > 3)
        if cap_words:
            hits      = sum(1 for w in cap_words if w in combined)
            cap_score = min(20.0, (hits / len(cap_words)) * 20.0)
            score     = max(score, cap_score)
    return score


def _capabilities_score_keyword(provider, intent: Dict[str, Any]) -> float:
    """Keyword-based capabilities score 0-50 pts (used when no embeddings)."""
    keywords = [k.lower() for k in _safe_list(intent.get('inferred_keywords', []))]
    if not keywords:
        spec = _safe_str(intent.get('inferred_specialty', '')).lower()
        keywords = [w for w in re.findall(r'[a-z0-9]+', spec) if len(w) > 3]
    if not keywords:
        return 10.0
    name_text = (_safe_str(getattr(provider, 'firm_name', '')) + ' '
                 + _safe_str(getattr(provider, 'name', ''))).lower()
    desc_text = _safe_str(getattr(provider, 'business_description', '')).lower()
    cap_text  = ' '.join(_safe_list(getattr(provider, 'capabilities', []))).lower()
    spec_text = ' '.join(_safe_list(getattr(provider, 'specialties', []))).lower()
    raw = 0.0
    for kw in keywords:
        if kw in name_text: raw += 5.0
        if kw in cap_text:  raw += 3.0
        if kw in spec_text: raw += 3.0
        if kw in desc_text: raw += 2.0
    max_raw = len(keywords) * 13.0
    if max_raw == 0:
        return 10.0
    return min(50.0, (raw / max_raw) * 50.0)


def _software_bonus(provider, intent: Dict[str, Any]) -> float:
    """Software Bonus 0-10 pts (3 pts/match, capped at 10)."""
    mentioned = [s.lower() for s in _safe_list(intent.get('software_mentioned', []))]
    if not mentioned:
        return 0.0
    tools = [t.lower() for t in _safe_list(getattr(provider, 'software_tools', []))]
    if not tools:
        return 0.0
    hits = sum(1 for s in mentioned if any(s in t or t in s for t in tools))
    return min(10.0, hits * 3.0)


def calculate_match_score(
    provider,
    intent: Dict[str, Any],
    similarity: float = 0.0,
) -> Dict[str, float]:
    """Compute deterministic 100-point composite score."""
    tier_pts      = _tier_score(provider)
    specialty_pts = _specialty_score(provider, intent)
    if similarity > 0.0:
        cap_pts = round(similarity * 50.0, 2)
    else:
        cap_pts = _capabilities_score_keyword(provider, intent)
    sw_bonus = _software_bonus(provider, intent)
    total    = min(100.0, specialty_pts + cap_pts + tier_pts + sw_bonus)
    return {
        'total':          round(total, 2),
        'specialty':      round(specialty_pts, 2),
        'capabilities':   round(cap_pts, 2),
        'tier':           round(tier_pts, 2),
        'software_bonus': round(sw_bonus, 2),
        'similarity':     round(similarity, 4),
    }


def _build_explanation(name: str, scores: Dict[str, float], intent: Dict[str, Any]) -> str:
    """Human-readable explanation grounded in actual scoring inputs (spec 11.12)."""
    specialty = intent.get('inferred_specialty', '') or 'engineering services'
    parts = [
        f"{name} scored {scores['total']:.0f}/100.",
        f"Specialty match: {scores['specialty']:.0f}/25.",
        f"Capabilities match: {scores['capabilities']:.0f}/50",
    ]
    if scores['similarity'] > 0:
        parts[-1] += f" (semantic similarity {scores['similarity']:.3f})"
    parts[-1] += '.'
    parts.append(f"Tier score: {scores['tier']:.0f}/25.")
    if scores['software_bonus'] > 0:
        parts.append(f"Software tool bonus: +{scores['software_bonus']:.0f}.")
    parts.append(f"Matched on: {specialty}.")
    return ' '.join(parts)


async def check_search_quota(
    db: AsyncSession,
    user_id: Optional[int] = None,
    ip_address: Optional[str] = None,
) -> Dict[str, Any]:
    """Check caller search quota. Returns {allowed, remaining, limit, used}."""
    now = datetime.utcnow()
    if user_id is None:
        if not ip_address:
            return {'allowed': True, 'remaining': 3, 'limit': 3, 'used': 0}
        try:
            from app.models.search import IpUsageTracking
            month_str = now.strftime('%Y-%m')
            result = await db.execute(
                select(IpUsageTracking)
                .where(IpUsageTracking.ip_address == ip_address)
                .where(IpUsageTracking.usage_month == month_str)
            )
            record = result.scalar_one_or_none()
            used  = record.search_count if record else 0
            limit = 3
            return {'allowed': used < limit, 'remaining': max(0, limit - used), 'limit': limit, 'used': used}
        except Exception as exc:
            logger.warning(f'[QUOTA] IP tracking error: {exc}')
            return {'allowed': True, 'remaining': 3, 'limit': 3, 'used': 0}
    try:
        from app.models.user import User
        result = await db.execute(select(User).where(User.id == user_id))
        user   = result.scalar_one_or_none()
        if not user:
            return {'allowed': False, 'remaining': 0, 'limit': 0, 'used': 0}
        search_tier = getattr(user, 'search_tier', None)
        limit = 200 if search_tier == 2 else (100 if search_tier == 1 else 10)
        used     = getattr(user, 'monthly_search_count', 0) or 0
        reset_at = getattr(user, 'search_count_reset_at', None)
        if reset_at and hasattr(reset_at, 'month'):
            if reset_at.year != now.year or reset_at.month != now.month:
                used = 0
        return {'allowed': used < limit, 'remaining': max(0, limit - used), 'limit': limit, 'used': used}
    except Exception as exc:
        logger.warning(f'[QUOTA] User quota check error: {exc}')
        return {'allowed': True, 'remaining': 10, 'limit': 10, 'used': 0}


async def increment_search_quota(
    db: AsyncSession,
    user_id: Optional[int] = None,
    ip_address: Optional[str] = None,
) -> None:
    """Increment search usage counter for the caller."""
    now = datetime.utcnow()
    if user_id is None:
        if not ip_address:
            return
        try:
            from app.models.search import IpUsageTracking
            month_str = now.strftime('%Y-%m')
            result = await db.execute(
                select(IpUsageTracking)
                .where(IpUsageTracking.ip_address == ip_address)
                .where(IpUsageTracking.usage_month == month_str)
            )
            record = result.scalar_one_or_none()
            if record:
                record.search_count = (record.search_count or 0) + 1
                record.updated_at   = now
            else:
                db.add(IpUsageTracking(
                    ip_address=ip_address,
                    usage_month=month_str,
                    search_count=1,
                    created_at=now,
                    updated_at=now,
                ))
            await db.commit()
        except Exception as exc:
            logger.warning(f'[QUOTA] IP increment error: {exc}')
            await db.rollback()
        return
    try:
        from app.models.user import User
        result = await db.execute(select(User).where(User.id == user_id))
        user   = result.scalar_one_or_none()
        if not user:
            return
        reset_at = getattr(user, 'search_count_reset_at', None)
        if reset_at and hasattr(reset_at, 'month'):
            if reset_at.year != now.year or reset_at.month != now.month:
                user.monthly_search_count  = 1
                user.search_count_reset_at = now
            else:
                user.monthly_search_count = (user.monthly_search_count or 0) + 1
        else:
            user.monthly_search_count  = (getattr(user, 'monthly_search_count', 0) or 0) + 1
            user.search_count_reset_at = now
        await db.commit()
    except Exception as exc:
        logger.warning(f'[QUOTA] User increment error: {exc}')
        await db.rollback()


async def _fetch_candidates(
    db: AsyncSession,
    intent: Dict[str, Any],
    filters: dict,
    query_vec: Optional[List[float]],
    limit: int = 50,
) -> tuple:
    """Steps 3, 5: hard filters + pgvector pre-filter. Returns (rows, used_vector, fallback_reason)."""
    from sqlalchemy import text
    fallback_reason: Optional[str] = None

    base_filters = []
    if intent.get('requires_engineering', 1) == 1:
        base_filters.append('is_engineering_service = 1')

    software_mentioned = [s.lower() for s in _safe_list(intent.get('software_mentioned', []))]
    software_filter_active = bool(software_mentioned)

    async def _run_query(extra_where: str = '', vector_col: str = '') -> list:
        where_parts = list(base_filters)
        if extra_where:
            where_parts.append(extra_where)
        where_clause = ('WHERE ' + ' AND '.join(where_parts)) if where_parts else ''

        if vector_col:
            sql = text(f"""
                SELECT p.*,
                       1 - (p.embedding <=> CAST(:vec AS vector)) AS cosine_similarity
                FROM providers p
                {where_clause}
                ORDER BY cosine_similarity DESC
                LIMIT :lim
            """)
            import json as _json
            result = await db.execute(sql, {'vec': _json.dumps(query_vec), 'lim': limit})
        else:
            sql = text(f"SELECT p.* FROM providers p {where_clause} LIMIT :lim")
            result = await db.execute(sql, {'lim': limit})
        return result.mappings().all()

    used_vector = False
    rows = []

    if query_vec:
        try:
            rows = await _run_query(vector_col='embedding')
            used_vector = True
            logger.info(f'[SEARCH] pgvector pre-filter returned {len(rows)} candidates')
        except Exception as exc:
            logger.warning(f'[SEARCH] pgvector failed ({exc}), falling back to text query')
            used_vector = False

    if not used_vector:
        try:
            rows = await _run_query()
            logger.info(f'[SEARCH] text/filter query returned {len(rows)} candidates')
        except Exception as exc:
            logger.error(f'[SEARCH] Candidate query failed: {exc}')
            rows = []

    return rows, used_vector, fallback_reason


class _ProviderProxy:
    """Wrap a sqlalchemy RowMapping so provider fields work via attribute access."""
    def __init__(self, mapping):
        self._m = mapping
    def __getattr__(self, name):
        try:
            return self._m[name]
        except KeyError:
            return None
    @property
    def id(self):
        return self._m.get('id')


async def search_providers(
    db: AsyncSession,
    query: str,
    filters: dict = None,
    limit: int = 50,
) -> List[SearchResultItem]:
    """Full spec-compliant search pipeline. Returns list of SearchResultItem."""
    if filters is None:
        filters = {}

    norm_query = _normalize_query(query)
    logger.info(f'[SEARCH] query={norm_query[:100]}')

    # Step 2 - LLM intent extraction
    intent = await extract_structured_intent(norm_query)
    fallback_reason: Optional[str] = None

    # Step 4 - Embed query
    query_vec: Optional[List[float]] = None
    if _has_api_key():
        try:
            query_vec = await generate_embedding(norm_query)
        except Exception as exc:
            logger.warning(f'[SEARCH] Embedding failed ({exc}), using keyword scoring')
            if fallback_reason is None:
                fallback_reason = f'embedding_failed:{exc}'

    # Steps 3+5 - Hard filters + pgvector candidates
    try:
        rows, used_vector, fetch_fallback = await _fetch_candidates(
            db, intent, filters, query_vec, limit=max(limit, 50)
        )
        if fetch_fallback:
            fallback_reason = fallback_reason or fetch_fallback
    except Exception as exc:
        logger.error(f'[SEARCH] Candidate fetch error: {exc}')
        rows = []
        used_vector = False

    if not rows:
        logger.info('[SEARCH] No candidates found, returning empty')
        return []

    # Step 6 - Score each candidate
    scored: List[tuple] = []
    for row in rows:
        try:
            provider = _ProviderProxy(row)
            similarity = float(row.get('cosine_similarity', 0.0) or 0.0) if used_vector else 0.0
            scores = calculate_match_score(provider, intent, similarity=similarity)
            name = _display_name(provider)
            explanation = _build_explanation(name, scores, intent)
            scored.append((
                scores['total'],
                SearchResultItem(
                    provider=provider,
                    score=scores['total'],
                    explanation=explanation,
                    specialty_score=scores['specialty'],
                    capabilities_score=scores['capabilities'],
                    tier_score=scores['tier'],
                    software_bonus=scores['software_bonus'],
                    similarity=scores['similarity'],
                    fallback_reason=fallback_reason,
                ),
            ))
        except Exception as exc:
            logger.warning(f'[SEARCH] Scoring error for row: {exc}')

    # Sort descending by total score
    scored.sort(key=lambda t: t[0], reverse=True)

    # Step 7 - Return top 5 (spec 11.10)
    results = [item for _, item in scored[:5]]

    logger.info(
        '[SEARCH] top-%d results: %s',
        len(results),
        [(r.provider.id, round(r.score, 1)) for r in results],
    )
    return results
