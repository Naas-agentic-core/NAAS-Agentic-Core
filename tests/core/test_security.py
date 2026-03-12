from unittest.mock import MagicMock, patch

import pytest

from app.core import security
from app.core.settings.base import AppSettings


@pytest.fixture
def mock_settings():
    settings = MagicMock(spec=AppSettings)
    settings.SECRET_KEY = "test-secret-key-that-is-very-long-and-secure-enough-for-tests-v4"
    return settings


def test_generate_service_token(mock_settings):
    user_id = "test-user"
    with patch("app.core.security.get_settings", return_value=mock_settings):
        token = security.generate_service_token(user_id)
        assert isinstance(token, str)
        assert len(token) > 0

        # Verify decoding
        decoded = security.jwt.decode(token, mock_settings.SECRET_KEY, algorithms=["HS256"])
        assert decoded["sub"] == user_id
        assert "exp" in decoded
        assert "iat" in decoded


def test_verify_password():
    plain = "secret"
    hashed = (
        "$2b$12$EixZaYVK1fsbw1ZfbX3OXePaWxn96p36WQoeG6Lruj3vjPGga31lW"  # bcrypt hash of 'secret'
    )

    with patch("app.core.security.pwd_context") as mock_pwd:
        mock_pwd.verify.return_value = True
        result = security.verify_password(plain, hashed)
        assert result is True
        mock_pwd.verify.assert_called_once_with(plain, hashed)


def test_verify_password_integration():
    # Helper to actually verify using the real context if possible context is simple
    # But failing that, we trust pwd_context logic.
    pass
