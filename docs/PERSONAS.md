# Customizable chatbot personas

An org admin picks how the assistant talks (Org Admin page -> **Bot Persona**).
Presets: Friendly & Professional (the original tone, default), Formal, Concise,
Enthusiastic - or a Custom description (max 600 characters, one per organization).

## What a persona can and cannot change
System prompt = header + **persona text** + guard + **fixed rules** (`personas.py`).
The fixed rules (search the knowledge base first, never invent facts, always say
you are an AI, collect name + phone + description before opening a ticket) come
AFTER the persona and cannot be switched off by it.

## Data
- `personas` table: built-in presets (`is_preset`, refreshed at startup from `personas.py`)
  + at most one custom persona per organization.
- `organizations.persona_id`: NULL = default persona.
- Additive changes only, created by `schema_upgrade.py` at startup.

## API (`admin_api.py`)
- `GET  /api/organizations/{org_id}/personas`  -> presets, the org's custom persona, selected id
- `PUT  /api/organizations/{org_id}/persona`   -> `{persona_id}` | `{custom_text, custom_name}` | `{}` to reset

## Behavior notes
- Orgs that never pick a persona behave exactly as before (no extra cost or latency).
- Direct knowledge-base answers used to skip the model. For orgs with a non-default
  persona, that passage is now re-worded by one extra Bedrock call (facts only from the
  passage; on any error the raw passage is returned). Default orgs are unchanged.
- If reading personas from the DB fails, chat falls back to the default persona.

## Chat user can pick the persona
The person chatting (chat widget and the dashboard chatbot) can pick the style from a
dropdown in the chat header. Empty choice = the organization's persona (previous behaviour).
- `GET  /chat/personas?organization_id=...` -> presets + this org's custom persona (id/name/description only)
- `POST /chat` accepts an optional `persona_id`. It is only honored if it is a preset or THIS
  organization's custom persona; anything else falls back to the organization's persona.
- The fixed rules (`CORE_RULES`) are still appended after whichever persona is used.
- The choice is remembered in the browser (`localStorage`, key `chat_persona_<org id>`).
