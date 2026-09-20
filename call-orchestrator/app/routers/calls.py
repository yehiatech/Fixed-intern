"""
T-07b: mock implementation of the API contract with Person 1's bridge
scripts (GitHub Issue #17). Returns hardcoded but contract-accurate JSON
so Person 1 can build call_trigger.py and call_result_sync.py against
this without waiting for the real Bedrock/Twilio pipeline (T-12, T-13).

Real logic (actual Twilio call, actual Bedrock conversation, actual
call_logs rows) replaces this in T-12/T-13 — the request/response shapes
defined here must not change without updating Issue #17 first.
"""
import logging
import uuid

from fastapi import APIRouter

from app.errors import APIError
from app.schemas import (
    CallResultCompleted,
    CallTriggerRequest,
    CallTriggerResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/calls", tags=["calls"])

# In-memory mock store: call_id -> True once /trigger has been called.
# Replaced by real call_logs reads/writes in T-13.
_triggered_calls: dict[str, bool] = {}


@router.post("/trigger", response_model=CallTriggerResponse, status_code=202)
def trigger_call(payload: CallTriggerRequest) -> CallTriggerResponse:
    if not payload.customer_phone.startswith("+"):
        raise APIError(
            status_code=400,
            error="invalid_phone_number",
            message="The phone number format is invalid. Must start with +",
            call_id=payload.call_id,
        )

    if _triggered_calls.get(payload.call_id):
        raise APIError(
            status_code=409,
            error="call_already_active",
            message="A call for this customer is already in progress",
            call_id=payload.call_id,
        )

    _triggered_calls[payload.call_id] = True

    logger.info(
        "Mock trigger_call accepted for call_id=%s org_id=%s retry_attempt=%s",
        payload.call_id,
        payload.org_id,
        payload.retry_attempt,
    )

    return CallTriggerResponse(
        status="accepted",
        call_id=payload.call_id,
        twilio_sid=f"CA{uuid.uuid4().hex}",
        message="Call initiated",
    )


@router.get("/result/{call_id}", response_model=CallResultCompleted)
def get_call_result(call_id: str) -> CallResultCompleted:
    if call_id not in _triggered_calls:
        raise APIError(
            status_code=404,
            error="call_not_found",
            message="No call was found for this call_id",
            call_id=call_id,
        )

    logger.info("Mock get_call_result returning completed dummy result for call_id=%s", call_id)

    return CallResultCompleted(
        call_id=call_id,
        status="completed",
        duration_seconds=145,
        transcript=(
            "مرحبا، أنا المساعد الذكي. كيف يمكنني مساعدتك اليوم؟\n"
            "العميل: عايز أعرف رصيدي\n"
            "المساعد: رصيدك الحالي هو 250 جنيه..."
        ),
        summary="Customer inquired about account balance. Agent provided current balance of 250 EGP.",
        sentiment="positive",
        tools_used=["lookup_customer", "check_balance"],
        resolution="resolved_first_call",
    )
