"""Inbound-email quote stripping: keep only the sender's new text. asyncio_mode=auto."""
from app.services.support_service import strip_quoted_reply


def test_gmail_on_wrote_quote_is_stripped():
    body = ("Resetting didnt work. what else can be done.\n\n"
            "On Sunday, May 31, 2026 at 04:16:01 AM EDT, ProMechDirectory Support "
            "<info@mail.promechdirectory.com> wrote:\n\n"
            "No, we actually donot charge except what was agreed upon. Try resetting.")
    out = strip_quoted_reply(body)
    assert out == "Resetting didnt work. what else can be done."
    assert "wrote:" not in out and "Try resetting" not in out


def test_outlook_original_message_separator():
    body = ("Here is my new reply.\n"
            "-----Original Message-----\n"
            "From: Support\nSent: yesterday\nblah blah quoted")
    out = strip_quoted_reply(body)
    assert out == "Here is my new reply."


def test_angle_bracket_quote_lines_trimmed():
    body = "Thanks, that worked!\n> previous line one\n> previous line two"
    out = strip_quoted_reply(body)
    assert out == "Thanks, that worked!"


def test_no_quote_returns_unchanged():
    body = "Just a plain message with no quoted history."
    assert strip_quoted_reply(body) == body


def test_safety_net_never_empties_message():
    # If the whole body looks like a quote, keep the original rather than lose it.
    body = "On Monday, X wrote:\n> only quoted content here"
    out = strip_quoted_reply(body)
    assert out.strip() != ""


def test_empty_input():
    assert strip_quoted_reply("") == ""
    assert strip_quoted_reply(None) == ""
