"""
User Service Client.
Provides a typed interface to the User Service Microservice.
Decouples the Monolith from the Identity Provider.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Final

import httpx
import jwt

from app.core.http_client_factory import HTTPClientConfig, get_http_client
from app.core.settings.base import get_settings

logger = logging.getLogger("user-service-client")

DEFAULT_USER_SERVICE_URL: Final[str] = "http://user-service:8003"


class UserServiceClient:
    """
    Client for interacting with the User Service.
    """

    def __init__(self, base_url: str | None = None) -> None:
        settings = get_settings()
        # Ensure we use the configuration from settings if available
        env_url = getattr(settings, "USER_SERVICE_URL", None)
        resolved_url = base_url or env_url or DEFAULT_USER_SERVICE_URL
        self.base_url = resolved_url.rstrip("/")
        self.config = HTTPClientConfig(
            name="user-service-client",
            timeout=1.0,  # Fail fast for auth
            max_connections=50,
        )
        self.secret_key = settings.SECRET_KEY

    async def _get_client(self) -> httpx.AsyncClient:
        return get_http_client(self.config)

    def _generate_service_token(self) -> str:
        """Generate a short-lived service token for internal communication."""
        payload = {
            "sub": "service-account",
            "role": "ADMIN",  # Service account has admin privileges
            "type": "service",
            "exp": datetime.now(datetime.UTC) + timedelta(minutes=5),
        }
        return jwt.encode(payload, self.secret_key, algorithm="HS256")

    async def register_user(self, full_name: str, email: str, password: str) -> dict[str, Any]:
        """
        Register a new user via the User Service.
        """
        url = f"{self.base_url}/auth/register"
        payload = {
            "full_name": full_name,
            "email": email,
            "password": password,
        }

        client = await self._get_client()
        try:
            logger.info(f"Dispatching registration to User Service: {email}")
            response = await client.post(url, json=payload)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            # Re-raise status errors (400, 401, etc.)
            logger.warning(f"User Service returned error for registration: {e.response.text}")
            raise
        except Exception as e:
            logger.error(f"Failed to register user via service: {e}", exc_info=True)
            raise

    async def login_user(
        self, email: str, password: str, user_agent: str | None = None, ip: str | None = None
    ) -> dict[str, Any]:
        """
        Authenticate user via the User Service.
        """
        url = f"{self.base_url}/auth/login"
        payload = {
            "email": email,
            "password": password,
        }
        headers = {}
        if user_agent:
            headers["User-Agent"] = user_agent

        client = await self._get_client()
        try:
            response = await client.post(url, json=payload, headers=headers)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            logger.warning(f"User Service returned error for login: {e.response.status_code}")
            raise
        except Exception as e:
            logger.error(f"Failed to login user via service: {e}", exc_info=True)
            raise

    async def get_me(self, token: str) -> dict[str, Any]:
        """
        Get current user details using the token.
        """
        url = f"{self.base_url}/user/me"
        headers = {"Authorization": f"Bearer {token}"}

        client = await self._get_client()
        try:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            logger.warning(f"User Service returned error for get_me: {e.response.status_code}")
            raise
        except Exception as e:
            logger.error(f"Failed to get user via service: {e}", exc_info=True)
            raise

    async def verify_token(self, token: str) -> bool:
        """
        Verify if a token is valid.
        """
        url = f"{self.base_url}/token/verify"
        payload = {"token": token}

        client = await self._get_client()
        try:
            response = await client.post(url, json=payload)
            response.raise_for_status()
            data = response.json()
            return data.get("data", {}).get("valid", False)
        except Exception as e:
            logger.error(f"Failed to verify token via service: {e}")
            return False

    async def get_users(self) -> list[dict[str, Any]]:
        """
        Get list of users (Admin only).
        """
        url = f"{self.base_url}/admin/users"
        token = self._generate_service_token()
        headers = {"Authorization": f"Bearer {token}"}

        client = await self._get_client()
        try:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Failed to get users: {e}")
            raise

    async def get_user_count(self) -> int:
        """
        Get total user count (Admin only).
        """
        try:
            users = await self.get_users()
            return len(users)
        except Exception as e:
            logger.error(f"Failed to get user count: {e}")
            raise


# Singleton
user_service_client = UserServiceClient()
user_client = user_service_client  # Alias for backward compatibility
