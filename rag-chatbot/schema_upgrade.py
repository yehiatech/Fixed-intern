"""
Additive schema upgrade, run once at API startup.

- If the base tables (users / organizations / support_tickets) do not exist yet,
  it runs the existing init_db() (unchanged) to create + seed them.
- Then it applies ONLY additive, idempotent changes (ADD COLUMN IF NOT EXISTS,
  CREATE ... IF NOT EXISTS). It never drops, renames or rewrites existing data.
"""
import hashlib

from db import get_connection

# Only the super admin is seeded (password 123, same as the original init_db.py - change it).
# Organizations, their admins and their agents are created from the dashboards.
DEFAULT_PASSWORD = "123"

ADDITIVE_SQL = [
    # Agents have a display name in the UI (agents.html "Full Name").
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS full_name VARCHAR(255);",
    # Where the ticket came from: 'chatbot' (AI escalation) or 'manual' (dashboard).
    "ALTER TABLE support_tickets ADD COLUMN IF NOT EXISTS source VARCHAR(20) DEFAULT 'manual';",
    "ALTER TABLE support_tickets ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;",
    # Collision-free ticket numbers (TCK-1001, TCK-1002, ...).
    "CREATE SEQUENCE IF NOT EXISTS ticket_number_seq START 1001;",
    "CREATE INDEX IF NOT EXISTS idx_support_tickets_org ON support_tickets(organization_id);",
    "CREATE INDEX IF NOT EXISTS idx_support_tickets_agent ON support_tickets(agent_id);",
    # Chatbot personas: built-in presets (is_preset, organization_id NULL) + at most one custom per org.
    """CREATE TABLE IF NOT EXISTS personas (
        id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        organization_id UUID REFERENCES organizations(id) ON DELETE CASCADE,
        preset_key VARCHAR(50),
        name VARCHAR(100) NOT NULL,
        description TEXT,
        prompt_text TEXT NOT NULL,
        is_preset BOOLEAN NOT NULL DEFAULT FALSE,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );""",
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_personas_preset_key ON personas(preset_key) WHERE is_preset;",
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_personas_org_custom ON personas(organization_id) WHERE NOT is_preset;",
    # NULL = the default persona (the tone the bot always had).
    "ALTER TABLE organizations ADD COLUMN IF NOT EXISTS persona_id UUID REFERENCES personas(id) ON DELETE SET NULL;",
]


def _base_tables_exist() -> bool:
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT to_regclass('public.users'), to_regclass('public.organizations'), "
                "to_regclass('public.support_tickets')"
            )
            return all(v is not None for v in cur.fetchone())
    finally:
        conn.close()


def ensure_schema() -> None:
    if not _base_tables_exist():
        from init_db import init_db
        init_db()

    conn = get_connection()
    try:
        with conn:
            with conn.cursor() as cur:
                for stmt in ADDITIVE_SQL:
                    cur.execute(stmt)
    finally:
        conn.close()

    seed_defaults()

    from personas import seed_presets
    seed_presets()


def seed_defaults() -> None:
    """Create the super admin if it is missing. Never overwrites an existing row."""
    pw = hashlib.sha256(DEFAULT_PASSWORD.encode()).hexdigest()
    conn = get_connection()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO users (username, password_hash, role, full_name) "
                    "VALUES ('superadmin', %s, 'super_admin', 'Super Admin') "
                    "ON CONFLICT (username) DO NOTHING", (pw,))
    finally:
        conn.close()
