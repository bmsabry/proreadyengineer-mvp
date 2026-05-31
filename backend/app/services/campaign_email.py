"""Deliverability-safe email shell for marketing/campaign emails.

The AI (or an admin) writes the body in plain, natural language; this module wraps it
in a clean, inbox-friendly HTML shell + plain-text alternative and the legally-required
CAN-SPAM footer (physical address + unsubscribe). Keeping format here means authors never
hand-write fragile HTML, and every campaign email is consistent and compliant.
"""
from __future__ import annotations

import html as _html
import re as _re
from typing import Dict, Optional

# CAN-SPAM requires a valid physical postal address in marketing email. Override via
# runtime config OPERATING/COMPANY address if you add one; this is the documented default.
DEFAULT_COMPANY_NAME = "ProMechDirectory"
DEFAULT_COMPANY_ADDRESS = "ProMechDirectory — see promechdirectory.com/contact for our mailing address"


def _looks_like_html(body: str) -> bool:
    return bool(_re.search(r"<\s*(p|div|br|a|h[1-6]|ul|ol|table|span)\b", body or "", _re.I))


def body_to_html(body: str) -> str:
    """Turn a plain-text body into safe minimal HTML (paragraphs + autolinked URLs).
    If the body already contains HTML tags, it's passed through untouched."""
    if not body:
        return ""
    if _looks_like_html(body):
        return body
    esc = _html.escape(body.strip())
    # autolink bare URLs
    esc = _re.sub(r"(https?://[^\s<]+)", r'<a href="\1">\1</a>', esc)
    paras = [p.strip().replace("\n", "<br>") for p in esc.split("\n\n") if p.strip()]
    return "".join(f'<p style="margin:0 0 16px;">{p}</p>' for p in paras)


def html_to_text(html_body: str) -> str:
    """Crude HTML -> plain text for the text/plain alternative part."""
    if not html_body:
        return ""
    t = _re.sub(r"(?i)<br\s*/?>", "\n", html_body)
    t = _re.sub(r"(?i)</p>", "\n\n", t)
    t = _re.sub(r"(?i)<a [^>]*href=[\"']([^\"']+)[\"'][^>]*>(.*?)</a>", r"\2 (\1)", t)
    t = _re.sub(r"<[^>]+>", "", t)
    t = _html.unescape(t)
    t = _re.sub(r"\n{3,}", "\n\n", t)
    return t.strip()


def wrap_campaign_email(
    inner_html: str,
    *,
    unsubscribe_url: str,
    company_name: str = DEFAULT_COMPANY_NAME,
    company_address: str = DEFAULT_COMPANY_ADDRESS,
    preheader: str = "",
) -> str:
    """Wrap an authored body in a deliverability-safe, on-brand HTML email shell with a
    CAN-SPAM footer (physical address + unsubscribe link)."""
    pre = (f'<div style="display:none;max-height:0;overflow:hidden;opacity:0;">{_html.escape(preheader)}</div>'
           if preheader else "")
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta name="color-scheme" content="light only"></head>
<body style="margin:0;padding:0;background:#f1f5f9;font-family:Arial,Helvetica,sans-serif;color:#0f172a;">
{pre}
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f1f5f9;padding:24px 0;">
<tr><td align="center">
<table role="presentation" width="600" cellpadding="0" cellspacing="0" style="max-width:600px;background:#ffffff;border-radius:12px;overflow:hidden;border:1px solid #e2e8f0;">
<tr><td style="background:#0F2B54;padding:18px 28px;color:#ffffff;font-size:18px;font-weight:bold;">{_html.escape(company_name)}</td></tr>
<tr><td style="padding:28px;font-size:15px;line-height:1.6;color:#1e293b;">{inner_html}</td></tr>
<tr><td style="padding:18px 28px;background:#f8fafc;border-top:1px solid #e2e8f0;font-size:12px;line-height:1.5;color:#64748b;">
{_html.escape(company_address)}<br>
You received this email because your firm is listed in the {_html.escape(company_name)} engineering directory.
<a href="{unsubscribe_url}" style="color:#64748b;text-decoration:underline;">Unsubscribe</a>.
</td></tr>
</table>
</td></tr></table>
</body></html>"""


def build_unsubscribe_headers(unsubscribe_url: str, mailto: Optional[str] = None) -> Dict[str, str]:
    """RFC 8058 one-click unsubscribe headers — mandatory for bulk marketing in 2026.

    Gmail/Yahoo require BOTH a List-Unsubscribe (with an https URL, and optionally a
    mailto) and List-Unsubscribe-Post for true one-click.
    """
    targets = [f"<{unsubscribe_url}>"]
    if mailto:
        targets.insert(0, f"<mailto:{mailto}?subject=unsubscribe>")
    return {
        "List-Unsubscribe": ", ".join(targets),
        "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
    }
