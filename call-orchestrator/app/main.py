"""
Call Orchestrator microservice — Person 2 (Voice AI Engineer).

T-11 (this file): empty skeleton, structural only.
T-12: adds the full voice pipeline with Bedrock tool calling.
T-13: adds the outbound call script + retry logic.
"""
import logging

from fastapi import FastAPI

from app.config import get_settings
from app.routers import calls, health

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)

settings = get_settings()

app = FastAPI(
    title="Call Orchestrator",
    description="Outbound Arabic call orchestration service (Voice AI Engineer).",
    version="0.1.0",
)

app.include_router(health.router)
app.include_router(calls.router)


@app.on_event("startup")
def on_startup() -> None:
    logger.info("%s starting on port %s", settings.service_name, settings.port)
