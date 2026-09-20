"""
Raise APIError anywhere in the call handling code to produce a response
that matches the T-07b contract's error format exactly:
{"error": "...", "message": "...", "call_id": "..."}
instead of FastAPI's default {"detail": "..."} shape.
"""


class APIError(Exception):
    def __init__(self, status_code: int, error: str, message: str, call_id: str | None = None):
        self.status_code = status_code
        self.error = error
        self.message = message
        self.call_id = call_id
        super().__init__(message)