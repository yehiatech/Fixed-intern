"""
Request/response shapes for the /calls endpoints, matching the T-07b
API contract exactly (see GitHub Issue #17).
"""
from typing import Literal

from pydantic import BaseModel, Field


class CallTriggerRequest(BaseModel):
    call_id: str
    customer_phone: str
    customer_name: str
    org_id: str
    retry_attempt: int = Field(ge=0, le=2)
    assigned_agent: str
    language: str = "ar-EG"


class CallTriggerResponse(BaseModel):
    status: Literal["accepted"]
    call_id: str
    livekit_token: str
    message: str


class CallResultCompleted(BaseModel):
    call_id: str
    status: Literal["completed"]
    duration_seconds: int
    transcript: str
    summary: str
    sentiment: Literal["positive", "neutral", "frustrated", "angry"]
    tools_used: list[str]
    resolution: str


class CallResultUnanswered(BaseModel):
    call_id: str
    status: Literal["unanswered"]
    duration_seconds: int = 0
    transcript: None = None
    summary: None = None
    sentiment: None = None
    tools_used: list[str] = []
    resolution: str = "no_answer"


class CallResultInProgress(BaseModel):
    call_id: str
    status: Literal["in_progress"]
    message: str = "Call is still active"


class APIErrorBody(BaseModel):
    error: str
    message: str
    call_id: str | None = None