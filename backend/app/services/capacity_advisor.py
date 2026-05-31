"""Capacity-planning math for the admin Bandwidth panel.

Pure functions (no I/O) so they are unit-testable: parse Render metric time series,
summarize (avg/peak/p95), compute a recent-vs-earlier trend, and turn utilization +
current plan into a plain-language scale recommendation. The endpoint does the HTTP.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

# Render instance plans (web/private services), smallest -> largest, with the CPU/RAM
# each provides. Used to (a) know current capacity and (b) name the next size up.
# Figures per Render's published instance types (2026); update if Render changes them.
RENDER_PLANS: List[Dict[str, Any]] = [
    {"plan": "free",      "label": "Free",       "cpu": 0.1, "ram_gb": 0.5, "usd_mo": 0},
    {"plan": "starter",   "label": "Starter",    "cpu": 0.5, "ram_gb": 0.5, "usd_mo": 7},
    {"plan": "standard",  "label": "Standard",   "cpu": 1.0, "ram_gb": 2.0, "usd_mo": 25},
    {"plan": "pro",       "label": "Pro",        "cpu": 2.0, "ram_gb": 4.0, "usd_mo": 85},
    {"plan": "pro plus",  "label": "Pro Plus",   "cpu": 4.0, "ram_gb": 8.0, "usd_mo": 175},
    {"plan": "pro max",   "label": "Pro Max",    "cpu": 4.0, "ram_gb": 16.0, "usd_mo": 225},
    {"plan": "pro ultra", "label": "Pro Ultra",  "cpu": 8.0, "ram_gb": 32.0, "usd_mo": 450},
]


def _plan_index(plan_name: Optional[str]) -> int:
    p = (plan_name or "").strip().lower()
    for i, e in enumerate(RENDER_PLANS):
        if e["plan"] == p:
            return i
    # default to 'starter' if unknown (our services run starter)
    return 1


def next_plan(plan_name: Optional[str]) -> Optional[Dict[str, Any]]:
    i = _plan_index(plan_name)
    return RENDER_PLANS[i + 1] if i + 1 < len(RENDER_PLANS) else None


def parse_series(series: Any) -> List[Tuple[str, float]]:
    """Flatten a Render metrics response (list of time series) into (timestamp, value)
    points, summed across series at each timestamp (handles multi-instance). Robust to
    empty / malformed payloads."""
    if not isinstance(series, list):
        return []
    bucket: Dict[str, float] = {}
    for ts_obj in series:
        if not isinstance(ts_obj, dict):
            continue
        for v in (ts_obj.get("values") or []):
            if not isinstance(v, dict):
                continue
            ts = v.get("timestamp")
            val = v.get("value")
            if ts is None or val is None:
                continue
            try:
                bucket[str(ts)] = bucket.get(str(ts), 0.0) + float(val)
            except (TypeError, ValueError):
                continue
    return sorted(bucket.items(), key=lambda kv: kv[0])


def summarize(points: List[Tuple[str, float]]) -> Dict[str, Any]:
    """avg / peak / p95 / latest / count + a downsampled spark list (<=40 pts)."""
    vals = [p[1] for p in points]
    if not vals:
        return {"avg": None, "peak": None, "p95": None, "latest": None, "count": 0, "spark": []}
    s = sorted(vals)
    p95 = s[min(len(s) - 1, int(round(0.95 * (len(s) - 1))))]
    # downsample to ~40 points for the sparkline
    step = max(1, len(vals) // 40)
    spark = [round(v, 4) for v in vals[::step]][:40]
    return {
        "avg": round(sum(vals) / len(vals), 4),
        "peak": round(max(vals), 4),
        "p95": round(p95, 4),
        "latest": round(vals[-1], 4),
        "count": len(vals),
        "spark": spark,
    }


def trend_pct(points: List[Tuple[str, float]]) -> Optional[float]:
    """Percent change of the recent half's average vs the earlier half's average.
    Positive = growing load. None if not enough data."""
    vals = [p[1] for p in points]
    if len(vals) < 6:
        return None
    mid = len(vals) // 2
    earlier = vals[:mid]
    recent = vals[mid:]
    ea = sum(earlier) / len(earlier) if earlier else 0.0
    ra = sum(recent) / len(recent) if recent else 0.0
    if ea <= 0:
        return None
    return round((ra - ea) / ea * 100.0, 1)


def recommend(cpu_pct: Optional[float], mem_pct: Optional[float],
              cpu_trend: Optional[float], current_plan: Optional[str]) -> Dict[str, Any]:
    """Rule-based capacity recommendation from peak utilization % and growth trend.

    cpu_pct / mem_pct are PEAK utilization (0-100) of the instance's capacity.
    Returns {status: healthy|watch|scale_now, headline, detail, suggested_plan}.
    """
    worst = max([x for x in (cpu_pct, mem_pct) if x is not None], default=None)
    nxt = next_plan(current_plan)
    nxt_label = nxt["label"] if nxt else "a larger instance (contact Render)"

    if worst is None:
        return {"status": "unknown", "headline": "Not enough metric data yet",
                "detail": "Render hasn't returned utilization data for this window. "
                          "Metrics need a paid instance and some traffic; check back after more usage.",
                "suggested_plan": None}

    growing = (cpu_trend is not None and cpu_trend >= 25)

    if worst >= 85:
        return {"status": "scale_now",
                "headline": f"Scale up soon — peak utilization {worst:.0f}%",
                "detail": (f"You're regularly hitting {worst:.0f}% of this instance's capacity. "
                           f"Headroom for traffic spikes is thin; upgrade to {nxt_label} before "
                           "performance degrades."),
                "suggested_plan": nxt}
    if worst >= 70 or (worst >= 55 and growing):
        extra = " and load is trending up" if growing else ""
        return {"status": "watch",
                "headline": f"Watch closely — peak {worst:.0f}%{extra}",
                "detail": (f"Peak utilization is {worst:.0f}%{extra}. You're fine for now, but plan to "
                           f"move to {nxt_label} if peaks cross ~85% or the trend keeps climbing."),
                "suggested_plan": nxt}
    return {"status": "healthy",
            "headline": f"Healthy — peak {worst:.0f}% of capacity",
            "detail": ("Plenty of headroom. No upgrade needed; keep an eye on the trend as traffic grows."
                       + (" Load is trending up, so revisit if it accelerates." if growing else "")),
            "suggested_plan": None}
