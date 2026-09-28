"""
Simple admin view: which customers' problems got marked resolved vs
not, so someone can follow up with the "not_resolved" / "unclear" ones.
"""
from fastapi import APIRouter

from app.call_results import get_all_results, get_results_for_phone

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/results")
def list_results() -> list[dict]:
    """All call outcomes, most recent first."""
    return get_all_results()


@router.get("/results/needs-followup")
def needs_followup() -> list[dict]:
    """Just the customers whose latest call was NOT resolved — the
    admin's actual to-do list. Registered BEFORE the {customer_phone}
    route below — otherwise FastAPI would match "needs-followup" as a
    phone number and this would never be reached."""
    all_results = get_all_results()
    latest_per_phone: dict[str, dict] = {}
    for r in all_results:  # already newest-first, so first hit per phone wins
        latest_per_phone.setdefault(r["customer_phone"], r)
    return [r for r in latest_per_phone.values() if r["decision"] != "resolved"]


@router.get("/results/{customer_phone}")
def list_results_for_phone(customer_phone: str) -> list[dict]:
    """Outcomes for one specific customer number."""
    return get_results_for_phone(customer_phone)
