"""Inbound webhook must ignore mail addressed to a different product.

Resend webhooks subscribe to EVENT TYPES, not domains — there is no
per-domain filter in the dashboard or the API, so every `email.received`
in the Resend account is delivered to every endpoint listening for that
event. The same Resend account serves proreadyengineer.com, which runs a
separate support desk with its own inbound webhook.

Without the recipient check these two standalone products would ingest
each other's customers and auto-reply under the wrong brand. These tests
are the guard on that; treat a failure here as a data-isolation defect,
not a cosmetic one.
"""
import pytest

from app.api.endpoints.support import RECEIVING_DOMAINS, _addressed_to_us


def call(payload=None, data=None, headers=None):
    return _addressed_to_us(payload or {}, data or {}, headers or {})


class TestOurMail:
    """Anything genuinely addressed to ProMechDirectory must be accepted."""

    @pytest.mark.parametrize(
        "recipient",
        [
            "info@mail.promechdirectory.com",
            "support@promechdirectory.com",
            "INFO@MAIL.PROMECHDIRECTORY.COM",
            "ProMech Support <info@mail.promechdirectory.com>",
        ],
    )
    def test_received_for_is_ours(self, recipient):
        assert call(data={"received_for": recipient}) is True

    def test_to_as_list(self):
        assert call(data={"to": ["info@mail.promechdirectory.com"]}) is True

    def test_ours_anywhere_in_a_multi_recipient_list(self):
        assert call(
            data={"to": ["someone@elsewhere.example", "info@promechdirectory.com"]}
        ) is True

    def test_comma_separated_string(self):
        assert call(
            data={"to": "a@elsewhere.example, support@promechdirectory.com"}
        ) is True

    def test_falls_back_to_the_to_header(self):
        assert call(headers={"to": "info@mail.promechdirectory.com"}) is True


class TestOtherBrands:
    """Mail for the training business must be dropped, silently and totally."""

    @pytest.mark.parametrize(
        "recipient",
        [
            "info@mail.proreadyengineer.com",
            "support@proreadyengineer.com",
            "noreply@mail.proreadyengineer.com",
        ],
    )
    def test_proreadyengineer_mail_is_rejected(self, recipient):
        assert call(data={"received_for": recipient}) is False

    def test_rejected_even_when_the_sender_looks_normal(self):
        assert call(
            data={
                "from": "student@example.com",
                "received_for": "info@mail.proreadyengineer.com",
                "to": ["info@mail.proreadyengineer.com"],
            }
        ) is False

    @pytest.mark.parametrize(
        "lookalike",
        [
            "info@mail.promechdirectory.com.evil.example",
            "info@notmail.promechdirectory.com",
            "info@promechdirectory.com.attacker.test",
        ],
    )
    def test_lookalike_domains_do_not_pass(self, lookalike):
        assert call(data={"received_for": lookalike}) is False


class TestUnknownRecipient:
    """No recognisable recipient is handled by a human, not dropped.

    The cross-brand fan-out always carries an explicit recipient, so being
    permissive here does not reopen the hole — but it does keep an oddly
    shaped payload from silently losing a real customer's message.
    """

    @pytest.mark.parametrize("payload", [{}, {"to": []}, {"to": ""}, {"to": ["not-an-address"]}])
    def test_unknown_is_treated_as_ours(self, payload):
        assert call(data=payload) is True


def test_receiving_domains_is_explicit():
    """A wildcard here would silently undo every test above."""
    assert RECEIVING_DOMAINS == {"mail.promechdirectory.com", "promechdirectory.com"}
