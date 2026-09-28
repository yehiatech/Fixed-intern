from fastapi import APIRouter

from app.conversation_state import all_calls

router = APIRouter(prefix="/calls", tags=["calls"])

# Anything that finished without a clean "resolved" needs a callback.
UNRESOLVED_RESOLUTIONS = {None, "not_resolved", "unclear", "no_response_ended", "no_answer", "hung_up"}


@router.get("/unresolved")
def list_unresolved_calls(org_id: str | None = None):
    results = []
    for state in all_calls():
        if org_id and state.get("org_id") != org_id:
            continue
        if not state["ended"] or state["resolution"] not in UNRESOLVED_RESOLUTIONS:
            continue
        results.append({
            "call_id": state["call_id"],
            "customer_name": state["customer_name"],
            "customer_phone": state.get("customer_phone", ""),
            "org_id": state["org_id"],
            "resolution": state["resolution"],
            "started_at": state.get("started_at"),
            "retry_attempt": state.get("retry_attempt", 0),
            "transcript_preview": state["transcript"][-1]["text"] if state["transcript"] else None,
        })
    return {"count": len(results), "unresolved_calls": results}
