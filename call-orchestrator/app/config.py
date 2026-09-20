"""
Centralized configuration, loaded from environment variables / .env file.
Ticket T-11 only needs this to exist so later tickets (T-12, T-13) can
import settings without restructuring anything.
"""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # AWS / Bedrock (used starting T-12, not yet in this skeleton)
    aws_access_key_id: str = ""
    aws_secret_access_key: str = ""
    aws_region: str = "us-east-1"

    # Twilio (used starting T-12)
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_phone_number: str = ""

    # Database
    database_url: str = "postgresql://admin:supersecretpassword@db:5432/ai_callcenter"

    # Service
    service_name: str = "call-orchestrator"
    port: int = 8001


@lru_cache
def get_settings() -> Settings:
    """Cached settings instance — import this, not Settings() directly."""
    return Settings()


