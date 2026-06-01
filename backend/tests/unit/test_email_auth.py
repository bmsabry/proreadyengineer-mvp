"""Unit tests for the SPF/DKIM/DMARC posture evaluators (pure functions)."""
from app.services import email_auth as ea


def test_spf_softfail_pass():
    r = ea.evaluate_spf(["v=spf1 include:_spf.google.com include:amazonses.com ~all"])
    assert r["status"] == "pass"
    assert "amazonses.com" in r["detail"]


def test_spf_missing_fails():
    assert ea.evaluate_spf([])["status"] == "fail"
    assert ea.evaluate_spf(["some-other-txt=value"])["status"] == "fail"


def test_dmarc_quarantine_pass():
    r = ea.evaluate_dmarc(["v=DMARC1; p=quarantine; rua=mailto:dmarc@promechdirectory.com; adkim=s; aspf=s"])
    assert r["status"] == "pass"
    assert r["policy"] == "quarantine"
    assert r["rua"] == "mailto:dmarc@promechdirectory.com"


def test_dmarc_none_warns():
    r = ea.evaluate_dmarc(["v=DMARC1; p=none; rua=mailto:x@y.com"])
    assert r["status"] == "warn"
    assert r["policy"] == "none"


def test_dmarc_reject_pass_and_missing_rua_noted():
    r = ea.evaluate_dmarc(["v=DMARC1; p=reject"])
    assert r["status"] == "pass" and r["policy"] == "reject"
    assert "rua" in r["detail"].lower()


def test_dmarc_missing_fails():
    assert ea.evaluate_dmarc([])["status"] == "fail"


def test_dkim_present_pass_missing_fail():
    assert ea.evaluate_dkim(["p=MIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQKBgQCeRo2bCD0Sfd1XvKIkM7N1Ux14UDQ"]) ["status"] == "pass"
    assert ea.evaluate_dkim([])["status"] == "fail"


def test_overall_status_precedence():
    p = {"status": "pass"}; w = {"status": "warn"}; f = {"status": "fail"}
    assert ea.overall_status(p, p, p)["overall"] == "pass"
    assert ea.overall_status(p, w, p)["overall"] == "warn"
    assert ea.overall_status(p, w, f)["overall"] == "fail"
