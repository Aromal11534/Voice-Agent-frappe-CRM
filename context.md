# Voice Agent + Frappe CRM — Current Project Context

Last verified: 2026-09-20 (Asia/Calcutta)

This document is the current handoff for agents working on this repository. It records verified runtime behavior and known blockers. Do not treat the README or passing unit tests alone as proof of production readiness.

## Current verdict

The project is **partially functional, but not end-to-end ready**.

- Docker services are running.
- The browser simulator has completed real Sarvam-powered English and Malayalam turns.
- PostgreSQL call persistence and post-call extraction work for browser simulations.
- Frappe credentials and the seven custom CRM Lead fields are present.
- Real Exotel inbound/outbound calls are not currently usable.
- No call has completed the full Exotel -> Sarvam -> PostgreSQL -> Frappe workflow.
- The conversation loop is prompt-driven; it is not currently a LangChain/LangGraph agentic workflow.

## Verified runtime state

At the time of this audit:

- All Docker Compose services were up.
- `GET /health` returned `status: degraded`.
- Database: connected.
- Sarvam: configured and live browser roundtrip proven.
- Frappe: configured; authenticated read access proven.
- Exotel: `missing_credentials` because `EXOTEL_PHONE` is not configured.
- `SERVER_URL` is still `https://your-ngrok-url.ngrok.io`.
- `EXOTEL_BASE_URL` is `https://api.exotel.com`, which is correct for the Singapore account region.
- `API_AUTH_TOKEN` is unset.
- PostgreSQL contained 7 completed calls and 7 extractions.
- All 7 calls were browser simulations; there were 0 real telephony calls.
- All 7 extractions were pending Frappe sync; 0 were synced.
- The running Frappe CRM contained 0 CRM Leads.
- The latest Malayalam example successfully processed:
  - Caller: `എനിക്കൊരു website വേണം`
  - Agent: `ശരി. നിങ്ങളുടെ പേര് ഒന്ന് പറയാമോ?`
- No stored call contained more than one caller turn, so multi-turn handling is coded but not yet proven live.

Docker reports the backend container as healthy even while `/health` says degraded. The Docker healthcheck only requires an HTTP-success response, and `/health` returns HTTP 200 for degraded status.

## Automated verification

The following checks passed:

- Backend: 13/13 unit tests.
- Frontend: `npm run lint`.
- Frontend: `npm run build`.
- Docker: `docker compose config --quiet`.
- Dashboard root, `/health`, `/api/stats`, call list and call-detail HTTP routes.

Important limitations:

- The tests are mostly unit/mocked tests.
- There is no real-phone end-to-end Exotel test.
- There is no live Frappe write test.
- Existing Exotel tests assert the outdated camelCase `streamSid` response format.
- There are no frontend interaction, Nginx routing, authentication or full workflow tests.

## What currently works

### Sarvam browser flow

The browser simulator uses the real `/voice/browser` WebSocket and has proven this path:

1. Browser microphone/audio input.
2. Sarvam realtime STT.
3. Direct Sarvam conversational-model completion.
4. Sarvam TTS.
5. Browser audio playback.
6. Transcript persistence in PostgreSQL.
7. Post-call lead extraction and Hot/Warm/Cold categorization.

Browser simulations intentionally skip Frappe writes to avoid creating fake CRM contacts.

### Dashboard read paths

Hash navigation for Overview, Calls, Leads and Simulator is connected. Stats, recent calls, filtering and call details use live backend data.

The Leads page is not a Frappe view. It derives lead rows from the latest 50 local call/extraction records, including browser simulations.

### Frappe read connectivity

Authentication to the running Frappe instance works. These custom CRM Lead fields exist:

- `custom_ai_summary`
- `custom_budget`
- `custom_intent`
- `custom_language`
- `custom_lead_category`
- `custom_requirement`
- `custom_timeline`

## Critical Exotel blockers

### Runtime configuration

- `EXOTEL_PHONE` is missing, so outbound calls have no usable caller ID.
- `SERVER_URL` is a placeholder, so Exotel has no real public TLS/WSS endpoint.
- Compose does not provision a public tunnel or public WSS endpoint.
- Recent logs contain browser calls only and no real `/voice` Exotel sessions.

### WebSocket message contract

`app/integrations/exotel.py` builds outbound media, mark and clear messages with `streamSid`. Current Exotel AgentStream documentation requires `stream_sid`.

`tests/test_integrations.py` currently locks in the obsolete `streamSid` behavior and must be updated with current Exotel fixtures.

### Audio contract

The real-phone pipeline currently:

- Requests Sarvam TTS as 8 kHz mu-law.
- Splits audio into 320-byte chunks.
- Sends those chunks directly to Exotel.

The current Exotel Voicebot Applet contract requires raw/slin signed linear16 little-endian PCM. Documented chunks must be 3,200–100,000 bytes and a multiple of 320. The current implementation can therefore cause rejected, missing or distorted caller audio.

Relevant code:

- `app/integrations/sarvam.py` — real-call TTS codec.
- `app/voice/pipeline.py` — 320-byte chunking and playback loop.
- `app/integrations/exotel.py` — outbound WebSocket envelopes.

Official contract: <https://developer.exotel.com/docs/agentstream/stream-voicebot-applet>

### Outbound REST response handling

The application reads the outbound response as `Call.Sid`. Current Exotel documentation returns `call.sid`, so the application can report success with an empty call SID.

The outbound request also lacks status callbacks. Busy, failed, unanswered and terminal call states are not persisted.

Official guide: <https://developer.exotel.com/docs/agentstream/developer-guide>

### Barge-in and reliability

- The app waits for an inbound `clear` event, but Exotel documents `clear` as a server-to-Exotel command.
- `build_clear_message()` exists but is never used when caller speech is detected.
- Playback-completion `mark` events are ignored.
- The conversation loop blocks while sending each TTS response; caller transcripts may queue until playback finishes.
- If the Sarvam STT listener dies, it only logs and exits. There is no reconnect or failure signal to the main loop.
- TTS returning empty audio leaves the caller with silence.
- The initial wait for Exotel's start event has no timeout.

### Telephony security

- `/voice` accepts arbitrary WebSocket connections without authentication or IP filtering.
- HTTP API token enforcement is disabled because `API_AUTH_TOKEN` is empty.
- Backend port 8000 is published directly.
- Exposing the current service through a tunnel would permit spoofed voice sessions and potentially arbitrary billed outbound calls.

## Critical Frappe blockers

### Lead schema mismatch

`app/services/crm.py::_build_lead_fields()` sends standard status `Open`. The running CRM's available statuses are:

- New
- Contacted
- Nurture
- Qualified
- Unqualified
- Junk

`Open` is not valid in the running CRM.

The running `CRM Lead` DocType also requires `first_name`. The code omits it whenever extraction has no caller name. Recent browser extractions had `name=None`, so an equivalent real call would fail lead creation.

### Comment RPC mismatch

`app/integrations/frappe.py` calls `frappe.client.add_comment`, which is not exposed by the running Frappe instance. Its available comment method is `frappe.desk.form.utils.add_comment`, with additional required caller/comment identity fields.

### False sync success and missing retries

- The orchestration can mark a record Frappe-synced after lead creation/update even if the summary comment or follow-up ToDo fails.
- `add_comment()` and `create_todo()` swallow failures and return `None`; the caller ignores those results.
- The code logs `Follow-up ToDo created` unconditionally after attempting creation.
- Logs say failed data is available for retry, but no retry queue, worker, retry route or pending-sync processor exists.
- Post-call extraction and Frappe synchronization run synchronously in the WebSocket handler rather than through a durable job.

### Data model limitations

- Full transcripts remain only in PostgreSQL.
- Frappe is intended to receive custom fields and a summary comment, not a CRM Call Log or full conversation transcript.
- Updating an existing lead always writes the standard status and can overwrite previously meaningful CRM state.
- Extraction failures fall back to a default Cold lead instead of a distinct failure state, allowing bogus `Extraction failed` CRM data.
- Hot/Warm/Cold classification is model-instructed but not validated deterministically.
- `calls.detected_lang` exists but is not updated from the active session.
- `call_sid` is unique and call start insertion is not an upsert, so a reconnect using the same SID can lose persistence.

## Frontend and proxy gaps

- There is no outbound-call/dialler UI.
- `frontend/nginx.conf` proxies `/api/*`, `/health`, `/voice/browser`, `/docs` and `/openapi.json`.
- It does not proxy `/calls/outbound`, `/test/extract` or real `/voice`.
- Runtime proof: direct backend invalid outbound payload returns JSON 422, while `POST http://localhost:3000/calls/outbound` returns HTML 405.
- Call details are wrapped in `hidden xl:block`, so they are inaccessible below the `xl` breakpoint. Their close button is `xl:hidden` inside that wrapper and is therefore never usable.
- The top search field, Help Center, sidebar collapse, Google/GitHub buttons, remember-me and forgot-password controls are inert.
- `BrowserPhone` hard-codes same-origin `/health` and WebSocket URLs instead of consistently using `VITE_API_BASE_URL`.
- Calls and Leads filtering only considers the latest 50 records.

### Authentication is currently cosmetic

`frontend/src/components/AuthPage.jsx` ignores the entered email/password and stores a supplied token or dummy demo token. Since the backend API token is unset, protected HTTP endpoints currently accept everyone. Both WebSocket endpoints are unauthenticated.

## Agentic workflow assessment

Neither LangChain nor LangGraph is installed. The runtime is a direct scripted loop:

`STT final -> append chat history -> one Sarvam completion -> TTS`

Post-call processing is another fixed sequence:

`extract JSON -> find/create/update lead -> add comment -> create ToDo`

The model has no tools. There are no explicit graph states for qualification, required-field completion, CRM lookup, appointment booking, transfer/handoff, retry, recovery or call completion. The current implementation should be described as a prompt-driven conversational pipeline with post-call extraction, not an agentic workflow.

LangGraph is the recommended orchestration layer after the underlying Exotel and Frappe integrations are corrected. Sarvam can remain the STT, conversational-model and TTS backend.

## Recommended repair order

1. Update Exotel media/mark/clear envelopes to `stream_sid` and replace legacy protocol tests with current fixtures.
2. Produce Exotel-compatible linear16 PCM, use compliant chunk sizes and add codec/chunk integration tests.
3. Parse `call.sid`, reject empty call IDs, and add terminal status callbacks.
4. Configure the ExoPhone and a real public TLS/WSS URL.
5. Add HTTP and WebSocket authentication/IP controls before exposing the service publicly.
6. Fix Frappe status mapping, mandatory-name fallback and the comment RPC.
7. Mark sync complete only after all required CRM operations succeed; add durable, idempotent retries.
8. Decide how full transcripts/call logs should be represented inside Frappe CRM.
9. Add the outbound dialler UI and Nginx action/WebSocket routes.
10. Prove one real inbound and one real outbound call through Exotel -> Sarvam -> PostgreSQL -> Frappe.
11. Add LangGraph qualification/tool/handoff states only after that end-to-end foundation is stable.

## Acceptance criteria for “fully functional”

Do not mark the project ready until all of the following are demonstrated:

- A real inbound Exotel call reaches `/voice`, hears intelligible English and Malayalam responses, supports interruption and ends cleanly.
- A real outbound call can be started from the dashboard and produces a non-empty Exotel call SID.
- Terminal call status is persisted for answered, failed, busy and no-answer outcomes.
- PostgreSQL contains the complete transcript and correct detected language.
- A Frappe CRM Lead is created or safely updated using valid schema values.
- The summary/comment and required follow-up ToDo are created successfully.
- Failed Frappe writes retry safely without duplicate leads or tasks.
- The dashboard shows real telephony calls separately from simulations and displays true Frappe sync state.
- Authentication protects HTTP endpoints and both WebSocket endpoints.
- Automated tests cover the current Exotel protocol and at least one full integration path.

## Safety notes for future agents

- Never print or commit `.env` secrets.
- Do not place a real external call without explicit user approval; calls may incur charges.
- Browser simulation records must not be synced into Frappe as real leads.
- A passing `/health` HTTP status or Docker `healthy` label does not currently establish telephony readiness.
