"""
Dashboard API: tickets, agents and org admins, all stored in PostgreSQL.
Mounted from main.py with app.include_router(router). Existing endpoints are untouched.
"""
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

import ticket_service as svc

router = APIRouter(prefix="/api/organizations/{org_id}", tags=["dashboard"])


def _run(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except svc.TicketError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    except Exception as e:  # DB down, etc.
        raise HTTPException(status_code=500, detail=str(e))


class TicketCreate(BaseModel):
    customer_name: str
    phone_number: Optional[str] = None
    issue_description: str
    agent_id: Optional[str] = None


class StatusBody(BaseModel):
    status: str


class AssignBody(BaseModel):
    agent_id: Optional[str] = None  # null = unassign


class AgentCreate(BaseModel):
    username: str
    password: str
    full_name: Optional[str] = None


class AdminCreate(BaseModel):
    username: str
    password: str


# ---- tickets
@router.get("/tickets")
def get_tickets(org_id: str, agent_id: Optional[str] = None):
    return {"tickets": _run(svc.list_tickets, org_id, agent_id)}


@router.post("/tickets")
def post_ticket(org_id: str, body: TicketCreate):
    return _run(svc.create_ticket_record, org_id, body.customer_name, body.phone_number,
                body.issue_description, body.agent_id, None, "manual")


@router.put("/tickets/{ticket_id}/status")
def put_ticket_status(org_id: str, ticket_id: str, body: StatusBody):
    return _run(svc.update_ticket_status, org_id, ticket_id, body.status)


@router.put("/tickets/{ticket_id}/assign")
def put_ticket_assign(org_id: str, ticket_id: str, body: AssignBody):
    return _run(svc.assign_ticket, org_id, ticket_id, body.agent_id)


# ---- agents
@router.get("/agents")
def get_agents(org_id: str):
    return {"agents": _run(svc.list_agents, org_id)}


@router.post("/agents")
def post_agent(org_id: str, body: AgentCreate):
    return _run(svc.create_agent, org_id, body.username, body.password, body.full_name)


# ---- org admins (used by the Manage modal in organizations.html)
@router.get("/admins")
def get_admins(org_id: str):
    return {"admins": _run(svc.list_org_admins, org_id)}


@router.post("/admins")
def post_admin(org_id: str, body: AdminCreate):
    return _run(svc.create_org_admin, org_id, body.username, body.password)


# ---- remove an agent / admin (scoped to this org)
@router.delete("/members/{user_id}")
def delete_member(org_id: str, user_id: str):
    return _run(svc.delete_member, org_id, user_id)

