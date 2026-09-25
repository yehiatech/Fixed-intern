# Database linking - what was added

Everything is stored in the same PostgreSQL DB through the `rag-chatbot` service (port 8002).

| Feature | Table | Endpoint(s) |
|---|---|---|
| Chatbot opens a ticket | `support_tickets` (`source='chatbot'`, `ai_transcript` = the chat) | chatbot tool `create_ticket` -> `ticket_service.create_ticket_record` |
| Dashboard tickets (list / create / status / assign) | `support_tickets` | `GET/POST /api/organizations/{org}/tickets`, `PUT .../tickets/{id}/status`, `PUT .../tickets/{id}/assign` |
| Agents | `users` (`role='agent'`, `organization_id`, `full_name`) | `GET/POST /api/organizations/{org}/agents`, `DELETE .../members/{user_id}` |
| Org admins | `users` (`role='org_admin'`) | `GET/POST /api/organizations/{org}/admins`, `DELETE .../members/{user_id}` |

Login (`POST /api/login`) still accepts the same body and returns the same keys, plus `user_id`, `username`, `full_name`, `organization_name`.

Schema changes are additive only (`schema_upgrade.py`, run at API start): `users.full_name`, `support_tickets.source`, `support_tickets.updated_at`, sequence `ticket_number_seq`, two indexes.

The super admin creates organizations + their admin exactly as before (unchanged). The org admin adds agents. The super admin account is created at startup if missing.

Chat widget: embed it as `index.html?org_id=<organization uuid>` so its tickets are saved under the right organization.
