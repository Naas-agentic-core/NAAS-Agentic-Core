from collections.abc import Generator
from datetime import timedelta

import pytest

import app.auth.jwt_handler as jwt_module
from app.auth.jwt_handler import JWTHandler, get_jwt_handler


@pytest.fixture(autouse=True)
def reset_global_jwt_handler() -> Generator[None, None, None]:
    """Reset the global JWT handler before and after every test."""
    # Setup: ensure it's None before test
    jwt_module._global_jwt_handler = None
    yield
    # Teardown: ensure it's None after test
    jwt_module._global_jwt_handler = None


def test_get_jwt_handler_initialization():
    """Test that the handler initializes correctly with a valid secret key."""
    handler = get_jwt_handler(secret_key="my-super-secret-key")

    assert isinstance(handler, JWTHandler)
    assert handler.secret_key == "my-super-secret-key"


def test_get_jwt_handler_missing_secret_first_call():
    """Test that calling without a secret key on the first call raises ValueError."""
    with pytest.raises(ValueError, match="secret_key is required for first initialization"):
        get_jwt_handler()


def test_get_jwt_handler_singleton():
    """Test that subsequent calls return the exact same instance."""
    handler1 = get_jwt_handler(secret_key="first-secret-key")
    handler2 = get_jwt_handler()

    assert handler1 is handler2


def test_get_jwt_handler_ignores_new_secret():
    """Test that calling with a different secret after initialization ignores it."""
    handler1 = get_jwt_handler(secret_key="original-secret")
    handler2 = get_jwt_handler(secret_key="new-secret")

    assert handler1 is handler2
    assert handler2.secret_key == "original-secret"


def test_verify_token_valid():
    """Test that a valid token is correctly verified and decoded."""
    handler = JWTHandler(secret_key="secret")
    token = handler.create_access_token(subject="user_123", scopes=["read", "write"])

    payload = handler.verify_token(token)
    assert payload is not None
    assert payload.sub == "user_123"
    assert payload.scopes == ["read", "write"]
    assert payload.type == "access"


def test_verify_token_invalid_signature():
    """Test that verifying a token with an invalid signature returns None and logs a warning."""
    handler = JWTHandler(secret_key="secret")
    other_handler = JWTHandler(secret_key="wrong_secret")

    # Create a token with a different secret
    token = other_handler.create_access_token(subject="user_123")

    # Verify with the original handler
    payload = handler.verify_token(token)

    # jwt.InvalidTokenError should be caught and return None
    assert payload is None


def test_verify_token_expired():
    """Test that verifying an expired token returns None and logs a warning."""
    handler = JWTHandler(secret_key="secret")

    # Create a token that is already expired
    token = handler.create_access_token(subject="user_123", expires_delta=timedelta(minutes=-10))

    # Verify with the handler
    payload = handler.verify_token(token)

    # jwt.ExpiredSignatureError should be caught and return None
    assert payload is None


def test_verify_token_revoked():
    """Test that verifying a revoked token returns None."""
    handler = JWTHandler(secret_key="secret")

    token = handler.create_access_token(subject="user_123")

    # Revoke the token
    handler.revoke_token(token)

    # Verify with the handler
    payload = handler.verify_token(token)

    # Should return None because it's in revoked_tokens
    assert payload is None
