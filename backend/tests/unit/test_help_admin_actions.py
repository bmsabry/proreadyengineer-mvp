"""Admin support-ticket actions: role gating + page ticket-id parsing. asyncio_mode=auto."""
import uuid, pytest
from app.services import help_actions as HA
from app.services import help_service as HS


class _U:
    def __init__(self, roles):
        self.id = uuid.uuid4(); self.roles = roles


def test_admin_actions_in_allowlist_not_forbidden():
    assert HA.ADMIN_ACTIONS == {"resolve_ticket", "escalate_ticket", "archive_ticket", "mark_ticket_spam"}
    for a in HA.ADMIN_ACTIONS:
        assert a in HA.ALL_ACTIONS and a not in HA.FORBIDDEN_ACTIONS


async def test_non_admin_cannot_resolve_ticket():
    user = _U(["customer"])
    with pytest.raises(Exception) as ei:
        await HA.execute_action(db=None, user=user, action_type="resolve_ticket",
                                params={"ticket_id": str(uuid.uuid4())}, autonomous_enabled=False)
    assert getattr(ei.value, "status_code", None) == 403


async def test_admin_resolve_missing_ticket_id_400():
    user = _U(["admin"])
    with pytest.raises(Exception) as ei:
        await HA.execute_action(db=None, user=user, action_type="resolve_ticket",
                                params={}, autonomous_enabled=False)
    assert getattr(ei.value, "status_code", None) == 400


def test_ticket_id_parsed_from_admin_page():
    tid = "6dd448bb-16e6-4158-90cb-81c360aa9145"
    assert HS._ticket_id_from_page(f"/admin/support/{tid}") == tid
    assert HS._ticket_id_from_page("/admin/dashboard") is None
    assert HS._ticket_id_from_page(None) is None


def test_admin_actions_proposable():
    for a in ["resolve_ticket", "escalate_ticket", "archive_ticket", "mark_ticket_spam"]:
        assert a in HS._PROPOSABLE_ACTIONS


def test_payments_still_forbidden_even_for_admin():
    for f in ["pay_unlock", "sign_nda"]:
        assert f in HA.FORBIDDEN_ACTIONS and f not in HA.ALL_ACTIONS
