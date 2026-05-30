"""Golden eval: the assistant's deterministic guardrails must never silently regress.
Offline only (no LLM/network). Driven by tests/eval/golden_help.yaml. asyncio_mode=auto.
"""
import os
import pathlib
import yaml
import pytest

from app.services import help_service as HS
from app.services import help_actions as HA

_GOLDEN = yaml.safe_load((pathlib.Path(__file__).parent / "golden_help.yaml").read_text())


@pytest.mark.parametrize("href", _GOLDEN["valid_links"])
def test_valid_links_accepted(href):
    assert HS._is_safe_internal_path(href) is True


@pytest.mark.parametrize("href", _GOLDEN["invalid_links"])
def test_invalid_links_rejected(href):
    assert HS._is_safe_internal_path(href) is False


def test_proposable_actions_match():
    assert set(_GOLDEN["proposable_actions"]) == set(HS._PROPOSABLE_ACTIONS)


@pytest.mark.parametrize("act", _GOLDEN["forbidden_actions"])
def test_forbidden_actions_never_executable(act):
    assert act in HA.FORBIDDEN_ACTIONS
    assert act not in HA.ALL_ACTIONS


def _manual_text():
    # Read the manual the same way the service does (first existing candidate path).
    here = pathlib.Path(__file__).resolve()
    for p in [
        here.parents[3] / "docs" / "help" / "proreadyengineer_manual.md",   # repo root /docs
        here.parents[2] / "docs" / "help" / "proreadyengineer_manual.md",   # backend/docs (fallback)
        pathlib.Path("docs/help/proreadyengineer_manual.md"),
        pathlib.Path("../docs/help/proreadyengineer_manual.md"),
    ]:
        if p.exists():
            return p.read_text(encoding="utf-8")
    pytest.skip("manual not found in this checkout")


@pytest.mark.parametrize("needle", _GOLDEN["manual_must_contain"])
def test_manual_contains(needle):
    assert needle in _manual_text()


@pytest.mark.parametrize("needle", _GOLDEN["manual_must_not_contain"])
def test_manual_excludes(needle):
    assert needle not in _manual_text()


def test_extract_action_strips_and_validates():
    clean, action = HS._extract_action("ok\nPROPOSE_ACTION: accept_quote|abc|Accept it")
    assert "PROPOSE_ACTION" not in clean and action and action["type"] == "accept_quote"
    # dangerous type -> no action, line still stripped
    clean2, action2 = HS._extract_action("ok\nPROPOSE_ACTION: pay_unlock|abc|pay")
    assert action2 is None and "PROPOSE_ACTION" not in clean2
