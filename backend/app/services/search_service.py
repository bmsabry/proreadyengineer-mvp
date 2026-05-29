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

# Monthly search quotas (single source of truth). Free tier matches the value
# advertised to users and shown on the admin tracking screen.
FREE_SEARCH_LIMIT = 10
PAID_SEARCH_LIMIT = 100


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
    similar_project_matched: bool = False
    matching_project_title: str = ""


def _friendly_fallback(reason) -> None:
    """Map internal fallback codes to user-friendly messages, or None to hide."""
    if not reason:
        return None
    if reason.startswith('embedding_failed') or reason.startswith('pgvector_error'):
        return None  # Don't expose internal errors - search still works via fallback
    if reason == 'no_keyword_match':
        return None  # Normal case, no need to show
    if reason.startswith('software_filter_relaxed'):
        return 'Software filter relaxed to find more results'
    return None  # Default: hide all internal codes


def _has_api_key(cfg: Dict[str, Any] = None) -> bool:
    """Check if an OpenAI-compatible API key is available (DB config takes priority)."""
    if cfg:
        key = cfg.get('OPENAI_API_KEY') or ''
    else:
        key = getattr(settings, 'OPENAI_API_KEY', '') or ''
    return bool(key) and key not in ('dummy-key', '')


def _get_client(cfg: Dict[str, Any] = None) -> AsyncOpenAI:
    """Build AsyncOpenAI client using DB config (falls back to env settings)."""
    if cfg:
        api_key = cfg.get('OPENAI_API_KEY') or 'dummy-key'
        base_url = cfg.get('OPENAI_API_BASE') or ''
    else:
        api_key = getattr(settings, 'OPENAI_API_KEY', 'dummy-key') or 'dummy-key'
        base_url = getattr(settings, 'OPENAI_API_BASE', '') or ''
    kwargs: Dict[str, Any] = {'api_key': api_key}
    if base_url:
        kwargs['base_url'] = base_url
    return AsyncOpenAI(**kwargs)


def _get_embedding_client(cfg: Dict[str, Any] = None) -> AsyncOpenAI:
    """Build AsyncOpenAI client for embeddings.
    ONLY uses dedicated EMBEDDING_ keys when BOTH EMBEDDING_API_KEY and EMBEDDING_API_BASE are set.
    Otherwise falls back entirely to LLM2 (OPENAI_) keys to prevent partial-override bugs.
    """
    if cfg:
        embed_key = (cfg.get('EMBEDDING_API_KEY') or '').strip()
        embed_base = (cfg.get('EMBEDDING_API_BASE') or '').strip()
        if embed_key and embed_base:
            api_key = embed_key
            base_url = embed_base
        else:
            api_key = cfg.get('OPENAI_API_KEY') or 'dummy-key'
            base_url = cfg.get('OPENAI_API_BASE') or ''
    else:
        api_key = getattr(settings, 'OPENAI_API_KEY', 'dummy-key') or 'dummy-key'
        base_url = getattr(settings, 'OPENAI_API_BASE', '') or ''
    kwargs: Dict[str, Any] = {'api_key': api_key}
    if base_url:
        kwargs['base_url'] = base_url
    return AsyncOpenAI(**kwargs)


def _embedding_model(cfg: Dict[str, Any] = None) -> str:
    """Return embedding model name, adapting for deepinfra when needed."""
    if cfg:
        model = cfg.get('OPENAI_EMBEDDING_MODEL') or 'BAAI/bge-large-en-v1.5'
        embed_key = (cfg.get('EMBEDDING_API_KEY') or '').strip()
        embed_base = (cfg.get('EMBEDDING_API_BASE') or '').strip()
        # Only use embedding-specific base when BOTH keys are explicitly configured
        base = embed_base if (embed_key and embed_base) else (cfg.get('OPENAI_API_BASE') or '')
    else:
        model = getattr(settings, 'OPENAI_EMBEDDING_MODEL', 'text-embedding-3-small') or 'text-embedding-3-small'
        base = getattr(settings, 'OPENAI_API_BASE', '') or ''
    openai_only = {'text-embedding-3-small', 'text-embedding-ada-002', 'text-embedding-3-large'}
    if 'deepinfra' in base.lower() and model in openai_only:
        return 'BAAI/bge-large-en-v1.5'
    return model


def _llm_model(cfg: Dict[str, Any] = None) -> str:
    """Return LLM model name from DB config or env settings."""
    if cfg:
        return cfg.get('OPENAI_LLM_MODEL') or 'moonshotai/Kimi-K2.5'
    return getattr(settings, 'OPENAI_LLM_MODEL', None) or 'moonshotai/Kimi-K2.5'


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
            logging.getLogger(__name__).debug("suppressed exception", exc_info=True)
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
    "emissions":        ["emissions", "exhaust", "pollutants", "nox", "sox", "co2",
                         "combustion gases", "stack gas", "flue gas", "emission probe",
                         "emissions measurement", "emissions testing"],
    "probe":            ["probe", "sensor", "measurement probe", "instrumentation",
                         "rake", "pitot", "thermocouple", "pressure probe",
                         "measurement device", "test probe"],
    "rake":             ["rake", "probe array", "multi-point measurement",
                         "measurement rake", "emissions rake", "traverse probe"],
    "sensor":           ["sensor", "transducer", "measurement", "instrumentation",
                         "detector", "probe", "gauge"],
    "measurement":      ["measurement", "instrumentation", "test", "probe",
                         "sensor", "diagnostics", "characterization", "metrology"],
    "instrumentation":  ["sensor", "probe", "measurement", "transducer",
                         "diagnostic", "test equipment", "data acquisition"],
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

# Engineering keyword → specialty mapping for fallback inference
_KEYWORD_SPECIALTY_MAP = [
    (['gas turbine', 'combustion', 'turbomachinery', 'turbofan', 'jet engine', 'compressor turbine'], 'Gas Turbine / Thermal Engineering'),
    (['cfd', 'computational fluid', 'fluent', 'openfoam', 'star ccm', 'flow simulation', 'cfx'], 'Computational Fluid Dynamics'),
    (['fea', 'finite element', 'structural analysis', 'stress analysis', 'ansys', 'abaqus', 'nastran'], 'Structural / FEA Engineering'),
    (['thermal', 'heat transfer', 'thermodynamics', 'heat exchanger', 'cooling', 'thermal fluid'], 'Thermal/Fluids Engineering'),
    (['aerospace', 'propulsion', 'rocket', 'missile', 'aircraft', 'satellite'], 'Aerospace Engineering'),
    (['fatigue', 'fracture', 'damage tolerance', 'crack propagation', 'life prediction'], 'Structural Fatigue Analysis'),
    (['pressure vessel', 'asme', 'boiler', 'vessel design', 'api 660', 'tema'], 'Pressure Vessel / Process Engineering'),
    (['vibration', 'modal analysis', 'dynamics', 'resonance', 'acoustic', 'noise'], 'Vibration / Dynamics Engineering'),
    (['machine learning', 'ai', 'data analytics', 'physics informed', 'neural network'], 'Engineering AI / Data Analytics'),
    (['controls', 'control systems', 'pid', 'automation', 'scada', 'plc'], 'Controls Engineering'),
    (['piping', 'pipeline', 'pipe stress', 'flow assurance'], 'Piping / Pipeline Engineering'),
    (['failure analysis', 'root cause', 'forensic', 'corrosion', 'metallurgy'], 'Failure Analysis'),
    (['electrical', 'power systems', 'circuit', 'pcb', 'embedded'], 'Electrical Engineering'),
    (['civil', 'structural', 'construction', 'geotechnical', 'foundation'], 'Civil / Structural Engineering'),
    (['manufacturing', 'machining', 'casting', 'forging', 'welding', 'cnc'], 'Manufacturing Engineering'),
]


def _infer_specialty_from_keywords(keywords: List[str]) -> str:
    """Infer engineering specialty from keywords when LLM returns empty specialty."""
    if not keywords:
        return ''
    kws_text = ' '.join(k.lower() for k in keywords)
    best_match = ''
    best_hits = 0
    for specialty_keywords, specialty_name in _KEYWORD_SPECIALTY_MAP:
        hits = sum(1 for sk in specialty_keywords if sk in kws_text)
        if hits > best_hits:
            best_hits = hits
            best_match = specialty_name
    return best_match if best_hits > 0 else '' 



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
    runtime_config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Step 2: LLM structured intent. Falls back to keywords on any failure."""
    if not _has_api_key(runtime_config):
        logger.info('[INTENT] No API key - using keyword extraction')
        _kws = _simple_keywords(query); return {**_DEFAULT_INTENT, 'inferred_keywords': _kws, 'inferred_specialty': _infer_specialty_from_keywords(_expand_keywords(_kws) or _kws)}

    norm = _normalize_query(query)
    combined = norm
    if document_text:
        combined = norm + '\n\nDocument:\n' + document_text

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
        client = _get_client(runtime_config)
        model  = _llm_model(runtime_config)
        logger.info(f'[INTENT] Calling LLM model={model} query={query[:80]}')
        response = await client.chat.completions.create(
            model=model,
            messages=[
                {'role': 'system', 'content': 'You are an engineering services analyzer. Return only valid JSON.'},
                {'role': 'user',   'content': prompt},
            ],
            temperature=0.1,
            
        )
        raw = response.choices[0].message.content.strip()
        raw = re.sub(r'^```(?:json)?\s*', '', raw)
        raw = re.sub(r'\s*```$', '', raw).strip()
        intent = json.loads(raw)
        for k, v in _DEFAULT_INTENT.items():
            intent.setdefault(k, v)
        # Post-process: infer specialty from keywords if LLM returned empty
        if not intent.get('inferred_specialty') and intent.get('inferred_keywords'):
            inferred = _infer_specialty_from_keywords(intent['inferred_keywords'])
            if inferred:
                intent['inferred_specialty'] = inferred
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

    _kws = _simple_keywords(query); return {**_DEFAULT_INTENT, 'inferred_keywords': _kws, 'inferred_specialty': _infer_specialty_from_keywords(_expand_keywords(_kws) or _kws)}


async def generate_embedding(
    text_input: str,
    runtime_config: Optional[Dict[str, Any]] = None,
) -> List[float]:
    """Step 4: Generate vector embedding. Raises ValueError if no API key."""
    # Check for dedicated embedding key OR general LLM key
    has_embed_key = bool((runtime_config or {}).get('EMBEDDING_API_KEY', '').strip()) if runtime_config else False
    if not has_embed_key and not _has_api_key(runtime_config):
        raise ValueError('No AI API key configured - embeddings unavailable')
    client = _get_embedding_client(runtime_config)
    model  = _embedding_model(runtime_config)
    logger.info(f'[EMBED] model={model}, input_len={len(text_input)}')
    try:
        resp = await client.embeddings.create(model=model, input=text_input)
        vec  = resp.data[0].embedding
        logger.info(f'[EMBED] Generated {len(vec)}-dim vector')
        return vec
    except Exception as exc:
        logger.error(f'[EMBED] Failed: {exc}', exc_info=True)
        raise


def _provider_embed_text(p) -> str:
    """Canonical provider text for embedding."""
    # Extract notable projects as a condensed text (first 500 chars of each, joined)
    notable_raw = getattr(p, 'proven_experience_notable_projects', None) or []
    if isinstance(notable_raw, str):
        import json
        try:
            notable_raw = json.loads(notable_raw)
        except Exception:
            notable_raw = [notable_raw]
    notable_text = ' '.join(str(n) for n in (notable_raw or []))

    parts = [
        _safe_str(getattr(p, 'firm_name', '') or getattr(p, 'name', '')),
        _safe_str(getattr(p, 'primary_specialty', '')),
        _safe_str(getattr(p, 'business_description', '')),
        ' '.join(_safe_list(getattr(p, 'capabilities', []))),
        ' '.join(_safe_list(getattr(p, 'specialties', []))),
        ' '.join(_safe_list(getattr(p, 'software_tools', []))),
        notable_text,
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
    # Fallback: use inferred_keywords as specialty proxy if both are empty
    if not inferred and not cap_needed:
        kw_list = _safe_list(intent.get('inferred_keywords', []))
        if kw_list:
            inferred = ' '.join(kw_list[:10]).lower()
        else:
            return 0.0
    primary   = _safe_str(getattr(provider, 'primary_specialty', '')).lower()
    secondary = ' '.join(_safe_list(getattr(provider, 'secondary_specialties', []))).lower()
    combined  = primary + ' ' + secondary
    score = 0.0
    if inferred:
        words = [w for w in re.findall(r'[a-z0-9]+', inferred) if len(w) >= 3]
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
            cap_words.extend(w for w in re.findall(r'[a-z0-9]+', cap) if len(w) >= 3)
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
        keywords = [w for w in re.findall(r'[a-z0-9]+', spec) if len(w) >= 3]
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


def _score_notable_projects(provider, intent: dict, raw_query: str = '') -> float:
    """Notable Projects Bonus 0-15 pts.

    Uses LLM-extracted intent terms as primary signal (Option B).
    Evaluates each project individually and returns score based on
    the best-matching single project to prevent score dilution.
    """
    import json
    notable_raw = getattr(provider, 'proven_experience_notable_projects', None) or []
    if isinstance(notable_raw, str):
        try:
            notable_raw = json.loads(notable_raw)
        except Exception:
            notable_raw = [notable_raw]

    case_studies_raw = getattr(provider, 'proven_experience_case_studies', None) or []
    if isinstance(case_studies_raw, str):
        try:
            case_studies_raw = json.loads(case_studies_raw)
        except Exception:
            case_studies_raw = [case_studies_raw]

    all_items = list(notable_raw) + list(case_studies_raw)
    if not all_items:
        return 0.0

    # Generic stop words - only true function words, NOT engineering terms
    stop = {
        'and', 'the', 'for', 'with', 'that', 'this', 'from', 'have',
        'will', 'what', 'can', 'are', 'was', 'but', 'not', 'our',
        'your', 'their', 'more', 'also', 'been', 'some', 'into',
        'such', 'than', 'when', 'over', 'each', 'only', 'used',
    }

    def _extract_terms(text: str, min_len: int = 3) -> set:
        return {w for w in re.findall(r'[a-z0-9]+', text.lower())
                if len(w) >= min_len and w not in stop}

    # Build weighted keyword sets from LLM intent (PRIMARY signal)
    specialty_terms = _extract_terms(_safe_str(intent.get('inferred_specialty', '')))
    cap_terms: set = set()
    for cap in _safe_list(intent.get('capabilities_needed', [])):
        cap_terms |= _extract_terms(cap)
    kw_terms: set = set()
    for kw in _safe_list(intent.get('inferred_keywords', [])):
        kw_terms |= _extract_terms(kw)
    # Raw query terms (lowest weight)
    raw_terms = _extract_terms(raw_query) if raw_query else set()

    # Nothing to match against
    if not (specialty_terms or cap_terms or kw_terms or raw_terms):
        return 0.0

    def _score_item(item_text: str) -> float:
        """Score a single project/case-study text with weighted matching."""
        item_words = _extract_terms(str(item_text))
        if not item_words:
            return 0.0
        weighted_hits = 0.0
        weighted_total = 0.0
        # Specialty terms: weight 3
        if specialty_terms:
            weighted_hits  += 3.0 * len(specialty_terms & item_words)
            weighted_total += 3.0 * len(specialty_terms)
        # Capabilities terms: weight 2
        if cap_terms:
            weighted_hits  += 2.0 * len(cap_terms & item_words)
            weighted_total += 2.0 * len(cap_terms)
        # Keyword terms: weight 1.5
        if kw_terms:
            weighted_hits  += 1.5 * len(kw_terms & item_words)
            weighted_total += 1.5 * len(kw_terms)
        # Raw query terms: weight 1
        if raw_terms:
            weighted_hits  += 1.0 * len(raw_terms & item_words)
            weighted_total += 1.0 * len(raw_terms)
        if weighted_total == 0:
            return 0.0
        return weighted_hits / weighted_total

    # Evaluate each project individually - take best match to prevent score dilution
    best_ratio = max(_score_item(str(item)) for item in all_items)

    # FIX: Tightened thresholds - old 0.5/0.3/0.15 too loose.
    # Parts suppliers with gas turbine in project text were getting +15.
    if best_ratio >= 0.65:
        return 15.0
    elif best_ratio >= 0.45:
        return 10.0
    elif best_ratio >= 0.28:
        return 5.0
    elif best_ratio >= 0.15:
        return 2.0
    return 0.0


def _project_types_bonus(provider, intent: Dict[str, Any], raw_query: str = '') -> float:
    """Project Types Bonus 0-15 pts.

    Awards points when the provider's proven_experience_industries_served
    contains industry/project types semantically related to the search query.
    Uses a keyword-to-industry mapping for broader semantic matching.
    """
    industries_raw = getattr(provider, 'proven_experience_industries_served', None)
    industries = _safe_list(industries_raw)
    if not industries:
        return 0.0

    industries_lower = [str(i).lower().strip() for i in industries]

    # Build combined query signal from intent + raw query
    query_signals: List[str] = []
    raw_q = raw_query.lower() if raw_query else ''
    if raw_q:
        query_signals.extend(re.findall(r'[a-z0-9]+', raw_q))
    for kw in _safe_list(intent.get('inferred_keywords', [])):
        query_signals.extend(re.findall(r'[a-z0-9]+', kw.lower()))
    specialty = _safe_str(intent.get('inferred_specialty', '')).lower()
    if specialty:
        query_signals.extend(re.findall(r'[a-z0-9]+', specialty))
    for cap in _safe_list(intent.get('capabilities_needed', [])):
        query_signals.extend(re.findall(r'[a-z0-9]+', cap.lower()))

    stop = {'and', 'the', 'for', 'with', 'that', 'this', 'from', 'have',
            'will', 'what', 'can', 'are', 'was', 'but', 'not', 'our',
            'your', 'their', 'more', 'also'}
    query_signal_set = {w for w in query_signals if len(w) > 2 and w not in stop}

    if not query_signal_set:
        return 0.0

    INDUSTRY_KEYWORDS: Dict[str, List[str]] = {
        'energy'            : ['energy', 'power', 'turbine', 'generator', 'electric',
                               'solar', 'wind', 'nuclear', 'fuel', 'combustion',
                               'thermal', 'heat', 'gas', 'oil'],
        'oil and gas'       : ['oil', 'gas', 'petroleum', 'refinery', 'pipeline',
                               'drilling', 'upstream', 'downstream', 'offshore',
                               'wellhead', 'compressor'],
        'oil & gas'         : ['oil', 'gas', 'petroleum', 'refinery', 'pipeline',
                               'drilling', 'upstream', 'downstream', 'offshore',
                               'wellhead', 'compressor'],
        'aerospace'         : ['aerospace', 'aircraft', 'aviation', 'flight',
                               'propulsion', 'aerodynamic', 'rocket', 'satellite',
                               'hypersonic', 'cfd', 'airfoil', 'turbine'],
        'defense'           : ['defense', 'military', 'weapon', 'armor', 'ballistic',
                               'missile', 'naval', 'combat', 'structural', 'blast'],
        'automotive'        : ['automotive', 'vehicle', 'car', 'truck', 'engine',
                               'transmission', 'suspension', 'brake', 'powertrain', 'crash'],
        'manufacturing'     : ['manufacturing', 'fabrication', 'machining', 'assembly',
                               'tooling', 'production', 'quality', 'process',
                               'automation', 'robot'],
        'construction'      : ['construction', 'building', 'structural', 'civil',
                               'foundation', 'bridge', 'concrete', 'steel',
                               'seismic', 'load'],
        'marine'            : ['marine', 'ship', 'boat', 'offshore', 'underwater',
                               'subsea', 'hull', 'propeller', 'wave', 'hydrodynamic'],
        'medical'           : ['medical', 'biomedical', 'device', 'implant', 'surgical',
                               'orthopedic', 'prosthetic', 'fda', 'biomechanical'],
        'semiconductor'     : ['semiconductor', 'microelectronics', 'chip', 'wafer',
                               'thermal', 'cooling', 'packaging', 'electronics', 'pcb'],
        'chemical'          : ['chemical', 'process', 'reaction', 'catalyst',
                               'distillation', 'polymer', 'material', 'corrosion',
                               'fluid', 'pressure'],
        'nuclear'           : ['nuclear', 'reactor', 'radiation', 'fission', 'fusion',
                               'shielding', 'criticality', 'coolant', 'thermal'],
        'mining'            : ['mining', 'excavation', 'ore', 'mineral', 'rock',
                               'geotechnical', 'blasting', 'equipment', 'underground'],
        'robotics'          : ['robot', 'automation', 'control', 'actuator', 'sensor',
                               'mechatronics', 'machine', 'manipulator', 'kinematics'],
        'power generation'  : ['power', 'generation', 'turbine', 'generator', 'grid',
                               'plant', 'steam', 'thermal', 'cycle', 'boiler', 'combustion'],
        'hvac'              : ['hvac', 'heating', 'cooling', 'ventilation', 'air',
                               'thermal', 'refrigeration', 'heat', 'chiller', 'duct'],
        'infrastructure'    : ['infrastructure', 'bridge', 'road', 'highway', 'rail',
                               'transit', 'utility', 'water', 'pipeline', 'structural'],
        'data center'       : ['data', 'center', 'server', 'cooling', 'thermal',
                               'power', 'rack', 'airflow', 'cfd', 'efficiency'],
        'renewable energy'  : ['renewable', 'solar', 'wind', 'hydro', 'geothermal',
                               'energy', 'sustainable', 'clean', 'green', 'storage'],
        'food and beverage'  : ['food', 'beverage', 'processing', 'sanitary', 'fda',
                               'packaging', 'conveyor', 'thermal', 'sterilization'],
        'pharmaceutical'    : ['pharmaceutical', 'drug', 'fda', 'gmp', 'cleanroom',
                               'bioprocess', 'sterile', 'mixing', 'filtration'],
    }

    best_score = 0.0

    for industry in industries_lower:
        ind_words = {w for w in re.findall(r'[a-z0-9]+', industry) if len(w) > 2}
        direct_overlap = ind_words & query_signal_set
        if direct_overlap:
            ratio = len(direct_overlap) / max(len(ind_words), 1)
            score = min(15.0, 15.0 * min(1.0, ratio * 1.5))
            best_score = max(best_score, score)
            continue

        for ind_key, related_kws in INDUSTRY_KEYWORDS.items():
            ind_key_words = {w for w in re.findall(r'[a-z0-9]+', ind_key) if len(w) > 2}
            if ind_key_words & ind_words:
                related_hits = sum(1 for kw in related_kws if kw in query_signal_set)
                if related_hits > 0:
                    ratio = related_hits / len(related_kws)
                    score = min(15.0, ratio * 80.0)
                    best_score = max(best_score, score)

    return round(min(15.0, best_score), 2)




def _detect_similar_project(
    provider,
    intent: Dict[str, Any],
    raw_query: str = '',
) -> tuple:
    """Direct keyword matching for similar project detection.

    Uses DIRECT LITERAL matching only - no synonym expansion.
    Requires that multiple DISTINCT query keywords appear literally
    in the same project item text. This prevents false positives from
    generic engineering companies whose project text contains common
    words like 'instrumentation', 'exhaust', or 'heat' that have
    nothing to do with the actual query intent.

    Returns (matched: bool, project_title: str, match_confidence: float)
    """
    import json as _json

    # Stop list: function words AND generic engineering words that appear everywhere
    # These words are too common to be meaningful for project matching
    stop = {
        # Function words
        'and', 'the', 'for', 'with', 'that', 'this', 'from', 'have',
        'will', 'what', 'can', 'are', 'was', 'but', 'not', 'our',
        'your', 'their', 'more', 'also', 'used', 'been', 'some',
        'into', 'such', 'than', 'when', 'over', 'each', 'only',
        # Generic engineering/business words - too common to be meaningful
        'engineering', 'design', 'system', 'systems', 'analysis',
        'service', 'services', 'project', 'projects', 'develop',
        'development', 'provide', 'provides', 'solution', 'solutions',
        'process', 'quality', 'testing', 'management', 'research',
        'technical', 'technology', 'application', 'applications',
        'using', 'based', 'data', 'high', 'new', 'large', 'small',
        'full', 'complete', 'multiple', 'various', 'advanced',
        'custom', 'support', 'include', 'includes', 'including',
    }

    # Extract ONLY raw query keywords (direct words from user input)
    # Do NOT include LLM-expanded specialty/capabilities - those are too broad
    core_kws = set()
    q = raw_query.lower() if raw_query else ''
    for w in re.findall(r'[a-z0-9]+', q):
        if len(w) > 2 and w not in stop:
            core_kws.add(w)

    if len(core_kws) == 0:
        return False, '', 0.0

    # ── Load case studies ─────────────────────────────────────────────────────
    case_studies_raw = getattr(provider, 'proven_experience_case_studies', None) or []
    if isinstance(case_studies_raw, str):
        try:
            case_studies_raw = _json.loads(case_studies_raw)
        except Exception:
            case_studies_raw = [case_studies_raw]

    # ── Load notable projects ─────────────────────────────────────────────────
    notable_raw = getattr(provider, 'proven_experience_notable_projects', None) or []
    if isinstance(notable_raw, str):
        try:
            notable_raw = _json.loads(notable_raw)
        except Exception:
            notable_raw = [notable_raw]

    all_items = list(case_studies_raw) + list(notable_raw)
    if not all_items:
        return False, '', 0.0

    # Determine minimum match threshold based on number of core keywords:
    # - 1 keyword: must match 1/1 (100%) - single specific term
    # - 2 keywords: must match 2/2 (100%) - both must appear
    # - 3+ keywords: must match at least 2 distinct keywords in same item
    min_matches_needed = min(2, len(core_kws)) if len(core_kws) >= 2 else 1

    best_count = 0
    best_title = ''
    best_ratio = 0.0

    for item in all_items:
        item_str = str(item).lower()
        if len(item_str) < 5:
            continue

        # DIRECT literal match only - check if each core keyword
        # (or its direct stem) appears in item text
        matched = set()
        for kw in core_kws:
            # Direct substring match - word must literally appear
            # Use word-boundary style: check for kw as a token in text
            # e.g. 'probe' matches 'probe' and 'probes' but not 'probe' != 'instrumentation'
            if kw in item_str:
                matched.add(kw)
            # Also check plural/stem variants (e.g. emission->emissions)
            elif kw.endswith('s') and kw[:-1] in item_str:
                matched.add(kw)
            elif not kw.endswith('s') and kw + 's' in item_str:
                matched.add(kw)
            elif kw.endswith('ing') and kw[:-3] in item_str:
                matched.add(kw)
            elif kw.endswith('ed') and kw[:-2] in item_str:
                matched.add(kw)
            elif kw.endswith('er') and kw[:-2] in item_str:
                matched.add(kw)

        count = len(matched)
        ratio = count / len(core_kws)

        if count > best_count or (count == best_count and ratio > best_ratio):
            best_count = count
            best_ratio = ratio
            raw_title = str(item)[:120].split('.')[0].strip()
            best_title = raw_title if len(raw_title) > 5 else str(item)[:80].strip()

    # Require minimum keyword matches - must be specific, not accidental
    matched_result = best_count >= min_matches_needed

    logger.debug(
        '[SIMILAR_PROJECT] provider=%s core_kws=%s best_count=%d/%d needed=%d matched=%s title=%s',
        getattr(provider, 'name', '?'), sorted(core_kws), best_count, len(core_kws),
        min_matches_needed, matched_result, best_title[:60]
    )

    return matched_result, best_title, best_ratio

def calculate_match_score(
    provider,
    intent: Dict[str, Any],
    similarity: float = 0.0,
    raw_query: str = '',
    similar_project_matched: bool = False,
) -> Dict[str, float]:
    """Compute deterministic 100-point composite score (+30 bonus if similar project)."""
    tier_pts      = _tier_score(provider)
    specialty_pts = _specialty_score(provider, intent)
    if similarity > 0.0:
        cap_pts = round(similarity * 50.0, 2)
    else:
        cap_pts = _capabilities_score_keyword(provider, intent)
    sw_bonus       = _software_bonus(provider, intent)
    proj_bonus     = _project_types_bonus(provider, intent, raw_query)
    notable_bonus  = _score_notable_projects(provider, intent, raw_query)
    # +30 boost when a genuinely similar project is confirmed via keyword detection
    sim_boost      = 30.0 if similar_project_matched else 0.0
    total    = min(100.0, specialty_pts + cap_pts + tier_pts + sw_bonus + proj_bonus + notable_bonus + sim_boost)
    return {
        'total':           round(total, 2),
        'specialty':       round(specialty_pts, 2),
        'capabilities':    round(cap_pts, 2),
        'tier':            round(tier_pts, 2),
        'software_bonus':  round(sw_bonus, 2),
        'proj_bonus':      round(proj_bonus, 2),
        'notable_bonus':   round(notable_bonus, 2),
        'sim_boost':       round(sim_boost, 2),
        'similarity':      round(similarity, 4),
    }


def _build_explanation(name: str, scores: Dict[str, float], intent: Dict[str, Any], similar_project_title: str = '') -> str:
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
    if scores.get('proj_bonus', 0) > 0:
        parts.append(f"Project types match bonus: +{scores['proj_bonus']:.0f}.")
    if scores.get('notable_bonus', 0) > 0:
        parts.append(f"Notable projects match: +{scores['notable_bonus']:.0f}.")
    if scores['software_bonus'] > 0:
        parts.append(f"Software tool bonus: +{scores['software_bonus']:.0f}.")
    parts.append(f"Matched on: {specialty}.")
    if similar_project_title:
        # Truncate title to 100 chars for readability
        short_title = similar_project_title[:100] + ('...' if len(similar_project_title) > 100 else '')
        parts.insert(0, f"✓ Conducted a similar project: {short_title}")
    return ' '.join(parts)




def _provider_summary_for_llm(provider, idx: int) -> dict:
    """Build condensed provider summary for LLM reranking.
    FIX: 100-char truncation hid installation/commissioning text,
    letting parts suppliers score 100/100 on design queries.
    """
    caps = _safe_list(getattr(provider, 'capabilities', []))[:8]
    notable = _safe_list(getattr(provider, 'proven_experience_notable_projects', []))[:3]
    case_studies = _safe_list(getattr(provider, 'proven_experience_case_studies', []))[:3]
    projects = notable + case_studies
    proj_texts = [str(p) for p in projects]
    description = _safe_str(getattr(provider, 'business_description', ''))
    tier = (getattr(provider, 'business_evaluation_tier', None)
            or getattr(provider, 'tier', None) or 'unknown')
    return {
        'id': provider.id,
        'name': _display_name(provider)[:60],
        'tier': str(tier),
        'specialty': _safe_str(getattr(provider, 'primary_specialty', ''))[:80],
        'description': description,
        'capabilities': caps,
        'projects': proj_texts,
    }




def _extract_llm_content(response) -> str:
    """Extract text from LLM response, handles Kimi-K2.5 reasoning models."""
    msg = response.choices[0].message
    content = getattr(msg, 'content', None) or ''
    if not content or not content.strip():
        reasoning = getattr(msg, 'reasoning_content', None) or ''
        if reasoning:
            content = reasoning
    return content.strip()


def _parse_json_from_llm(text: str):
    """Extract and parse JSON array from LLM response text."""
    import re as _re
    text = _re.sub(r'^```(?:json)?\s*', '', text)
    text = _re.sub(r'\s*```$', '', text).strip()
    if text.startswith('{'):
        arr_match = _re.search(r'\[.*\]', text, _re.DOTALL)
        if arr_match:
            text = arr_match.group(0)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    arr_match = _re.search(r'\[.*\]', text, _re.DOTALL)
    if arr_match:
        try:
            return json.loads(arr_match.group(0))
        except json.JSONDecodeError:
            pass
    raise json.JSONDecodeError('Could not find valid JSON array', text, 0)


async def llm_pass1_filter(
    providers: list,
    query: str,
    intent: Dict[str, Any],
    runtime_config: Optional[Dict[str, Any]] = None,
) -> Optional[List[int]]:
    """Pass 1: ONE LLM call to filter engineering service providers.

    Returns list of provider IDs to keep, or None on failure.
    None => caller uses all candidates as safe fallback.
    """
    if not providers:
        return None
    try:
        companies = []
        for prov, _sim in providers:
            desc = _safe_str(getattr(prov, 'business_description', ''))
            companies.append({
                'id': prov.id,
                'name': _display_name(prov)[:60],
                'business_description': desc,
            })
        specialty = _safe_str(intent.get('inferred_specialty', ''))
        caps = _safe_list(intent.get('capabilities_needed', []))
        caps_str = json.dumps(caps)
        prompt_lines = [
            'You are an expert engineering services classifier.',
            '',
            f'Query: {chr(34)}{query}{chr(34)}',
            f'Inferred specialty: {chr(34)}{specialty}{chr(34)}',
            f'Required capabilities: {caps_str}',
            '',
            'For each company below, determine if they provide engineering SERVICES relevant to this query.',
            'IMPORTANT RULES:',
            '- Keep=true ONLY if the company performs engineering analysis, design, testing, or consulting services',
            '- Keep=false if the company primarily manufactures or supplies products/parts/hardware',
            '- Keep=false if the company is a staffing agency with no engineering focus',
            '- Keep=false if the description is clearly unrelated to the query domain',
            '',
            'Return ONLY a JSON array, no other text:',
            '[{' + chr(34) + 'id' + chr(34) + ': <id>, ' + chr(34) + 'keep' + chr(34) + ': <true/false>}, ...]',
            '',
            'Companies:',
            json.dumps(companies, separators=(',', ': ')),
        ]
        prompt = '\n'.join(prompt_lines)
        client = _get_client(runtime_config)
        model = _llm_model(runtime_config)
        logger.info('[PASS1] Calling LLM model=%s with %d candidates', model, len(companies))
        response = await client.chat.completions.create(
            model=model,
            messages=[
                {'role': 'system', 'content': 'You are an engineering services classifier. Return only valid JSON arrays.'},
                {'role': 'user', 'content': prompt},
            ],
            temperature=0.1,
            
        )
        raw = _extract_llm_content(response)
        parsed = _parse_json_from_llm(raw)
        if not isinstance(parsed, list):
            logger.warning('[PASS1] LLM returned non-list JSON, using all candidates')
            return None
        kept_ids = []
        for item in parsed:
            if not isinstance(item, dict):
                continue
            pid = item.get('id')
            keep = item.get('keep')
            if pid is not None and keep is True:
                try:
                    kept_ids.append(int(pid))
                except (ValueError, TypeError):
                    pass
        logger.info('[PASS1] Filter: %d/%d providers passed', len(kept_ids), len(companies))
        if not kept_ids:
            logger.warning('[PASS1] LLM filtered all candidates - using all as fallback')
            return None
        return kept_ids
    except json.JSONDecodeError as exc:
        logger.warning('[PASS1] JSON parse error: %s - using all candidates', exc)
        return None
    except Exception as exc:
        logger.warning('[PASS1] LLM error: %s - using all candidates', exc)
        return None


async def llm_pass2_rank(
    providers: list,
    query: str,
    intent: Dict[str, Any],
    runtime_config: Optional[Dict[str, Any]] = None,
) -> Optional[List[tuple]]:
    """Pass 2: ONE LLM call to rank filtered candidates by project similarity.

    Returns ordered list of (provider_id, similar_project) tuples, or None on failure.
    None => caller ranks by vector similarity score.
    """
    if not providers:
        return None
    try:
        companies = []
        for prov, _sim in providers:
            notable_raw = getattr(prov, 'proven_experience_notable_projects', None) or []
            if isinstance(notable_raw, str):
                try:
                    notable_raw = json.loads(notable_raw)
                except Exception:
                    notable_raw = [notable_raw] if notable_raw.strip() else []
            case_raw = getattr(prov, 'proven_experience_case_studies', None) or []
            if isinstance(case_raw, str):
                try:
                    case_raw = json.loads(case_raw)
                except Exception:
                    case_raw = [case_raw] if case_raw.strip() else []
            notable_list = [str(p) for p in (notable_raw or [])]
            case_list = [str(c) for c in (case_raw or [])]
            companies.append({
                'id': prov.id,
                'name': _display_name(prov)[:60],
                'notable_projects': notable_list,
                'proven_experience_case_studies': case_list,
            })
        specialty = _safe_str(intent.get('inferred_specialty', ''))
        prompt_lines = [
            'You are an expert engineering project evaluator.',
            '',
            f'Query: {chr(34)}{query}{chr(34)}',
            f'Inferred specialty: {chr(34)}{specialty}{chr(34)}',
            '',
            'Rank the following companies by how closely their past projects match the query.',
            'Companies with directly matching projects should rank highest.',
            'Companies with no projects rank last.',
            '',
            'IMPORTANT RULES:',
            '- Set similar_project=true ONLY if the firm PERFORMED or CONDUCTED the requested service',
            '  (designed, analyzed, engineered, modeled, evaluated, tested)',
            '- Set similar_project=false if the firm merely SUPPLIED PRODUCTS, PARTS, or HARDWARE',
            '- Set similar_project=false if project only mentions INSTALLING, COMMISSIONING, or MAINTAINING equipment',
            '',
            'Return ONLY a JSON array ordered from most to least relevant, no other text:',
            '[{' + chr(34) + 'id' + chr(34) + ': <id>, ' + chr(34) + 'rank' + chr(34) + ': <1,2,...>, ' + chr(34) + 'similar_project' + chr(34) + ': <true/false>}, ...]',
            '',
            'Companies:',
            json.dumps(companies, separators=(',', ': ')),
        ]
        prompt = '\n'.join(prompt_lines)
        client = _get_client(runtime_config)
        model = _llm_model(runtime_config)
        logger.info('[PASS2] Calling LLM model=%s with %d candidates', model, len(companies))
        response = await client.chat.completions.create(
            model=model,
            messages=[
                {'role': 'system', 'content': 'You are an engineering project evaluator. Return only valid JSON arrays.'},
                {'role': 'user', 'content': prompt},
            ],
            temperature=0.1,
            
        )
        raw = _extract_llm_content(response)
        parsed = _parse_json_from_llm(raw)
        if not isinstance(parsed, list):
            logger.warning('[PASS2] LLM returned non-list JSON, using similarity order')
            return None
        ranked_items = []
        for item in parsed:
            if not isinstance(item, dict):
                continue
            pid = item.get('id')
            rank = item.get('rank')
            if pid is not None and rank is not None:
                try:
                    ranked_items.append((
                        int(rank),
                        int(pid),
                        bool(item.get('similar_project', False)),
                    ))
                except (ValueError, TypeError):
                    pass
        ranked_items.sort(key=lambda x: x[0])
        result = [(pid, sim_proj) for _, pid, sim_proj in ranked_items]
        logger.info('[PASS2] Ranked %d providers', len(result))
        if result:
            logger.info('[PASS2] Top 5: %s', [pid for pid, _ in result[:5]])
        return result if result else None
    except json.JSONDecodeError as exc:
        logger.warning('[PASS2] JSON parse error: %s - using similarity order', exc)
        return None
    except Exception as exc:
        logger.warning('[PASS2] LLM error: %s - using similarity order', exc)
        return None
async def check_search_quota(
    db: AsyncSession,
    user_id=None,
    ip_address: Optional[str] = None,
) -> Dict[str, Any]:
    """Check caller search quota using a FRESH session to avoid contamination.
    Returns {allowed, remaining, limit, used}.
    """
    from app.db.session import AsyncSessionLocal
    now = datetime.utcnow()

    # --- Anonymous users must register to search ---
    if user_id is None:
        return {'allowed': False, 'remaining': 0, 'limit': 0, 'used': 0, 'reason': 'registration_required'}

    # --- Registered user quota ---
    try:
        from app.models.user import User
        from app.models.payment import Subscription
        async with AsyncSessionLocal() as fresh_db:
            # Fetch user with fresh session
            result = await fresh_db.execute(
                select(User).where(User.id == user_id)
            )
            user = result.scalar_one_or_none()
            if not user:
                return {'allowed': False, 'remaining': 0, 'limit': 0, 'used': 0}

            # Determine quota limit from active subscription
            limit = FREE_SEARCH_LIMIT  # free tier (matches advertised/admin value)
            try:
                sub_result = await fresh_db.execute(
                    select(Subscription).where(
                        Subscription.user_id == user_id,
                        Subscription.subscription_status == 'active',
                        Subscription.subscription_type.in_(['search_tier_1', 'search_tier_2']),
                    ).order_by(Subscription.created_at.desc()).limit(1)
                )
                sub = sub_result.scalar_one_or_none()
                if sub:
                    # search_tier_1 (current) or legacy search_tier_2 both grant the paid quota
                    limit = PAID_SEARCH_LIMIT
            except Exception:
                pass  # Keep default limit of 5

            used = user.monthly_search_count or 0
            reset_at = user.search_count_reset_at
            # Reset count if it's a new month
            if reset_at and hasattr(reset_at, 'month'):
                if reset_at.year != now.year or reset_at.month != now.month:
                    used = 0

        return {'allowed': used < limit, 'remaining': max(0, limit - used), 'limit': limit, 'used': used}
    except Exception as exc:
        logger.warning(f'[QUOTA] User quota check error: {exc}')
        return {'allowed': True, 'remaining': FREE_SEARCH_LIMIT, 'limit': FREE_SEARCH_LIMIT, 'used': 0}


async def increment_search_quota(
    db: AsyncSession,
    user_id=None,
    ip_address: Optional[str] = None,
) -> None:
    """Increment search usage counter using a FRESH independent session.
    Uses direct SQL UPDATE to bypass ORM identity-map stale cache issues.
    The `db` parameter is kept for signature compatibility but NOT used here.
    """
    from app.db.session import AsyncSessionLocal
    now = datetime.utcnow()

    # --- Anonymous / IP-based increment ---
    if user_id is None:
        if not ip_address:
            return
        try:
            from app.models.search import IPUsageTracking
            month_str = now.strftime('%Y-%m')
            async with AsyncSessionLocal() as fresh_db:
                result = await fresh_db.execute(
                    select(IPUsageTracking)
                    .where(IPUsageTracking.ip_address == ip_address)
                    .where(IPUsageTracking.usage_month == month_str)
                )
                record = result.scalar_one_or_none()
                if record:
                    record.search_count = (record.search_count or 0) + 1
                    record.updated_at = now
                else:
                    fresh_db.add(IPUsageTracking(
                        ip_address=ip_address,
                        usage_month=month_str,
                        search_count=1,
                        created_at=now,
                        updated_at=now,
                    ))
                await fresh_db.commit()
            logger.info(f'[QUOTA] IP increment OK: {ip_address} month={month_str}')
        except Exception as exc:
            logger.warning(f'[QUOTA] IP increment error: {exc}')
        return

    # --- Registered user increment via direct SQL UPDATE ---
    try:
        from app.models.user import User
        from sqlalchemy import update as sql_update
        async with AsyncSessionLocal() as fresh_db:
            # Fetch user to check current month
            result = await fresh_db.execute(
                select(User.monthly_search_count, User.search_count_reset_at)
                .where(User.id == user_id)
            )
            row = result.first()
            if not row:
                logger.warning(f'[QUOTA] User {user_id} not found for increment')
                return

            current_count, reset_at = row
            current_count = current_count or 0

            # Determine new count (reset if new month)
            if reset_at and hasattr(reset_at, 'month'):
                if reset_at.year != now.year or reset_at.month != now.month:
                    new_count = 1  # new month - reset
                else:
                    new_count = current_count + 1
            else:
                new_count = current_count + 1

            # Direct SQL UPDATE - bypasses ORM identity map entirely
            await fresh_db.execute(
                sql_update(User)
                .where(User.id == user_id)
                .values(
                    monthly_search_count=new_count,
                    search_count_reset_at=now,
                )
            )
            await fresh_db.commit()
            logger.info(f'[QUOTA] User {user_id} increment OK: {current_count} -> {new_count}')
    except Exception as exc:
        logger.warning(f'[QUOTA] User increment error: {exc}', exc_info=True)


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
            "LOWER(COALESCE(CAST(p.proven_experience_notable_projects AS TEXT), ''))",
            "LOWER(COALESCE(CAST(p.proven_experience_case_studies AS TEXT), ''))",
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
    limit = 250,
):
    """
    Steps 3+5: hard filters + pgvector or keyword pre-filter.
    Returns (rows, used_vector, fallback_reason).

    NUCLEAR FIX: Each query path uses its OWN fresh AsyncSession.
    asyncpg marks a connection as aborted on ANY SQL error - even inside a
    SAVEPOINT - making all subsequent queries on that session fail with
    InFailedSQLTransactionError. The ONLY reliable fix is a fresh connection.
    """
    from sqlalchemy import text as sa_text
    import json as _json
    from app.db.session import AsyncSessionLocal
    fallback_reason = None

    base_filters = []
    if intent.get('requires_engineering', 1) == 1:
        base_filters.append('is_engineering_service = 1')

    # ── Vector path (isolated fresh session) ─────────────────────────────────
    if query_vec:
        try:
            async with AsyncSessionLocal() as vec_db:
                where_clause = ('WHERE ' + ' AND '.join(base_filters)) if base_filters else ''
                sql = sa_text(f"""
                    SELECT p.*,
                           1 - (p.embedding <=> CAST(:vec AS vector)) AS cosine_similarity
                    FROM providers p
                    {where_clause}
                    ORDER BY cosine_similarity DESC
                    LIMIT :lim
                """)
                result = await vec_db.execute(sql, {'vec': _json.dumps(query_vec), 'lim': max(limit, 250)})
                rows = result.mappings().all()
                logger.info(f'[SEARCH] pgvector returned {len(rows)} candidates')
                # ── Project injection: find providers with matching case studies ─────
                # These providers may not score high on vector similarity but have
                # directly relevant project experience - always include them.
                # Strategy: use SPECIFIC keywords only (not generic like 'design', 'system')
                # with AND logic when 2+ specific keywords exist, to avoid matching
                # hundreds of unrelated companies.
                injected_rows = []
                try:
                    # Generic/stop words that match too many companies - exclude from injection
                    _inject_stop = {
                        'design', 'system', 'systems', 'analysis', 'service', 'services',
                        'project', 'projects', 'develop', 'development', 'provide', 'provides',
                        'solution', 'solutions', 'process', 'quality', 'testing', 'management',
                        'research', 'technical', 'technology', 'application', 'applications',
                        'data', 'high', 'large', 'full', 'complete', 'advanced', 'custom',
                        'support', 'include', 'using', 'based', 'engineering', 'mechanical',
                        'electrical', 'structural', 'civil', 'software', 'hardware',
                        'test', 'work', 'make', 'build', 'create', 'implement',
                    }
                    # Collect raw query words only (not LLM expansions - too broad)
                    q_str = filters.get('raw_query', '') or ''
                    specific_kws = []
                    for w in re.findall(r'[a-z0-9]+', q_str.lower()):
                        if len(w) > 3 and w not in _inject_stop:
                            specific_kws.append(w)
                    specific_kws = list(dict.fromkeys(specific_kws))  # dedupe, preserve order

                    if specific_kws:
                        existing_ids = {r.get('id') for r in rows}

                        # Build per-keyword conditions (case_studies OR notable_projects)
                        def _kw_condition(kw):
                            k = kw.replace("'", "''")
                            return (
                                f"(LOWER(COALESCE(CAST(p.proven_experience_case_studies AS TEXT),'')) LIKE '%{k}%' "
                                f"OR LOWER(COALESCE(CAST(p.proven_experience_notable_projects AS TEXT),'')) LIKE '%{k}%')"
                            )

                        if len(specific_kws) >= 2:
                            # AND logic: ALL specific keywords must appear in projects
                            # This is strict but ensures relevance - e.g. both 'emissions'
                            # AND 'probe' must appear, not just one of them
                            and_conditions = [_kw_condition(kw) for kw in specific_kws[:4]]
                            project_filter = ' AND '.join(and_conditions)
                        else:
                            # Single keyword: OR is fine, it's already specific
                            project_filter = _kw_condition(specific_kws[0])

                        where_inject = (
                            ('WHERE ' + ' AND '.join(base_filters) + ' AND ' if base_filters else 'WHERE ')
                            + '(' + project_filter + ')'
                        )
                        inject_sql = sa_text(f"""
                            SELECT p.*, 0.0 AS cosine_similarity
                            FROM providers p
                            {where_inject}
                            ORDER BY p.business_evaluation_tier ASC
                            LIMIT 100
                        """)
                        inject_result = await vec_db.execute(inject_sql)
                        inject_rows = inject_result.mappings().all()
                        for ir in inject_rows:
                            if ir.get('id') not in existing_ids:
                                injected_rows.append(ir)
                                existing_ids.add(ir.get('id'))
                        if injected_rows:
                            logger.info(
                                f'[SEARCH] Injected {len(injected_rows)} project-matched providers '
                                f'(keywords={specific_kws[:4]}, and_logic={len(specific_kws)>=2})'
                            )
                except Exception as inj_exc:
                    logger.warning(f'[SEARCH] Project injection failed (non-fatal): {inj_exc}')
                all_rows = list(rows) + injected_rows
                return all_rows, True, None
        except Exception as exc:
            logger.warning(f'[SEARCH] pgvector failed: {type(exc).__name__}: {str(exc)[:200]}')
            fallback_reason = f'pgvector_error:{type(exc).__name__}:{str(exc)[:120]}'

    # ── Keyword SQL path (fresh isolated session) ─────────────────────────────
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
        async with AsyncSessionLocal() as kw_db:
            rows = await _keyword_candidate_query(kw_db, expanded, base_filters, max(limit, 150))
            logger.info(f'[SEARCH] keyword SQL returned {len(rows)} candidates')

            if not rows:
                logger.warning('[SEARCH] No keyword matches, returning providers by tier')
                fallback_reason = fallback_reason or 'no_keyword_match'
                rows = await _all_providers_by_tier(kw_db, base_filters, max(limit, 250))

            return rows, False, fallback_reason
    except Exception as exc:
        logger.error(f'[SEARCH] Keyword query failed: {type(exc).__name__}: {str(exc)[:200]}')
        try:
            async with AsyncSessionLocal() as tier_db:
                rows = await _all_providers_by_tier(tier_db, base_filters, max(limit, 50))
                return rows, False, f'keyword_error:{type(exc).__name__}'
        except Exception as exc2:
            logger.error(f'[SEARCH] All fallbacks failed: {type(exc2).__name__}: {str(exc2)[:200]}')
            return [], False, f'err:{type(exc2).__name__}:{str(exc2)[:120]}'




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
    top_n: int = 5,
) -> tuple:
    """Full two-pass LLM search pipeline.
    Returns (results: List[SearchResultItem], pipeline_info: dict)
    """
    if filters is None:
        filters = {}
    norm_query = _normalize_query(query)
    logger.info(f'[SEARCH] query={norm_query[:100]}')
    filters['raw_query'] = norm_query
    pipeline_info: Dict[str, Any] = {
        'pipeline_used': 'keyword_fallback',
        'llm_called': False,
        'llm_response_received': False,
        'llm_model': '',
        'embedding_called': False,
        'embedding_dims': 0,
        'api_key_source': 'missing',
        'fallback_reason': None,
        'inferred_specialty': None,
        'inferred_keywords': [],
        'llm_reranking_called': False,
        'llm_reranking_success': False,
        'candidates_evaluated': 0,
        'pass1_kept': 0,
        'pass2_ranked': 0,
    }
    from app.services.config_service import get_runtime_config
    runtime_config = await get_runtime_config(db)
    api_key = runtime_config.get('OPENAI_API_KEY', '') or ''
    embed_key_gate = runtime_config.get('EMBEDDING_API_KEY', '') or ''
    has_key = (
        (bool(api_key) and api_key not in ('dummy-key', 'your-api-key-here', ''))
        or (bool(embed_key_gate) and embed_key_gate not in ('dummy-key', 'your-api-key-here', ''))
    )
    if has_key:
        try:
            from app.models.system_config import SystemConfig
            from sqlalchemy import select as sa_select
            result = await db.execute(
                sa_select(SystemConfig).where(SystemConfig.key == 'OPENAI_API_KEY')
            )
            rec = result.scalar_one_or_none()
            pipeline_info['api_key_source'] = 'database' if (rec and rec.value) else 'env_var'
        except Exception:
            pipeline_info['api_key_source'] = 'env_var'
    else:
        pipeline_info['api_key_source'] = 'missing'
    logger.info('[SEARCH] API key source=%s has_key=%s', pipeline_info['api_key_source'], has_key)
    llm_model = (
        runtime_config.get('OPENAI_LLM_MODEL', '')
        or runtime_config.get('OPENAI_MODEL', '')
        or 'moonshotai/Kimi-K2.5'
    )
    pipeline_info['llm_model'] = llm_model if has_key else '(none - no API key)'
    pipeline_info['llm_called'] = has_key
    intent = await extract_structured_intent(norm_query, runtime_config=runtime_config)
    fallback_reason: Optional[str] = None
    if has_key:
        got_specialty = bool(intent.get('inferred_specialty', ''))
        got_keywords = bool(intent.get('inferred_keywords') or intent.get('capabilities_needed'))
        pipeline_info['llm_response_received'] = got_specialty or got_keywords
        logger.info(
            '[SEARCH] LLM response received=%s specialty=%s keywords=%s',
            pipeline_info['llm_response_received'],
            intent.get('inferred_specialty', ''),
            intent.get('inferred_keywords', []),
        )
    pipeline_info['inferred_specialty'] = intent.get('inferred_specialty', '') or ''
    pipeline_info['inferred_keywords'] = (intent.get('inferred_keywords') or [])[:8]
    query_vec: Optional[List[float]] = None
    if has_key:
        pipeline_info['embedding_called'] = True
        try:
            query_vec = await generate_embedding(norm_query, runtime_config=runtime_config)
            pipeline_info['embedding_dims'] = len(query_vec) if query_vec else 0
            logger.info('[SEARCH] Embedding generated: %d dims', pipeline_info['embedding_dims'])
        except Exception as exc:
            pipeline_info['embedding_called'] = False
            logger.warning(f'[SEARCH] Embedding failed ({exc}), using keyword scoring')
            fallback_reason = fallback_reason or f'embedding_failed:{type(exc).__name__}'
    try:
        rows, used_vector, fetch_fallback = await _fetch_candidates(
            db, intent, filters, query_vec, limit=250
        )
        if fetch_fallback:
            fallback_reason = fallback_reason or fetch_fallback
    except Exception as exc:
        logger.error(f'[SEARCH] Candidate fetch error: {exc}')
        rows = []
        used_vector = False
    if used_vector:
        pipeline_info['pipeline_used'] = 'ai_vector'
    elif not has_key:
        pipeline_info['pipeline_used'] = 'no_api_key'
    else:
        pipeline_info['pipeline_used'] = 'keyword_fallback'
    pipeline_info['fallback_reason'] = fallback_reason
    if not rows:
        logger.info('[SEARCH] No candidates found, returning empty')
        return [], pipeline_info
    provider_list = []
    for row in rows:
        try:
            provider = _ProviderProxy(row)
            similarity = float(row.get('cosine_similarity', 0.0) or 0.0) if used_vector else 0.0
            provider_list.append((provider, similarity))
        except Exception as exc:
            logger.warning(f'[SEARCH] Proxy build error for row: {exc}')
    pipeline_info['candidates_evaluated'] = len(provider_list)
    pipeline_info['llm_reranking_called'] = has_key and bool(provider_list)
    scored: List[tuple] = []
    if has_key and provider_list:
        # ---- TWO-PASS LLM PIPELINE ----
        # Pass 1: filter non-service providers (ONE LLM call)
        kept_ids = await llm_pass1_filter(provider_list, norm_query, intent, runtime_config)
        if kept_ids is None:
            filtered_list = provider_list
            logger.info('[SEARCH] Pass1 fallback: using all %d candidates', len(provider_list))
        else:
            id_set = set(kept_ids)
            filtered_list = [(p, s) for p, s in provider_list if p.id in id_set]
            logger.info('[SEARCH] Pass1 kept %d/%d candidates', len(filtered_list), len(provider_list))
        pipeline_info['pass1_kept'] = len(filtered_list)

        # Pass 2: rank by project similarity (ONE LLM call)
        ranked_result = await llm_pass2_rank(filtered_list, norm_query, intent, runtime_config)
        if ranked_result is None:
            logger.info('[SEARCH] Pass2 fallback: ranking by vector similarity')
            ranked_result = [
                (p.id, False)
                for p, s in sorted(filtered_list, key=lambda x: x[1], reverse=True)
            ]
        pipeline_info['pass2_ranked'] = len(ranked_result)
        pipeline_info['llm_reranking_success'] = True

        # Build id->provider map
        id_to_prov = {p.id: (p, s) for p, s in filtered_list}
        tier_bonus = {
            'A': 5, 'B': 4, 'C': 3, 'D': 2, 'E': 1,
            'a': 5, 'b': 4, 'c': 3, 'd': 2, 'e': 1,
        }

        for rank_pos, (pid, sim_proj) in enumerate(ranked_result, start=1):
            if pid not in id_to_prov:
                continue
            provider, similarity = id_to_prov[pid]
            try:
                name = _display_name(provider)
                # rank 1=100pts, rank 2=90pts ... floor at 10pts
                base_score = max(1.0, 101.0 - rank_pos)
                tier_raw = _safe_str(getattr(provider, 'tier', '') or '').strip()
                bonus = tier_bonus.get(tier_raw, 1)
                # LLM Pass 2 `sim_proj` flag is the authoritative signal for similar project.
                # +30 boost is the greatest score component — applied when LLM confirms similarity.
                sim_matched = bool(sim_proj)
                sim_boost = 30.0 if sim_matched else 0.0
                final_score = min(100.0, base_score + bonus + sim_boost)

                # Use keyword detector ONLY to find a display title — not to override LLM verdict.
                _kw_matched, sim_title, _ratio = _detect_similar_project(
                    provider, intent, raw_query=query
                )
                # If LLM says similar but keyword detector found no title, use a generic label.
                if sim_matched and not sim_title:
                    sim_title = 'Similar project confirmed by AI'

                if sim_matched and sim_title:
                    short = sim_title[:120] + ('...' if len(sim_title) > 120 else '')
                    explanation = (
                        f'Similar project: {short} | '
                        f'{name}: Ranked #{rank_pos} by AI project relevance '
                        f'(Score: {final_score:.0f}/100, Tier: {tier_raw or "E"}, +30 similar project boost)'
                    )
                else:
                    explanation = (
                        f'{name}: Ranked #{rank_pos} by AI project relevance '
                        f'(Score: {final_score:.0f}/100, Tier: {tier_raw or "E"})'
                    )

                scores = {
                    'total': round(final_score, 2),
                    'specialty': 0.0,
                    'capabilities': round(base_score, 2),
                    'tier': float(bonus),
                    'software_bonus': 0.0,
                    'sim_boost': round(sim_boost, 2),
                    'similarity': round(similarity, 4),
                }
                scored.append((
                    final_score,
                    SearchResultItem(
                        provider=provider,
                        score=scores['total'],
                        explanation=explanation,
                        specialty_score=scores.get('specialty', 0.0),
                        capabilities_score=scores.get('capabilities', 0.0),
                        tier_score=scores.get('tier', 0.0),
                        software_bonus=scores.get('software_bonus', 0.0),
                        similarity=scores.get('similarity', similarity),
                        fallback_reason=_friendly_fallback(fallback_reason),
                        similar_project_matched=sim_matched,
                        matching_project_title=sim_title,
                    ),
                ))
            except Exception as exc:
                logger.warning(
                    f'[SEARCH] Scoring error for provider {getattr(provider, "id", "?")}: {exc}'
                )
    else:
        # ---- DETERMINISTIC FALLBACK (no API key) ----
        logger.info('[SEARCH] No API key: deterministic scoring for %d candidates', len(provider_list))
        pipeline_info['llm_reranking_success'] = False
        for provider, similarity in provider_list:
            try:
                scores = calculate_match_score(
                    provider, intent, similarity=similarity, raw_query=query
                )
                sim_matched, sim_title, _ratio = _detect_similar_project(
                    provider, intent, raw_query=query
                )
                if sim_matched:
                    scores = calculate_match_score(
                        provider, intent, similarity=similarity,
                        raw_query=query, similar_project_matched=True
                    )
                name = _display_name(provider)
                explanation = _build_explanation(
                    name, scores, intent,
                    similar_project_title=sim_title if sim_matched else ''
                )
                scored.append((
                    scores['total'],
                    SearchResultItem(
                        provider=provider,
                        score=scores['total'],
                        explanation=explanation,
                        specialty_score=scores.get('specialty', 0.0),
                        capabilities_score=scores.get('capabilities', 0.0),
                        tier_score=scores.get('tier', 0.0),
                        software_bonus=scores.get('software_bonus', 0.0),
                        similarity=scores.get('similarity', similarity),
                        fallback_reason=_friendly_fallback(fallback_reason),
                        similar_project_matched=sim_matched,
                        matching_project_title=sim_title,
                    ),
                ))
            except Exception as exc:
                logger.warning(
                    f'[SEARCH] Scoring error for provider {getattr(provider, "id", "?")}: {exc}'
                )

    # Sort by final score descending
    scored.sort(key=lambda t: t[0], reverse=True)

    # Return top_n results (None = all)
    results = [item for _, item in (scored[:top_n] if top_n is not None else scored)]

    logger.info(
        '[SEARCH] top-%d results: %s (pipeline=%s pass1=%d pass2=%d)',
        len(results),
        [(r.provider.id, round(r.score, 1)) for r in results],
        pipeline_info.get('pipeline_used'),
        pipeline_info.get('pass1_kept', 0),
        pipeline_info.get('pass2_ranked', 0),
    )
    return results, pipeline_info
