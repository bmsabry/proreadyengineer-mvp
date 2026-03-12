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
    similar_project_matched: bool = False
    matching_project_title: str = ""


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


def _embedding_model(cfg: Dict[str, Any] = None) -> str:
    """Return embedding model name, adapting for deepinfra when needed."""
    if cfg:
        model = cfg.get('OPENAI_EMBEDDING_MODEL') or 'BAAI/bge-large-en-v1.5'
        base = cfg.get('OPENAI_API_BASE') or ''
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
        return cfg.get('OPENAI_LLM_MODEL') or 'moonshotai/kimi-k2.5'
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
            max_tokens=600,
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
    if not _has_api_key(runtime_config):
        raise ValueError('No AI API key configured - embeddings unavailable')
    client = _get_client(runtime_config)
    model  = _embedding_model(runtime_config)
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
    # Extract notable projects as a condensed text (first 500 chars of each, joined)
    notable_raw = getattr(p, 'proven_experience_notable_projects', None) or []
    if isinstance(notable_raw, str):
        import json
        try:
            notable_raw = json.loads(notable_raw)
        except Exception:
            notable_raw = [notable_raw]
    notable_text = ' '.join(str(n)[:200] for n in (notable_raw or []))[:1000]

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


def _score_notable_projects(provider, intent: dict, raw_query: str = '') -> float:
    """Notable Projects Bonus 0-15 pts.

    Awards points when provider's proven_experience_notable_projects
    descriptions contain keywords from the search query.
    """
    import json
    notable_raw = getattr(provider, 'proven_experience_notable_projects', None) or []
    if isinstance(notable_raw, str):
        try:
            notable_raw = json.loads(notable_raw)
        except Exception:
            notable_raw = [notable_raw]
    if not notable_raw:
        return 0.0

    # Build a combined text of all project descriptions
    projects_text = ' '.join(str(n) for n in notable_raw).lower()

    # Collect keywords from intent + raw query
    stop = {'and', 'the', 'for', 'with', 'that', 'this', 'from', 'have',
            'will', 'what', 'can', 'are', 'was', 'but', 'not', 'our',
            'your', 'their', 'more', 'also', 'data', 'system', 'used'}
    kw_set = set()
    q = raw_query.lower() if raw_query else ''
    for w in re.findall(r'[a-z0-9]+', q):
        if len(w) > 3 and w not in stop:
            kw_set.add(w)
    for kw in _safe_list(intent.get('inferred_keywords', [])):
        for w in re.findall(r'[a-z0-9]+', kw.lower()):
            if len(w) > 3 and w not in stop:
                kw_set.add(w)
    spec = _safe_str(intent.get('inferred_specialty', '')).lower()
    for w in re.findall(r'[a-z0-9]+', spec):
        if len(w) > 3 and w not in stop:
            kw_set.add(w)
    for cap in _safe_list(intent.get('capabilities_needed', [])):
        for w in re.findall(r'[a-z0-9]+', cap.lower()):
            if len(w) > 3 and w not in stop:
                kw_set.add(w)

    if not kw_set:
        return 0.0

    hits = sum(1 for w in kw_set if w in projects_text)
    ratio = hits / len(kw_set)
    if ratio >= 0.5:
        return 15.0
    elif ratio >= 0.3:
        return 10.0
    elif ratio >= 0.15:
        return 5.0
    elif hits > 0:
        return 3.0
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
    """Option B: Keyword-based similar project detection.

    Checks provider case studies AND notable projects for keyword matches.
    Returns (matched: bool, project_title: str, match_confidence: float)
    where matched=True means provider has conducted a similar project.
    Threshold: requires strong keyword match (>= 0.35 ratio) to flag as similar.
    """
    import json as _json

    # Build comprehensive keyword set from intent + raw query + synonyms
    stop = {'and', 'the', 'for', 'with', 'that', 'this', 'from', 'have',
            'will', 'what', 'can', 'are', 'was', 'but', 'not', 'our',
            'your', 'their', 'more', 'also', 'data', 'system', 'used',
            'design', 'analysis', 'engineering', 'service', 'test', 'project'}

    kw_set = set()
    q = raw_query.lower() if raw_query else ''
    for w in re.findall(r'[a-z0-9]+', q):
        if len(w) > 3 and w not in stop:
            kw_set.add(w)
    for kw in _safe_list(intent.get('inferred_keywords', [])):
        for w in re.findall(r'[a-z0-9]+', kw.lower()):
            if len(w) > 3 and w not in stop:
                kw_set.add(w)
    for cap in _safe_list(intent.get('capabilities_needed', [])):
        for w in re.findall(r'[a-z0-9]+', cap.lower()):
            if len(w) > 3 and w not in stop:
                kw_set.add(w)
    spec = _safe_str(intent.get('inferred_specialty', ''))  .lower()
    for w in re.findall(r'[a-z0-9]+', spec):
        if len(w) > 3 and w not in stop:
            kw_set.add(w)

    # Expand with synonyms for richer matching
    expanded_kws = _expand_keywords(list(kw_set))
    search_terms = set(expanded_kws) | kw_set

    if not search_terms:
        return False, '', 0.0

    # ── Check case studies ────────────────────────────────────────────────────
    case_studies_raw = getattr(provider, 'proven_experience_case_studies', None) or []
    if isinstance(case_studies_raw, str):
        try:
            case_studies_raw = _json.loads(case_studies_raw)
        except Exception:
            case_studies_raw = [case_studies_raw]

    # ── Check notable projects ────────────────────────────────────────────────
    notable_raw = getattr(provider, 'proven_experience_notable_projects', None) or []
    if isinstance(notable_raw, str):
        try:
            notable_raw = _json.loads(notable_raw)
        except Exception:
            notable_raw = [notable_raw]

    best_ratio = 0.0
    best_title = ''

    # Score each case study individually
    for item in case_studies_raw:
        item_str = str(item).lower()
        if len(item_str) < 10:
            continue
        hits = sum(1 for w in search_terms if w in item_str)
        ratio = hits / max(len(search_terms), 1)
        if ratio > best_ratio:
            best_ratio = ratio
            # Extract title: first sentence or first 80 chars
            raw_title = str(item)[:120].split('.')[0].strip()
            best_title = raw_title if len(raw_title) > 5 else str(item)[:80].strip()

    # Score each notable project individually
    for item in notable_raw:
        item_str = str(item).lower()
        if len(item_str) < 10:
            continue
        hits = sum(1 for w in search_terms if w in item_str)
        ratio = hits / max(len(search_terms), 1)
        if ratio > best_ratio:
            best_ratio = ratio
            raw_title = str(item)[:120].split('.')[0].strip()
            best_title = raw_title if len(raw_title) > 5 else str(item)[:80].strip()

    # Threshold: >= 0.35 ratio = similar project confirmed
    # This means at least 35% of the search terms appear in the project description
    matched = best_ratio >= 0.35

    return matched, best_title, best_ratio

def calculate_match_score(
    provider,
    intent: Dict[str, Any],
    similarity: float = 0.0,
    raw_query: str = '',
) -> Dict[str, float]:
    """Compute deterministic 100-point composite score."""
    tier_pts      = _tier_score(provider)
    specialty_pts = _specialty_score(provider, intent)
    if similarity > 0.0:
        cap_pts = round(similarity * 50.0, 2)
    else:
        cap_pts = _capabilities_score_keyword(provider, intent)
    sw_bonus       = _software_bonus(provider, intent)
    proj_bonus     = _project_types_bonus(provider, intent, raw_query)
    notable_bonus  = _score_notable_projects(provider, intent, raw_query)
    total    = min(100.0, specialty_pts + cap_pts + tier_pts + sw_bonus + proj_bonus + notable_bonus)
    return {
        'total':           round(total, 2),
        'specialty':       round(specialty_pts, 2),
        'capabilities':    round(cap_pts, 2),
        'tier':            round(tier_pts, 2),
        'software_bonus':  round(sw_bonus, 2),
        'proj_bonus':      round(proj_bonus, 2),
        'notable_bonus':   round(notable_bonus, 2),
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
            from app.models.search import IPUsageTracking
            month_str = now.strftime('%Y-%m')
            result = await db.execute(
                select(IPUsageTracking)
                .where(IPUsageTracking.ip_address == ip_address)
                .where(IPUsageTracking.usage_month == month_str)
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
            from app.models.search import IPUsageTracking
            month_str = now.strftime('%Y-%m')
            result = await db.execute(
                select(IPUsageTracking)
                .where(IPUsageTracking.ip_address == ip_address)
                .where(IPUsageTracking.usage_month == month_str)
            )
            record = result.scalar_one_or_none()
            if record:
                record.search_count = (record.search_count or 0) + 1
                record.updated_at   = now
            else:
                db.add(IPUsageTracking(
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
            "LOWER(COALESCE(CAST(p.proven_experience_notable_projects AS TEXT), ''))",
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
                result = await vec_db.execute(sql, {'vec': _json.dumps(query_vec), 'lim': max(limit, 100)})
                rows = result.mappings().all()
                logger.info(f'[SEARCH] pgvector returned {len(rows)} candidates')
                return rows, True, None
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
                rows = await _all_providers_by_tier(kw_db, base_filters, max(limit, 100))

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
) -> tuple:
    """Full spec-compliant search pipeline.
    Returns (results: List[SearchResultItem], pipeline_info: dict)
    pipeline_info contains AI diagnostics for debug display.
    """
    if filters is None:
        filters = {}

    norm_query = _normalize_query(query)
    logger.info(f'[SEARCH] query={norm_query[:100]}')

    # Initialize pipeline tracking dict
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
    }

    # Load runtime config from DB (falls back to env vars)
    from app.services.config_service import get_runtime_config
    runtime_config = await get_runtime_config(db)

    # Determine API key and source
    api_key = runtime_config.get('OPENAI_API_KEY', '') or ''
    has_key = bool(api_key) and api_key not in ('dummy-key', 'your-api-key-here', '')

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

    # Step 2 - LLM intent extraction
    llm_model = (
        runtime_config.get('OPENAI_LLM_MODEL', '')
        or runtime_config.get('OPENAI_MODEL', '')
        or 'moonshotai/kimi-k2.5'
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
            '[SEARCH] ✅ LLM response received=%s specialty=%s keywords=%s',
            pipeline_info['llm_response_received'],
            intent.get('inferred_specialty', ''),
            intent.get('inferred_keywords', []),
        )

    pipeline_info['inferred_specialty'] = intent.get('inferred_specialty', '') or ''
    pipeline_info['inferred_keywords'] = (intent.get('inferred_keywords') or [])[:8]

    # Step 4 - Embed query
    query_vec: Optional[List[float]] = None
    if has_key:
        pipeline_info['embedding_called'] = True
        try:
            query_vec = await generate_embedding(norm_query, runtime_config=runtime_config)
            pipeline_info['embedding_dims'] = len(query_vec) if query_vec else 0
            logger.info('[SEARCH] ✅ Embedding generated: %d dims', pipeline_info['embedding_dims'])
        except Exception as exc:
            pipeline_info['embedding_called'] = False
            logger.warning(f'[SEARCH] Embedding failed ({exc}), using keyword scoring')
            fallback_reason = fallback_reason or f'embedding_failed:{type(exc).__name__}'

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

    # Set final pipeline_used
    if used_vector:
        pipeline_info['pipeline_used'] = 'ai_vector'
    elif not has_key:
        pipeline_info['pipeline_used'] = 'no_api_key'
    else:
        pipeline_info['pipeline_used'] = 'keyword_fallback'
    pipeline_info['fallback_reason'] = fallback_reason

    logger.info(
        '[SEARCH] U0001f4ca Pipeline=%s | LLM=%s->%s | Embed=%s(%ddims) | Key=%s',
        pipeline_info['pipeline_used'],
        'called' if pipeline_info['llm_called'] else 'skipped',
        'received' if pipeline_info['llm_response_received'] else 'no-response',
        'ok' if pipeline_info['embedding_called'] else 'failed',
        pipeline_info['embedding_dims'],
        pipeline_info['api_key_source'],
    )

    if not rows:
        logger.info('[SEARCH] No candidates found, returning empty')
        return [], pipeline_info

    # Step 6 - Score each candidate
    scored: List[tuple] = []
    for row in rows:
        try:
            provider = _ProviderProxy(row)
            similarity = float(row.get('cosine_similarity', 0.0) or 0.0) if used_vector else 0.0
            scores = calculate_match_score(provider, intent, similarity=similarity, raw_query=query)
            name = _display_name(provider)
            # Option B: detect similar project via keyword matching
            sim_matched, sim_title, sim_ratio = _detect_similar_project(provider, intent, raw_query=query)
            explanation = _build_explanation(name, scores, intent, similar_project_title=sim_title if sim_matched else '')
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
                    similar_project_matched=sim_matched,
                    matching_project_title=sim_title,
                ),
            ))
        except Exception as exc:
            logger.warning(f'[SEARCH] Scoring error for row: {exc}')

    # Two-key sort: 1) similar_project_matched (True first), 2) total score (higher first)
    scored.sort(
        key=lambda t: (1 if t[1].similar_project_matched else 0, t[0]),
        reverse=True,
    )

    # Step 7 - Return top 5 (spec 11.10)
    results = [item for _, item in scored[:5]]

    logger.info(
        '[SEARCH] top-%d results: %s',
        len(results),
        [(r.provider.id, round(r.score, 1)) for r in results],
    )
    return results, pipeline_info
