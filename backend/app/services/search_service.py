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


# --- Engineering synonym/expansion map ----------------------------------
_SYNONYMS = {
    "cfd":              ["computational fluid dynamics", "fluid simulation", "flow simulation",
                         "fluent", "openfoam", "star ccm", "cfx", "flow analysis"],
    "combustor":        ["combustion", "burner", "combustion chamber", "gas turbine combustion",
                         "flame", "ignition", "combustor design", "annular combustor"],
    "combustion":       ["combustor", "burner", "combustion chamber", "ignition", "flame",
                         "gas turbine combustion"],
    "gas turbine":      ["turbomachinery", "combustion turbine", "turbine engine",
                         "jet engine", "turbofan", "gas turbine combustion", "compressor"],
    "turbine":          ["turbomachinery", "gas turbine", "steam turbine", "compressor"],
    "fea":              ["finite element", "finite element analysis", "structural analysis",
                         "ansys", "abaqus", "nastran", "stress analysis"],
    "structural":       ["fea", "finite element", "stress analysis", "fatigue", "fracture"],
    "thermal":          ["heat transfer", "thermodynamics", "thermal analysis", "heat exchanger",
                         "cooling", "thermal fluid", "hvac"],
    "vibration":        ["modal analysis", "dynamics", "resonance", "acoustic", "noise"],
    "aerodynamics":     ["cfd", "fluid dynamics", "airflow", "drag", "lift", "wind tunnel"],
    "fatigue":          ["stress analysis", "fracture mechanics", "crack propagation",
                         "damage tolerance", "life prediction"],
    "failure analysis": ["root cause", "forensic engineering", "fracture", "corrosion"],
    "pressure vessel":  ["asme", "vessel design", "boiler", "code stamping"],
    "piping":           ["pipeline", "pipe stress", "flow assurance"],
    "machine learning": ["ai", "artificial intelligence", "deep learning", "neural network",
                         "data analytics", "physics informed"],
    "ai":               ["machine learning", "deep learning", "data analytics", "physics informed"],
    "nde":              ["non destructive", "inspection", "testing", "ultrasonic", "radiography"],
    "controls":         ["control systems", "pid", "plc", "scada", "automation"],
    "acoustics":        ["vibration", "noise", "sound"],
    "hvac":             ["mechanical", "thermal", "heat transfer", "cooling", "ventilation"],
}


def _expand_keywords(keywords):
    """Expand keywords using synonym map, returning deduplicated extended list."""
    expanded = list(keywords)
    for kw in keywords:
        kl = kw.lower()
        if kl in _SYNONYMS:
            expanded.extend(_SYNONYMS[kl])
        for syn_key, syn_vals in _SYNONYMS.items():
            if syn_key != kl and (syn_key in kl or kl in syn_key):
                expanded.extend(syn_vals)
                expanded.append(syn_key)
    seen = set()
    result = []
    for k in expanded:
        kl = k.lower().strip()
        if kl and kl not in seen:
            seen.add(kl)
            result.append(kl)
    return result



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
    team_text = str(getattr(provider, "team_members", "") or "").lower()
    proj_text = str(getattr(provider, "proven_experience_notable_projects", "") or "").lower()
    raw = 0.0
    for kw in keywords:
        if kw in name_text: raw += 5.0
        if kw in cap_text:  raw += 3.0
        if kw in spec_text: raw += 3.0
        if kw in desc_text:  raw += 2.0
        if kw in team_text:  raw += 4.0  # team member expertise
        if kw in proj_text:  raw += 2.0
    max_raw = len(keywords) * 21.0  # 5+3+3+2+4+2+2
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


async def _keyword_candidate_query(
    db,
    keywords,
    base_filters,
    limit,
):
    """Build keyword ILIKE SQL across ALL text fields including JSON arrays.
    Returns providers sorted by number of keyword-field matches.
    """
    from sqlalchemy import text as sa_text

    if not keywords:
        return []

    # Use top keywords to avoid SQL explosion (synonyms can make list long)
    top_kws = keywords[:15]

    # Build WHERE conditions: any keyword in any searchable field
    or_conditions = []
    for kw in top_kws:
        kw_safe = kw.replace("'", "''")  # SQL-safe single quote escape
        for field in [
            "LOWER(COALESCE(p.name, ''))",
            "LOWER(COALESCE(p.firm_name, ''))",
            "LOWER(COALESCE(p.business_description, ''))",
            "LOWER(COALESCE(p.primary_specialty, ''))",
            "LOWER(COALESCE(CAST(p.capabilities AS TEXT), ''))",
            "LOWER(COALESCE(CAST(p.specialties AS TEXT), ''))",
            "LOWER(COALESCE(CAST(p.secondary_specialties AS TEXT), ''))",
            "LOWER(COALESCE(CAST(p.software_tools AS TEXT), ''))",
            "LOWER(COALESCE(CAST(p.team_members AS TEXT), ''))",
            "LOWER(COALESCE(p.notable_clients, ''))",
            "LOWER(COALESCE(p.proven_experience_notable_projects, ''))",
        ]:
            or_conditions.append(f"{field} LIKE '%{kw_safe}%'")

    # Build relevance score: count how many keyword+field combos match
    score_cases = []
    for kw in top_kws[:6]:  # Limit score cases to top 6 for SQL clarity
        kw_safe = kw.replace("'", "''")
        for field in [
            "LOWER(COALESCE(p.name, ''))",
            "LOWER(COALESCE(p.business_description, ''))",
            "LOWER(COALESCE(CAST(p.capabilities AS TEXT), ''))",
            "LOWER(COALESCE(CAST(p.team_members AS TEXT), ''))",
            "LOWER(COALESCE(p.primary_specialty, ''))",
        ]:
            score_cases.append(
                f"CASE WHEN {field} LIKE '%{kw_safe}%' THEN 1 ELSE 0 END"
            )

    relevance_expr = " + ".join(score_cases) if score_cases else "0"
    where_clause = ""
    all_conditions = list(base_filters)
    all_conditions.append("(" + " OR ".join(or_conditions) + ")")
    where_clause = "WHERE " + " AND ".join(all_conditions)

    sql_str = f"""
        SELECT p.*, ({relevance_expr}) AS relevance_score
        FROM providers p
        {where_clause}
        ORDER BY relevance_score DESC
        LIMIT {limit}
    """

    try:
        result = await db.execute(sa_text(sql_str))
        rows = result.mappings().all()
        return rows
    except Exception as exc:
        logger.warning(f'[SEARCH] keyword SQL failed ({exc}), trying simplified query')
        # Simplified fallback: search only business_description and name
        simple_conditions = list(base_filters)
        simple_or = []
        for kw in top_kws[:5]:
            kw_safe = kw.replace("'", "''")
            simple_or.append(f"LOWER(COALESCE(p.business_description, '')) LIKE '%{kw_safe}%'")
            simple_or.append(f"LOWER(COALESCE(p.name, '')) LIKE '%{kw_safe}%'")
            simple_or.append(f"LOWER(COALESCE(CAST(p.capabilities AS TEXT), '')) LIKE '%{kw_safe}%'")
        simple_conditions.append("(" + " OR ".join(simple_or) + ")")
        simple_where = "WHERE " + " AND ".join(simple_conditions)
        simple_sql = sa_text(f"SELECT p.* FROM providers p {simple_where} LIMIT {limit}")
        result = await db.execute(simple_sql)
        return result.mappings().all()


async def _all_providers_by_tier(db, base_filters, limit):
    """Fallback: return all providers ordered by tier quality."""
    from sqlalchemy import text as sa_text
    where_clause = ("WHERE " + " AND ".join(base_filters)) if base_filters else ""
    sql = sa_text(f"""
        SELECT p.* FROM providers p
        {where_clause}
        ORDER BY
            CASE p.business_evaluation_tier
                WHEN 'A' THEN 1 WHEN 'B' THEN 2 WHEN 'C' THEN 3
                WHEN 'D' THEN 4 WHEN 'E' THEN 5 ELSE 6
            END ASC
        LIMIT {limit}
    """)
    result = await db.execute(sql)
    return result.mappings().all()


async def _fetch_candidates(
    db,
    intent,
    filters,
    query_vec,
    limit = 50,
):
    """Steps 3+5: hard filters + pgvector or keyword pre-filter.
    Returns (rows, used_vector, fallback_reason).

    KEY FIX: When no embeddings, uses full keyword SQL search across ALL text
    fields (including JSON arrays cast to text) so providers deep in the
    database are found by relevance, not just the first 50 rows by ID order.
    """
    from sqlalchemy import text as sa_text
    import json as _json
    fallback_reason = None

    base_filters = []
    if intent.get('requires_engineering', 1) == 1:
        base_filters.append('is_engineering_service = 1')

    # ── Vector path ──────────────────────────────────────────────────────────
    if query_vec:
        try:
            where_clause = ('WHERE ' + ' AND '.join(base_filters)) if base_filters else ''
            sql = sa_text(f"""
                SELECT p.*,
                       1 - (p.embedding <=> CAST(:vec AS vector)) AS cosine_similarity
                FROM providers p
                {where_clause}
                ORDER BY cosine_similarity DESC
                LIMIT :lim
            """)
            result = await db.execute(sql, {'vec': _json.dumps(query_vec), 'lim': max(limit, 100)})
            rows = result.mappings().all()
            logger.info(f'[SEARCH] pgvector returned {len(rows)} candidates')
            return rows, True, None
        except Exception as exc:
            logger.warning(f'[SEARCH] pgvector failed ({exc}), falling back to keyword SQL')
            fallback_reason = f'pgvector_error: {type(exc).__name__}'

    # ── Keyword SQL path (no embeddings or pgvector failed) ───────────────────
    # Extract + expand keywords from intent
    raw_kws = [
        *_safe_list(intent.get('inferred_keywords', [])),
        *_safe_list(intent.get('capabilities_needed', [])),
    ]
    spec = intent.get('inferred_specialty', '')
    if spec:
        raw_kws.append(spec)
    if not raw_kws:
        raw_kws = _simple_keywords(filters.get('raw_query', ''))

    expanded = _expand_keywords(raw_kws) if raw_kws else []
    logger.info(f'[SEARCH] keyword search with {len(expanded)} terms (raw: {raw_kws[:3]})')

    try:
        rows = await _keyword_candidate_query(db, expanded, base_filters, max(limit, 150))
        logger.info(f'[SEARCH] keyword SQL returned {len(rows)} candidates')

        if not rows:
            logger.warning('[SEARCH] No keyword matches, returning providers by tier')
            fallback_reason = fallback_reason or 'no_keyword_match'
            rows = await _all_providers_by_tier(db, base_filters, max(limit, 100))

        return rows, False, fallback_reason
    except Exception as exc:
        logger.error(f'[SEARCH] Keyword query failed: {exc}')
        try:
            rows = await _all_providers_by_tier(db, base_filters, max(limit, 50))
            return rows, False, f'keyword_error:{type(exc).__name__}'
        except Exception as exc2:
            logger.error(f'[SEARCH] All fallbacks failed: {exc2}')
            return [], False, 'query_failed'



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
