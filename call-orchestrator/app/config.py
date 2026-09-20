"""
Centralized configuration, loaded from environment variables / .env file.
Ticket T-11 only needs this to exist so later tickets (T-12, T-13) can
import settings without restructuring anything.
"""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
    )

    # =========================
    # AWS
    # =========================
    aws_access_key_id: str = ""
    aws_secret_access_key: str = ""
    aws_region: str = "us-east-1"

    # =========================
    # LiveKit
    # =========================
    livekit_url: str = ""
    livekit_api_key: str = ""
    livekit_api_secret: str = ""

    # =========================
    # Bedrock
    # =========================
    bedrock_model_id: str = (
        "anthropic.claude-3-haiku-20240307-v1:0"
    )

    # =========================
    # Amazon Polly
    # =========================
    polly_voice: str = "Zeina"

    # =========================
    # Public URL
    # =========================
    # Used when an external service needs to reach
    # the local FastAPI application during development.
    public_base_url: str = ""

    # =========================
    # Agent Transfer
    # =========================
    # Phone number used when transfer_to_agent is triggered.
    transfer_agent_number: str = ""

    # =========================
    # Database
    # =========================
    database_url: str = (
        "postgresql://admin:supersecretpassword@db:5432/ai_callcenter"
    )

    # =========================
    # Service
    # =========================
    service_name: str = "call-orchestrator"
    port: int = 8001


@lru_cache
def get_settings() -> Settings:
    """Return a cached application settings instance."""
    return Settings()

