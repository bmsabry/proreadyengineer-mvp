"""The assistant must not carry a customer's identity/contact into the
provider-visible RFQ description (or vice versa for quotes)."""
import app.services.help_actions as ha


class _U:
    full_name = "Bassam 12"
    business_name = "Pro12"
    first_name = "Bassam"
    last_name = "12"
    email = "bassam12@proreadyengineerteam.testinator.email"


SRC = """REQUEST FOR QUOTE Badger Control Valve Sizing Services

CUSTOMER INFORMATION
Customer Name: Bassam 12
Company: Pro12
Email: bassam12@proreadyengineerteam.testinator.email
Phone: +1 (555) 123-4567
Date: March 24, 2026

PROJECT OVERVIEW
Pro12 is seeking professional engineering services for the sizing and selection of
Badger control valves for combustion applications, per ISA-75.01.01, with Cv
calculations and Stellite vs Stainless Steel trim material selection.
"""


def test_scrub_removes_identity_and_contact():
    out = ha._scrub_pii(SRC, _U())
    low = out.lower()
    assert "bassam" not in low, out
    assert "pro12" not in low, out
    assert "@" not in out, out
    assert "555" not in out, out
    assert "customer name" not in low
    assert "customer information" not in low
    # Technical scope must survive.
    assert "isa-75.01.01" in low
    assert "cv" in low
    assert "combustion" in low
    assert "stellite" in low


def test_scrub_handles_empty():
    assert ha._scrub_pii("", _U()) == ""
    assert ha._scrub_pii(None, _U()) is None
