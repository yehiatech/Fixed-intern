"""
Call Orchestrator microservice — Person 2 (Voice AI Engineer).

T-11: skeleton, structural only.
T-07b (this update): mock /calls endpoints matching the contract in
Issue #17, so Person 1 can build the bridge scripts (T-08) against them.
T-12: adds the full voice pipeline with Bedrock tool calling.
T-13: adds the outbound call script + retry logic.
"""
import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.errors import APIError
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


@app.exception_handler(APIError)
def api_error_handler(request: Request, exc: APIError) -> JSONResponse:
    """Turns a raised APIError into the exact error shape T-07b specifies:
    {"error": "...", "message": "...", "call_id": "..."} — not FastAPI's
    default {"detail": "..."}.
    """
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": exc.error, "message": exc.message, "call_id": exc.call_id},
    )


@app.on_event("startup")
def on_startup() -> None:
    logger.info("%s starting on port %s", settings.service_name, settings.port)