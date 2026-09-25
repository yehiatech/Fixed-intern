# T-07b — API Contract Agreement

**Status:** Ready for Person 2 to review and implement a mock  
**Participants:** Person 1 (you) + Person 2 (Voice AI Engineer)  
**Prerequisite:** T-07 ✅ Done  
**Blocks:** T-08 (Bridge Scripts)

---

## What This Is

This document is the formal API contract between your bridge scripts (Person 1) and the Voice AI Call Orchestrator (Person 2). Person 2 must commit **mock endpoints** returning these exact JSON shapes so you can start building `call_trigger.py` and `call_result_sync.py` immediately — without waiting for the real AI pipeline.

---

## EspoCRM API Reference (for context)

- **Endpoint:** `http://107.20.124.171:8080/api/v1/CFollowUpCall`
- **Auth Header:** `X-Api-Key: a7a0307817c91ab7feea464170c310f6`
- **Entity Name:** `CFollowUpCall` (note the `C` prefix — this is permanent)

---

## Endpoint 1: Trigger a Call — `POST /calls/trigger`

*Person 1's bridge script sends this to Person 2's Voice API (port 8001) when a new FollowUpCall is pending in EspoCRM.*

### Request Body

```json
{
  "call_id": "67a1b2c3d4e5f6",
  "customer_phone": "+201012345678",
  "customer_name": "يحيى",
  "org_id": "fixed",
  "retry_attempt": 0,
  "assigned_agent": "agent1",
  "language": "ar-EG"
}
```

| Field | Type | Required | Notes |
|---|---|---|---|
| `call_id` | string | ✅ | The EspoCRM `CFollowUpCall` record ID |
| `customer_phone` | string | ✅ | E.164 format, always starts with `+` |
| `customer_name` | string | ✅ | Arabic name for personalized greeting |
| `org_id` | string | ✅ | The organization/team ID (for multi-tenant isolation) |
| `retry_attempt` | integer | ✅ | 0 = first attempt, max = 2 (3 attempts total) |
| `assigned_agent` | string | ✅ | EspoCRM username of the agent who owns this ticket |
| `language` | string | ✅ | Always `ar-EG` (Egyptian Arabic) |

### Expected Response (HTTP `202 Accepted`)

```json
{
  "status": "accepted",
  "call_id": "67a1b2c3d4e5f6",
  "twilio_sid": "CA1234567890abcdef",
  "message": "Call initiated"
}
```

---

## Endpoint 2: Get Call Result — `GET /calls/result/{call_id}`

*Person 1's bridge script polls this endpoint to check if the call is done, then syncs the result back to EspoCRM.*

### Response — Call Completed (HTTP `200 OK`)

```json
{
  "call_id": "67a1b2c3d4e5f6",
  "status": "completed",
  "duration_seconds": 145,
  "transcript": "مرحبا يحيى، أنا المساعد الذكي من شركة فيكسد. كيف يمكنني مساعدتك اليوم؟\nيحيى: عايز أعرف رصيدي\nالمساعد: رصيدك الحالي هو 250 جنيه...",
  "summary": "Customer inquired about account balance. Agent provided current balance of 250 EGP. Customer confirmed satisfaction.",
  "sentiment": "positive",
  "tools_used": ["lookup_customer", "check_balance"],
  "resolution": "resolved_first_call"
}
```

### Response — Call Unanswered (HTTP `200 OK`)

```json
{
  "call_id": "67a1b2c3d4e5f6",
  "status": "unanswered",
  "duration_seconds": 0,
  "transcript": null,
  "summary": null,
  "sentiment": null,
  "tools_used": [],
  "resolution": "no_answer"
}
```

### Response — Call Still In Progress (HTTP `200 OK`)

```json
{
  "call_id": "67a1b2c3d4e5f6",
  "status": "in_progress",
  "message": "Call is still active"
}
```

---

## Field Mapping: Voice API → EspoCRM

*How Person 1's bridge script syncs call results back to `CFollowUpCall` records:*

| Voice API Field | EspoCRM CFollowUpCall Field | Sync Logic |
|---|---|---|
| `status` | `status` | `completed` → `completed`; `unanswered` + attempts < 3 → `pending`; `unanswered` + attempts ≥ 3 → `failed_max_retries` |
| `transcript` | `transcript` | Full Arabic conversation text |
| `summary` | `summary` | AI-generated call summary |
| `sentiment` | `sentiment` | Must be one of: `positive`, `neutral`, `frustrated`, `angry` |
| `retry_attempt` | `callAttempts` | Incremented by bridge script on unanswered |
| — | `nextRetryAt` | Set by bridge script to `now + 15 min` on unanswered |

---

## Error Responses

All errors follow this standard format:

```json
{
  "error": "invalid_phone_number",
  "message": "The phone number format is invalid. Must start with +",
  "call_id": "67a1b2c3d4e5f6"
}
```

| HTTP Code | Error Key | When |
|---|---|---|
| `400` | `invalid_phone_number` | Phone number format is wrong |
| `404` | `call_not_found` | `call_id` doesn't exist |
| `409` | `call_already_active` | A call for this customer is already in progress |
| `500` | `twilio_error` | Twilio API failed |
| `500` | `bedrock_timeout` | Bedrock didn't respond within 10s |

---

## Action Items

### Person 2 (Voice AI Engineer) — DO THIS NOW:

1. **Review this contract** and comment on GitHub Issue #17 with any changes.
2. **Commit a mock implementation** of both endpoints in the `call-orchestrator/` service:
   - `POST /calls/trigger` → return the `202 Accepted` dummy JSON
   - `GET /calls/result/{call_id}` → return the `200 OK` completed dummy JSON
3. Push to branch `feat/call-orchestrator-skeleton` and open a PR.

### Person 1 (You) — AFTER Person 2 commits the mock:

1. Close GitHub Issue #17 (T-07b).
2. Start T-08: build `call_trigger.py` and `call_result_sync.py` against the mock endpoints.

---

## Git Branch Rules Reminder

> ⚠️ **NEVER push directly to `dev` or `main`!**  
> All work goes on feature branches → PR into `dev`.
