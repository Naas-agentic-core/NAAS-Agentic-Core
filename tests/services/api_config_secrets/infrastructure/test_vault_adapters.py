import os
from unittest.mock import patch

import pytest

from app.services.api_config_secrets.infrastructure.vault_adapters import (
    AWSSecretsManagerBackend,
    HashiCorpVaultBackend,
    LocalVaultBackend,
    SecretEncryption,
)
from cryptography.fernet import Fernet


def test_secret_encryption_with_key():
    Fernet.generate_key()
    # Actually SecretEncryption inits Fernet.
    # Let's verify we can init with None (auto-gen)
    enc = SecretEncryption()
    encrypted = enc.encrypt("secret")
    decrypted = enc.decrypt(encrypted)
    assert decrypted == "secret"


def test_secret_encryption_custom_key():
    from cryptography.fernet import Fernet

    key = Fernet.generate_key()
    enc = SecretEncryption(master_key=key)
    assert enc.decrypt(enc.encrypt("foo")) == "foo"


def test_secret_encryption_env_key():
    from cryptography.fernet import Fernet

    key = Fernet.generate_key()
    key.decode()  # Fernet key is bytes, but env usually str
    # Logic: master_key = base64.urlsafe_b64decode(master_key_str.encode())
    # Fernet.generate_key() returns urlsafe b64 encoded bytes already.
    # So if env has the string version of it.

    with patch.dict(os.environ, {"MASTER_ENCRYPTION_KEY": key.decode()}):
        enc = SecretEncryption()
        assert enc.decrypt(enc.encrypt("bar")) == "bar"


def test_local_vault_backend():
    vault = LocalVaultBackend()
    vault.write_secret("db_pass", "supersecret")
    assert vault.read_secret("db_pass") == "supersecret"
    assert vault.read_secret("missing") is None

    # List
    assert "db_pass" in vault.list_secrets()
    assert vault.list_secrets("db") == ["db_pass"]

    # Delete
    assert vault.delete_secret("db_pass") is True
    assert vault.read_secret("db_pass") is None
    assert vault.delete_secret("missing") is False

    # Rotate (no-op)
    assert vault.rotate_secret("any") is True


def test_hashicorp_backend_not_implemented():
    vault = HashiCorpVaultBackend("http://localhost:8200", "token")
    with pytest.raises(NotImplementedError):
        vault.read_secret("foo")
    with pytest.raises(NotImplementedError):
        vault.write_secret("foo", "bar")
    with pytest.raises(NotImplementedError):
        vault.delete_secret("foo")
    with pytest.raises(NotImplementedError):
        vault.list_secrets()
    with pytest.raises(NotImplementedError):
        vault.rotate_secret("foo")


def test_aws_backend_not_implemented():
    vault = AWSSecretsManagerBackend("us-east-1")
    with pytest.raises(NotImplementedError):
        vault.read_secret("foo")
    with pytest.raises(NotImplementedError):
        vault.write_secret("foo", "bar")
    with pytest.raises(NotImplementedError):
        vault.delete_secret("foo")
    with pytest.raises(NotImplementedError):
        vault.list_secrets()
    with pytest.raises(NotImplementedError):
        vault.rotate_secret("foo")
