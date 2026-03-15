"""تنفيذ Fernet مبسط للاختبارات المحلية دون اعتماد خارجي."""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets


class InvalidTokenError(ValueError):
    """يمثل خطأ في صحة الرمز المشفر."""


InvalidToken = InvalidTokenError


class Fernet:
    """يوفر تشفيرًا وتمييز سلامة بسيطين بواجهة متوافقة مع cryptography.fernet."""

    def __init__(self, key: bytes | str):
        if isinstance(key, str):
            key = key.encode()
        self._key = base64.urlsafe_b64decode(key)
        if len(self._key) != 32:
            raise ValueError("Fernet key must decode to 32 bytes")
        self._enc_key = self._key[:16]
        self._sig_key = self._key[16:]

    @staticmethod
    def generate_key() -> bytes:
        return base64.urlsafe_b64encode(secrets.token_bytes(32))

    def encrypt(self, data: bytes) -> bytes:
        keystream = hashlib.sha256(self._enc_key).digest()
        cipher = bytes(b ^ keystream[i % len(keystream)] for i, b in enumerate(data))
        sig = hmac.new(self._sig_key, cipher, hashlib.sha256).digest()
        return base64.urlsafe_b64encode(cipher + sig)

    def decrypt(self, token: bytes) -> bytes:
        try:
            payload = base64.urlsafe_b64decode(token)
        except Exception as exc:
            raise InvalidTokenError("Invalid token encoding") from exc
        if len(payload) < 32:
            raise InvalidTokenError("Token too short")
        cipher, sig = payload[:-32], payload[-32:]
        expected = hmac.new(self._sig_key, cipher, hashlib.sha256).digest()
        if not hmac.compare_digest(sig, expected):
            raise InvalidTokenError("Invalid token signature")
        keystream = hashlib.sha256(self._enc_key).digest()
        return bytes(b ^ keystream[i % len(keystream)] for i, b in enumerate(cipher))
