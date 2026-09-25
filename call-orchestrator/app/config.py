"""
Centralized configuration, loaded from environment variables / .env file.

Reverted from LiveKit back to a direct webhook-based pipeline, now on
Vonage instead of Twilio. Back to the T-12-era architecture: this
FastAPI service runs the Bedrock converse() tool-calling loop directly
(app/bedrock_client.py), no separate worker process.
"""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
    )

    # AWS / Bedrock + Polly
    aws_access_key_id: str = ""
    aws_secret_access_key: str = ""
    aws_region: str = "us-east-1"
    bedrock_model_id: str = "us.anthropic.claude-haiku-4-5-20251001-v1:0"
    polly_voice_language: str = "arb"  # Amazon Polly's Arabic (Zeina) language code, used via Vonage's talk action

    # Vonage Voice API
    # Voice API auth is Application ID + private key (JWT), NOT api_key/api_secret.
    # vonage_private_key_path should point to the .pem file Vonage gives you when
    # you create the Application — NEVER commit that file or paste its contents here.
    vonage_application_id: str = ""
    vonage_private_key_path: str = ""  # e.g. /app/vonage_private.pem — mount it, don't commit it
    vonage_number: str = ""  # your Vonage virtual number, E.164, no "+" (e.g. 447700900000)
    public_base_url: str = ""  # your ngrok URL — Vonage calls answer_url/event_url here
    transfer_agent_number: str = ""  # phone number to <connect> to when transfer_to_agent fires

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
