from pydantic_settings import BaseSettings
import os
from typing import Optional

class AppSettings(BaseSettings):
    PROJECT_NAME: str = "Orchestrator Service"
    DATABASE_URL: str = "sqlite+aiosqlite:///:memory:"
    PLANNING_AGENT_URL: str = "http://localhost:8000"
    REDIS_URL: str = "redis://localhost:6379/0"
    ENVIRONMENT: str = "testing"
    OPENAI_API_KEY: Optional[str] = "test_key"
    OPENROUTER_API_KEY: Optional[str] = "test_key"
    AI_MODEL: str = "test-model"
    BACKEND_CORS_ORIGINS: list[str] = ["*"]

    class Config:
        env_file = ".env"

def get_settings():
    return AppSettings()

settings = AppSettings()
