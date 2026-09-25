"""app/errors.py — custom API exception + FastAPI handler.

Used across the app as:
    raise APIError(status_code=404, error="call_not_found", message="...", call_id=call_id)
"""
import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)


class APIError(Exception):
    def __init__(
        self,
        status_code: int = 500,
        error: str = "internal_error",
        message: str = "",
        call_id: str | None = None,
    ):
        self.status_code = status_code
        self.error = error
        self.message = message or error
        self.call_id = call_id
        super().__init__(self.message)


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(APIError)
    async def _api_error_handler(_: Request, exc: APIError) -> JSONResponse:
        if exc.status_code >= 500:
            logger.error("APIError %s (%s): %s", exc.status_code, exc.error, exc.message)
        body = {"error": exc.error, "message": exc.message}
        if exc.call_id:
            body["call_id"] = exc.call_id
        return JSONResponse(status_code=exc.status_code, content=body)

    @app.exception_handler(Exception)
    async def _unhandled_error_handler(_: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled error: %s", exc)
        return JSONResponse(
            status_code=500,
            content={"error": "internal_error", "message": "Unexpected server error"},
        )
