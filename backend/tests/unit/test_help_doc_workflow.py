"""Doc-driven workflow safety: attachment key-prefix ownership + action allowlist.
Pure where possible. asyncio_mode=auto.
"""
import uuid
import pytest
from app.services import help_actions as HA


class _U:
    def __init__(self, roles=None, autonomous=True):
        self.id = uuid.UUID("11111111-1111-1111-1111-111111111111")
        self.roles = roles or ["customer"]
        self.email = "u@example.com"
        self.full_name = "U Name"
        self.business_name = "U Co"
        self.agent_autonomous_enabled = autonomous


def test_validate_attachments_only_keeps_own_prefix():
    u = _U()
    mine = f"assistant-uploads/{u.id}/abc/spec.pdf"
    theirs = "assistant-uploads/22222222-2222-2222-2222-222222222222/x/secret.pdf"
    external = "https://evil.com/x.pdf"
    traversal = f"assistant-uploads/{u.id}/../../etc/passwd"
    atts = [
        {"key": mine, "filename": "spec.pdf", "excerpt": "hi"},
        {"key": theirs, "filename": "secret.pdf"},
        {"key": external, "filename": "x.pdf"},
        {"key": traversal, "filename": "p"},
    ]
    out = HA._validate_attachments(u, atts)
    keys = [a["key"] for a in out]
    assert keys == [mine]  # only the caller's own, no foreign / external / traversal


def test_validate_attachments_caps_and_handles_junk():
    u = _U()
    base = f"assistant-uploads/{u.id}/"
    atts = [{"key": base + f"{i}/f{i}.pdf"} for i in range(8)] + [None, "notadict", {"nokey": 1}]
    out = HA._validate_attachments(u, atts)
    assert len(out) == 5  # capped


def test_doc_actions_are_in_autonomous_set_not_forbidden():
    assert "create_rfq_from_docs" in HA.AUTONOMOUS_ACTIONS
    assert "submit_quote_from_docs" in HA.AUTONOMOUS_ACTIONS
    # still never financial/legal
    for f in ["pay", "pay_unlock", "sign_nda", "countersign_nda"]:
        assert f in HA.FORBIDDEN_ACTIONS and f not in HA.ALL_ACTIONS


async def test_doc_action_rejected_when_autonomy_off():
    u = _U(autonomous=False)
    with pytest.raises(Exception) as ei:
        await HA.execute_action(db=None, user=u, action_type="create_rfq_from_docs",
                                params={"attachments": [{"key": f"assistant-uploads/{u.id}/a/x.pdf"}]},
                                autonomous_enabled=False)
    assert getattr(ei.value, "status_code", None) == 403


async def test_doc_action_with_no_valid_attachments_400():
    u = _U(autonomous=True)
    with pytest.raises(Exception) as ei:
        await HA.execute_action(db=None, user=u, action_type="create_rfq_from_docs",
                                params={"attachments": [{"key": "assistant-uploads/OTHER/x.pdf"}]},
                                autonomous_enabled=True)
    assert getattr(ei.value, "status_code", None) == 400
