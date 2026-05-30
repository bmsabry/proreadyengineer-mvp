"""Phase 3: SUGGESTED_LINKS parsing + internal-path validation. Pure. asyncio_mode=auto."""
from app.services import help_service as H


def test_extracts_valid_internal_links_and_strips_line():
    reply = ("Here's how to submit an RFQ.\n"
             "SUGGESTED_LINKS: /customer/rfq/new|Submit a new RFQ ;; /customer/quotes|Review quotes")
    clean, links = H._extract_links(reply)
    assert "SUGGESTED_LINKS" not in clean
    assert clean.strip() == "Here's how to submit an RFQ."
    assert links == [
        {"href": "/customer/rfq/new", "label": "Submit a new RFQ"},
        {"href": "/customer/quotes", "label": "Review quotes"},
    ]


def test_rejects_external_and_unknown_paths():
    reply = "x\nSUGGESTED_LINKS: https://evil.com|Hack ;; /admin/users|Admin ;; //x|bad ;; /provider/upgrade|Upgrade"
    clean, links = H._extract_links(reply)
    # only the safe internal allowlisted path survives
    assert links == [{"href": "/provider/upgrade", "label": "Upgrade"}]


def test_caps_at_three_links():
    paths = " ;; ".join(f"/customer/rfq/new|L{i}" for i in range(6))
    _, links = H._extract_links("hi\nSUGGESTED_LINKS: " + paths)
    assert len(links) == 3


def test_no_sentinel_returns_reply_unchanged():
    clean, links = H._extract_links("just a normal answer")
    assert clean == "just a normal answer" and links == []


def test_safe_internal_path_helper():
    assert H._is_safe_internal_path("/customer/dashboard")
    assert H._is_safe_internal_path("/billing")
    assert not H._is_safe_internal_path("/admin/settings")
    assert not H._is_safe_internal_path("https://x.com")
    assert not H._is_safe_internal_path("//evil")
    assert not H._is_safe_internal_path("relative/path")
