"""Email authentication (SPF / DKIM / DMARC) DNS posture evaluation.

Pure evaluator functions (unit-tested) + a DNS-over-HTTPS TXT fetch helper.
Used by the admin "Email Authentication" panel to show the live sending-domain
posture without needing access to the DMARC report mailbox.
"""
from __future__ import annotations

import re

import httpx

DOH_URL = "https://dns.google/resolve"


async def fetch_txt(name: str) -> list[str]:
    """Fetch TXT records for a DNS name via DNS-over-HTTPS (Google). Best-effort:
    returns [] on any error so the panel degrades gracefully."""
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.get(DOH_URL, params={"name": name, "type": "TXT"})
            resp.raise_for_status()
            data = resp.json()
    except Exception:
        return []
    out: list[str] = []
    for ans in (data.get("Answer") or []):
        if ans.get("type") != 16:  # 16 = TXT
            continue
        raw = (ans.get("data") or "").strip()
        chunks = re.findall(r'"((?:[^"\\]|\\.)*)"', raw)
        out.append("".join(chunks) if chunks else raw.strip('"'))
    return out


def evaluate_spf(txts: list[str]) -> dict:
    spf = next((t for t in txts if t.lower().startswith("v=spf1")), None)
    if not spf:
        return {
            "status": "fail",
            "record": None,
            "detail": "No SPF record found. Add a v=spf1 TXT record so receivers can verify your senders.",
        }
    includes = [p for p in spf.split() if p.lower().startswith("include:")]
    if "-all" in spf:
        enforce, status = "strict (-all)", "pass"
    elif "~all" in spf:
        enforce, status = "soft-fail (~all)", "pass"
    elif "?all" in spf:
        enforce, status = "neutral (?all)", "warn"
    else:
        enforce, status = "no 'all' mechanism", "warn"
    detail = "SPF present ({}).".format(enforce)
    if includes:
        detail += " Senders: " + ", ".join(i.split(":", 1)[1] for i in includes) + "."
    return {"status": status, "record": spf, "detail": detail}


def evaluate_dkim(txts: list[str], selector: str = "resend") -> dict:
    rec = next((t for t in txts if "p=" in t and ("dkim" in t.lower() or "k=rsa" in t.lower() or t.strip().startswith("p="))), None)
    if rec is None:
        rec = next((t for t in txts if "p=" in t and len(t) > 80), None)
    if rec:
        shown = (rec[:60] + "...") if len(rec) > 60 else rec
        return {
            "status": "pass",
            "selector": selector,
            "record": shown,
            "detail": "DKIM key published at {}._domainkey.".format(selector),
        }
    return {
        "status": "fail",
        "selector": selector,
        "record": None,
        "detail": "No DKIM key found at {}._domainkey. Add the DKIM record from your email provider.".format(selector),
    }


def evaluate_dmarc(txts: list[str]) -> dict:
    rec = next((t for t in txts if t.lower().startswith("v=dmarc1")), None)
    if not rec:
        return {
            "status": "fail",
            "record": None,
            "policy": None,
            "rua": None,
            "detail": "No DMARC record at _dmarc. Add one to protect your domain from spoofing.",
        }
    tags: dict[str, str] = {}
    for part in rec.split(";"):
        if "=" in part:
            k, v = part.split("=", 1)
            tags[k.strip().lower()] = v.strip()
    policy = tags.get("p")
    rua = tags.get("rua")
    if policy == "reject":
        status, msg = "pass", "Strictest policy: spoofed mail is rejected outright."
    elif policy == "quarantine":
        status, msg = "pass", "Spoofed mail is sent to the recipient's spam/junk folder."
    elif policy == "none":
        status, msg = "warn", "Monitoring only - spoofed mail still reaches inboxes. Consider tightening to quarantine."
    else:
        status, msg = "warn", "Policy '{}'.".format(policy)
    if not rua:
        msg += " No aggregate-report address (rua=) set."
    return {"status": status, "record": rec, "policy": policy, "rua": rua, "detail": msg}


def overall_status(*checks: dict) -> dict:
    statuses = [c.get("status") for c in checks]
    if "fail" in statuses:
        return {"overall": "fail", "message": "One or more email-authentication records need attention."}
    if "warn" in statuses:
        return {"overall": "warn", "message": "Email authentication is working but could be hardened."}
    return {"overall": "pass", "message": "SPF, DKIM, and DMARC are all in good shape."}
