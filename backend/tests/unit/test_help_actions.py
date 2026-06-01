"""Phase 4: PROPOSE_ACTION parsing + executable-action allowlist. Pure. asyncio_mode=auto."""
from app.services import help_service as H
from app.api.endpoints import help as HELP


def test_extracts_valid_mark_contacted_proposal():
    reply = ("I'll mark that one as contacted once you confirm.\n"
             "PROPOSE_ACTION: mark_contacted|11111111-1111-1111-1111-111111111111|Mark Acme as contacted")
    clean, action = H._extract_action(reply)
    assert "PROPOSE_ACTION" not in clean
    assert clean.strip().startswith("I'll mark")
    assert action == {
        "type": "mark_contacted",
        "quote_id": "11111111-1111-1111-1111-111111111111",
        "summary": "Mark Acme as contacted",
    }


def test_rejects_unknown_or_dangerous_action_types():
    # Truly forbidden / unknown types are never turned into a proposal.
    for bad in ["delete_account", "pay_invoice", "sign_nda", "launch_missiles"]:
        clean, action = H._extract_action(f"sure\nPROPOSE_ACTION: {bad}|x|do it")
        assert action is None              # not proposable
        assert "PROPOSE_ACTION" not in clean  # control line still stripped

    # Autonomous actions ARE proposable now (execution is gated server-side by the
    # autonomous flag + ownership check), so the model may propose them.
    for ok in ["accept_quote", "cancel_rfq", "withdraw_quote"]:
        _, action = H._extract_action(f"sure\nPROPOSE_ACTION: {ok}|x|do it")
        assert action is not None and action["type"] == ok


def test_missing_quote_id_yields_no_action():
    _, action = H._extract_action("ok\nPROPOSE_ACTION: mark_contacted")
    assert action is None


def test_no_prefix_returns_unchanged():
    clean, action = H._extract_action("just a normal answer")
    assert clean == "just a normal answer" and action is None


def test_executable_allowlist_is_tiny_and_safe():
    # Only the two reversible toggles are executable server-side.
    assert HELP._EXECUTABLE_ACTIONS == {"mark_contacted", "undo_mark_contacted", "update_profile_from_docs"}
    for forbidden in ["pay", "sign_nda", "submit_quote", "accept_quote", "cancel_rfq", "delete"]:
        assert forbidden not in HELP._EXECUTABLE_ACTIONS
