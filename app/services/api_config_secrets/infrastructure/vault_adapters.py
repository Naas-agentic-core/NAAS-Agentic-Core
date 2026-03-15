import os
import threading

from app.services.api_config_secrets.domain.ports import VaultBackend
from cryptography.fernet import Fernet


class SecretEncryption:
    """
    Secret encryption utility using Fernet (symmetric encryption)
    """

    def __init__(self, master_key: bytes | None = None):
        if master_key is None:
            # Generate a key from environment or create new one
            master_key_str = os.environ.get("MASTER_ENCRYPTION_KEY")
            if master_key_str:
                # The environment variable is expected to be the base64-encoded key itself
                # Fernet(key) expects the url-safe base64-encoded 32-byte key directly.
                # If we decode it, we might be getting raw bytes that Fernet.init() doesn't want
                # if it expects the encoded version.
                # However, Fernet(key) doc says:
                # key (bytes or str) – A URL-safe base64-encoded 32-byte key.
                # So we should pass the encoded bytes or string directly.
                if isinstance(master_key_str, str):
                    master_key = master_key_str.encode()
            else:
                master_key = Fernet.generate_key()

        self.cipher = Fernet(master_key)

    def encrypt(self, plaintext: str) -> str:
        """Encrypt plaintext"""
        return self.cipher.encrypt(plaintext.encode()).decode()

    def decrypt(self, ciphertext: str) -> str:
        """Decrypt ciphertext"""
        return self.cipher.decrypt(ciphertext.encode()).decode()


class LocalVaultBackend(VaultBackend):
    """
    Local vault backend for development
    """

    def __init__(self):
        self.secrets: dict[str, str] = {}
        self.encryption = SecretEncryption()
        self.lock = threading.RLock()

    def read_secret(self, secret_id: str) -> str | None:
        with self.lock:
            encrypted = self.secrets.get(secret_id)
            if encrypted:
                return self.encryption.decrypt(encrypted)
            return None

    def write_secret(self, secret_id: str, value: str, metadata: dict | None = None) -> bool:
        with self.lock:
            encrypted = self.encryption.encrypt(value)
            self.secrets[secret_id] = encrypted
            return True

    def delete_secret(self, secret_id: str) -> bool:
        with self.lock:
            if secret_id in self.secrets:
                del self.secrets[secret_id]
                return True
            return False

    def list_secrets(self, prefix: str | None = None) -> list[str]:
        with self.lock:
            if prefix:
                return [k for k in self.secrets if k.startswith(prefix)]
            return list(self.secrets.keys())

    def rotate_secret(self, secret_id: str) -> bool:
        # For local backend, rotation just marks the secret for update
        return True


class HashiCorpVaultBackend(VaultBackend):
    """
    HashiCorp Vault backend
    """

    def __init__(self, vault_url: str, token: str):
        self.vault_url = vault_url
        self.token = token

    def read_secret(self, secret_id: str) -> str | None:
        raise NotImplementedError("HashiCorp Vault integration requires hvac library")

    def write_secret(self, secret_id: str, value: str, metadata: dict | None = None) -> bool:
        raise NotImplementedError("HashiCorp Vault integration requires hvac library")

    def delete_secret(self, secret_id: str) -> bool:
        raise NotImplementedError("HashiCorp Vault integration requires hvac library")

    def list_secrets(self, prefix: str | None = None) -> list[str]:
        raise NotImplementedError("HashiCorp Vault integration requires hvac library")

    def rotate_secret(self, secret_id: str) -> bool:
        raise NotImplementedError("HashiCorp Vault integration requires hvac library")


class AWSSecretsManagerBackend(VaultBackend):
    """
    AWS Secrets Manager backend
    """

    def __init__(self, region_name: str):
        self.region_name = region_name

    def read_secret(self, secret_id: str) -> str | None:
        raise NotImplementedError("AWS Secrets Manager integration requires boto3 library")

    def write_secret(self, secret_id: str, value: str, metadata: dict | None = None) -> bool:
        raise NotImplementedError("AWS Secrets Manager integration requires boto3 library")

    def delete_secret(self, secret_id: str) -> bool:
        raise NotImplementedError("AWS Secrets Manager integration requires boto3 library")

    def list_secrets(self, prefix: str | None = None) -> list[str]:
        raise NotImplementedError("AWS Secrets Manager integration requires boto3 library")

    def rotate_secret(self, secret_id: str) -> bool:
        raise NotImplementedError("AWS Secrets Manager integration requires boto3 library")
