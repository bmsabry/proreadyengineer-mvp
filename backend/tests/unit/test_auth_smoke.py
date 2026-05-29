"""Auth smoke tests against the CURRENT auth_service API.

Self-contained (no DB), fast, and meaningful. Replaces coverage from the drifted
legacy test_auth_service.py until that suite is rewritten.
"""
from datetime import datetime, timedelta, timezone

import pytest

from app.services.auth_service import (
    hash_password,
    verify_password,
    validate_password_strength,
    create_access_token,
    decode_token,
    _as_aware,
)


class TestPasswordHashing:
    def test_hash_and_verify_roundtrip(self):
        h = hash_password("StrongPassw0rd!23")
        assert h != "StrongPassw0rd!23"          # never store plaintext
        assert verify_password("StrongPassw0rd!23", h) is True
        assert verify_password("wrong", h) is False


class TestPasswordPolicy:
    def test_strong_password_accepted(self):
        validate_password_strength("StrongPassw0rd!23")  # must not raise

    @pytest.mark.parametrize("weak", [
        "short1!A",            # too short
        "alllowercase123!",    # no uppercase
        "ALLUPPERCASE123!",    # no lowercase
        "NoNumbersHere!!",     # no digit
        "NoSpecialChar123",    # no special
    ])
    def test_weak_passwords_rejected(self, weak):
        with pytest.raises(ValueError):
            validate_password_strength(weak)


class TestJWT:
    def test_access_token_roundtrip(self):
        import uuid
        uid = uuid.uuid4()
        token = create_access_token(uid)
        payload = decode_token(token)
        assert payload["sub"] == str(uid)
        assert payload["type"] == "access"
        assert "exp" in payload and "jti" in payload

    def test_tampered_token_rejected(self):
        import uuid
        token = create_access_token(uuid.uuid4())
        with pytest.raises(Exception):
            decode_token(token + "tampered")


class TestDatetimeSafety:
    """Guards the auth_service.py:266/110 fix: naive vs aware comparison must not crash."""
    def test_as_aware_coerces_naive_to_utc(self):
        naive = datetime.utcnow()
        aware = _as_aware(naive)
        assert aware.tzinfo is not None
        # Comparison with an aware 'now' must not raise.
        _ = aware < datetime.now(timezone.utc)

    def test_as_aware_passthrough_for_aware(self):
        aware_in = datetime.now(timezone.utc)
        assert _as_aware(aware_in) == aware_in

    def test_as_aware_handles_none(self):
        assert _as_aware(None) is None
