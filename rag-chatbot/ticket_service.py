"""
Single place that reads/writes support tickets, agents and org admins.
Used by BOTH the chatbot (create_ticket tool) and the dashboard API (admin_api.py),
so a ticket always lands in the same `support_tickets` table.
"""
import hashlib
import json
import uuid

from db import get_connection

VALID_STATUSES = ("open", "in_progress", "resolved", "closed")
ACTIVE_STATUSES = ("open", "in_progress")


class TicketError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def _uuid_or_none(value):
    if value is None or value == "":
        return None
    try:
        return str(uuid.UUID(str(value)))
    except (ValueError, AttributeError, TypeError):
        raise TicketError(f"Invalid id: {value}", 400)


def _require_org(cur, organization_id: str) -> str:
    org_id = _uuid_or_none(organization_id)
    if org_id is None:
        raise TicketError("organization_id is required", 400)
    cur.execute("SELECT 1 FROM organizations WHERE id = %s", (org_id,))
    if cur.fetchone() is None:
        raise TicketError("Organization not found", 404)
    return org_id


def _require_agent_in_org(cur, agent_id: str, org_id: str) -> str:
    agent_id = _uuid_or_none(agent_id)
    cur.execute(
        "SELECT 1 FROM users WHERE id = %s AND organization_id = %s AND role = 'agent'",
        (agent_id, org_id),
    )
    if cur.fetchone() is None:
        raise TicketError("Agent not found in this organization", 404)
    return agent_id


def _hash_pw(password: str) -> str:
    # Same algorithm as init_db.hash_pw and POST /users, so login keeps working.
    return hashlib.sha256(password.encode()).hexdigest()


# ------------------------------------------------------------------ tickets
_TICKET_SELECT = """
    SELECT t.id, t.organization_id, t.customer_name, t.phone_number,
           t.issue_description, t.status, t.agent_id, t.ai_transcript,
           t.source, t.created_at, u.username, u.full_name
    FROM support_tickets t
    LEFT JOIN users u ON u.id = t.agent_id
"""


def _row_to_ticket(row) -> dict:
    return {
        "id": row[0],
        "organization_id": str(row[1]),
        "customer_name": row[2],
        "phone_number": row[3],
        "issue_description": row[4],
        "status": row[5],
        "agent_id": str(row[6]) if row[6] else None,
        "ai_transcript": row[7] or [],
        "source": row[8] or "manual",
        "created_at": row[9].isoformat() if row[9] else None,
        "agent_username": row[10],
        "agent_name": row[11] or row[10],
    }


def create_ticket_record(organization_id, customer_name, phone_number,
                         issue_description, agent_id=None, ai_transcript=None,
                         source="manual") -> dict:
    customer_name = (customer_name or "").strip()
    issue_description = (issue_description or "").strip()
    if not customer_name:
        raise TicketError("customer_name is required", 400)
    if not issue_description:
        raise TicketError("issue_description is required", 400)

    conn = get_connection()
    try:
        with conn:
            with conn.cursor() as cur:
                org_id = _require_org(cur, organization_id)
                if agent_id:
                    agent_id = _require_agent_in_org(cur, agent_id, org_id)
                else:
                    agent_id = None
                cur.execute(
                    """
                    INSERT INTO support_tickets
                        (id, organization_id, customer_name, phone_number,
                         issue_description, status, agent_id, ai_transcript, source)
                    VALUES ('TCK-' || nextval('ticket_number_seq'),
                            %s, %s, %s, %s, 'open', %s, %s, %s)
                    RETURNING id
                    """,
                    (org_id, customer_name, (phone_number or "").strip() or None,
                     issue_description, agent_id,
                     json.dumps(ai_transcript, ensure_ascii=False) if ai_transcript is not None else None,
                     source),
                )
                ticket_id = cur.fetchone()[0]
        return {"id": ticket_id, "status": "open", "agent_id": agent_id, "source": source}
    finally:
        conn.close()


def list_tickets(organization_id: str, agent_id: str | None = None) -> list[dict]:
    conn = get_connection()
    try:
        with conn:
            with conn.cursor() as cur:
                org_id = _require_org(cur, organization_id)
                sql = _TICKET_SELECT + " WHERE t.organization_id = %s"
                params = [org_id]
                if agent_id:
                    sql += " AND t.agent_id = %s"
                    params.append(_uuid_or_none(agent_id))
                sql += " ORDER BY t.created_at DESC"
                cur.execute(sql, params)
                return [_row_to_ticket(r) for r in cur.fetchall()]
    finally:
        conn.close()


def update_ticket_status(organization_id: str, ticket_id: str, status: str) -> dict:
    if status not in VALID_STATUSES:
        raise TicketError(f"status must be one of {', '.join(VALID_STATUSES)}", 400)
    conn = get_connection()
    try:
        with conn:
            with conn.cursor() as cur:
                org_id = _require_org(cur, organization_id)
                cur.execute(
                    "UPDATE support_tickets SET status = %s, updated_at = CURRENT_TIMESTAMP "
                    "WHERE id = %s AND organization_id = %s",
                    (status, ticket_id, org_id),
                )
                if cur.rowcount == 0:
                    raise TicketError("Ticket not found", 404)
        return {"id": ticket_id, "status": status}
    finally:
        conn.close()


def assign_ticket(organization_id: str, ticket_id: str, agent_id: str | None) -> dict:
    conn = get_connection()
    try:
        with conn:
            with conn.cursor() as cur:
                org_id = _require_org(cur, organization_id)
                if agent_id:
                    agent_id = _require_agent_in_org(cur, agent_id, org_id)
                else:
                    agent_id = None
                cur.execute(
                    "UPDATE support_tickets SET agent_id = %s, updated_at = CURRENT_TIMESTAMP "
                    "WHERE id = %s AND organization_id = %s",
                    (agent_id, ticket_id, org_id),
                )
                if cur.rowcount == 0:
                    raise TicketError("Ticket not found", 404)
        return {"id": ticket_id, "agent_id": agent_id}
    finally:
        conn.close()


# ------------------------------------------------------------------- agents
def list_agents(organization_id: str) -> list[dict]:
    conn = get_connection()
    try:
        with conn:
            with conn.cursor() as cur:
                org_id = _require_org(cur, organization_id)
                cur.execute(
                    """
                    SELECT u.id, u.username, u.full_name,
                           COUNT(t.id) FILTER (WHERE t.status IN ('open','in_progress')) AS active_tickets
                    FROM users u
                    LEFT JOIN support_tickets t ON t.agent_id = u.id
                    WHERE u.organization_id = %s AND u.role = 'agent'
                    GROUP BY u.id, u.username, u.full_name, u.created_at
                    ORDER BY u.created_at
                    """,
                    (org_id,),
                )
                return [
                    {"id": str(r[0]), "username": r[1], "full_name": r[2] or r[1],
                     "active_tickets": r[3]}
                    for r in cur.fetchall()
                ]
    finally:
        conn.close()


def _create_member(organization_id: str, role: str, username: str, password: str,
                   full_name: str | None) -> dict:
    username = (username or "").strip().lstrip("@")
    if not username:
        raise TicketError("username is required", 400)
    if not password:
        raise TicketError("password is required", 400)
    conn = get_connection()
    try:
        with conn:
            with conn.cursor() as cur:
                org_id = _require_org(cur, organization_id)
                cur.execute("SELECT 1 FROM users WHERE username = %s", (username,))
                if cur.fetchone():
                    raise TicketError("Username already exists", 409)
                cur.execute(
                    "INSERT INTO users (username, password_hash, role, organization_id, full_name) "
                    "VALUES (%s, %s, %s, %s, %s) RETURNING id",
                    (username, _hash_pw(password), role, org_id,
                     (full_name or "").strip() or None),
                )
                user_id = cur.fetchone()[0]
        return {"id": str(user_id), "username": username, "role": role,
                "full_name": (full_name or "").strip() or username}
    finally:
        conn.close()


def create_agent(organization_id, username, password, full_name=None) -> dict:
    return _create_member(organization_id, "agent", username, password, full_name)


def create_org_admin(organization_id, username, password) -> dict:
    return _create_member(organization_id, "org_admin", username, password, None)


def delete_member(organization_id: str, user_id: str) -> dict:
    """Delete an agent / org_admin, only inside the given organization."""
    conn = get_connection()
    try:
        with conn:
            with conn.cursor() as cur:
                org_id = _require_org(cur, organization_id)
                cur.execute(
                    "DELETE FROM users WHERE id = %s AND organization_id = %s "
                    "AND role IN ('agent','org_admin')",
                    (_uuid_or_none(user_id), org_id),
                )
                if cur.rowcount == 0:
                    raise TicketError("User not found in this organization", 404)
        return {"status": "success"}
    finally:
        conn.close()


def list_org_admins(organization_id: str) -> list[dict]:
    conn = get_connection()
    try:
        with conn:
            with conn.cursor() as cur:
                org_id = _require_org(cur, organization_id)
                cur.execute(
                    "SELECT id, username FROM users WHERE organization_id = %s "
                    "AND role = 'org_admin' ORDER BY created_at",
                    (org_id,),
                )
                return [{"id": str(r[0]), "username": r[1]} for r in cur.fetchall()]
    finally:
        conn.close()

