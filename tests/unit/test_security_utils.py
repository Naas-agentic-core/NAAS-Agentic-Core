from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import jwt

from app.core import security
from app.security.passwords import pwd_context


def test_generate_service_token_includes_subject(monkeypatch) -> None:
    secret_key = "test-secret-key-that-is-very-long-and-secure-enough-for-tests-v4"
    monkeypatch.setattr(security, "get_settings", lambda: SimpleNamespace(SECRET_KEY=secret_key))

    token = security.generate_service_token("user-123")

    payload = jwt.decode(token, secret_key, algorithms=["HS256"])

    assert payload["sub"] == "user-123"
    assert "exp" in payload
    assert "iat" in payload


def test_generate_service_token_has_short_expiry(monkeypatch) -> None:
    secret_key = "test-secret-key-that-is-very-long-and-secure-enough-for-tests-v4"
    monkeypatch.setattr(security, "get_settings", lambda: SimpleNamespace(SECRET_KEY=secret_key))

    token = security.generate_service_token("service")
    payload = jwt.decode(token, secret_key, algorithms=["HS256"])

    exp = datetime.fromtimestamp(payload["exp"], tz=UTC)
    iat = datetime.fromtimestamp(payload["iat"], tz=UTC)

    assert exp > iat
    assert exp - iat <= timedelta(minutes=5, seconds=5)


def test_verify_password_matches_hash() -> None:
    hashed = pwd_context.hash("super-secret")

    assert security.verify_password("super-secret", hashed) is True
    assert security.verify_password("wrong", hashed) is False
