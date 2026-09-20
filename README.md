# AI Voice Agent + Frappe CRM Integration

An AI-powered voice agent that handles incoming and outgoing phone calls in **Malayalam and English**, conducts sales conversations, and automatically saves structured lead data to **Frappe CRM**.

## What It Does

```
📞 Caller dials your number
    ↓
🤖 AI agent answers and speaks naturally
    ↓
🗣️ Caller speaks Malayalam, English, or mixed
    ↓
🧠 AI understands and asks relevant questions
    ↓
📞 Call ends
    ↓
📊 AI extracts: name, intent, budget, timeline
    ↓
💼 Frappe CRM receives the lead automatically
    ↓
📋 Follow-up task is created
```

## Architecture

```
Caller
   │
   ▼
Exotel (Telephony)
   │  WebSocket — bidirectional audio stream
   ▼
FastAPI Server
   ├── Audio resampling (8kHz ↔ 16kHz)
   ├── Sarvam STT (Realtime WebSocket)
   ├── Sarvam-105B Conversations (Conversation AI)
   ├── Sarvam TTS (REST API)
   └── Post-call: LLM extraction → Frappe CRM
```

### Audio Pipeline

| Segment | Format | Sample Rate |
|---|---|---|
| Exotel → Server | Base64 PCM | 8 kHz |
| Server → Sarvam STT | Base64 PCM | 16 kHz (upsampled) |
| Sarvam TTS → Server | mulaw | 8 kHz |
| Server → Exotel | Base64 mulaw | 8 kHz |

## Tech Stack

| Component | Technology |
|---|---|
| **Backend** | Python 3.12 + FastAPI |
| **Telephony** | Exotel (AgentStream / Voicebot Applet) |
| **Speech-to-Text** | Sarvam AI Saaras v3 (Realtime Streaming) |
| **Text-to-Speech** | Sarvam AI Bulbul v3 |
| **Conversational AI** | Sarvam-105B Conversations |
| **CRM** | Frappe CRM (REST API) |
| **Audio Processing** | audioop-lts (resampling) |
| **Dashboard** | React 19 + Vite + Tailwind CSS |
| **Persistence** | PostgreSQL + asyncpg |

## Project Structure

```
app/
├── main.py                 # FastAPI entry point
├── config.py               # Environment configuration
├── routes.py               # API endpoints
│
├── voice/
│   ├── pipeline.py         # Core WebSocket call handler
│   ├── prompts.py          # LLM system prompts
│   └── audio.py            # Audio resampling utilities
│
├── integrations/
│   ├── sarvam.py           # Sarvam STT/TTS client
│   ├── exotel.py           # Exotel event parsing + outbound API
│   └── frappe.py           # Frappe CRM HTTP client
│
├── services/
│   ├── crm.py              # CRM orchestration (create/update lead)
│   └── extraction.py       # LLM-based transcript extraction
│
└── models/
    └── schemas.py          # Pydantic data models
```

## Prerequisites

- **Python 3.12+**
- **Exotel account** with AgentStream/Voicebot Applet enabled
- **Sarvam AI** API subscription key
- **Frappe CRM** instance with API access
- **ngrok** (for local development)

## Setup

### 1. Clone and Install

```bash
git clone <repo-url>
cd voice-agent-frappe-crm

python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # macOS/Linux

pip install -r requirements.txt
```

### 2. Configure Environment

```bash
copy .env.example .env
# Edit .env with your API credentials
```

### 3. Set Up Frappe CRM Custom Fields

```bash
python -m scripts.setup_frappe
```

This creates custom fields on the CRM Lead DocType:
- Language, Intent, Requirement, Budget, Timeline
- Lead Category (Hot/Warm/Cold/Not Interested)
- AI Summary

### 4. Configure Exotel

1. Go to your Exotel Dashboard → App Bazaar
2. Create or edit a flow using the **Voicebot Applet**
3. Set the WebSocket URL to your server:
   - Local: `wss://your-ngrok-url.ngrok.io/voice`
   - Deployed: `wss://your-domain.com/voice`
4. Assign this flow to your ExoPhone number

### 5. Start the Server

```bash
# Start ngrok (in a separate terminal)
ngrok http 8000

# Update .env with ngrok URL
# SERVER_URL=https://xxxx.ngrok.io

# Start the server
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 6. Start the Dashboard

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`. Vite proxies API and health requests to the backend on port 8000.

If `API_AUTH_TOKEN` is configured, select the key icon in the dashboard and enter the same token. The token is stored only in the current browser tab.

## API Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/` | Project info and available endpoints |
| `GET` | `/health` | Health check with service status |
| `WS` | `/voice` | Exotel WebSocket for live calls |
| `POST` | `/calls/outbound` | Trigger an outbound call |
| `POST` | `/test/extract` | Test extraction without a phone call |

Dashboard, outbound-call, and extraction endpoints require `Authorization: Bearer <token>` when `API_AUTH_TOKEN` is set. Keep the token empty only during isolated local development.

### Test Extraction (No Phone Call Needed)

```bash
curl -X POST http://localhost:8000/test/extract \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $API_AUTH_TOKEN" \
  -d '{
    "transcript": "Caller: എനിക്ക് ഒരു ecommerce website വേണം.\nAgent: Sure. How many products?\nCaller: Around 100.\nAgent: Budget?\nCaller: 50000 rupees.\nAgent: Timeline?\nCaller: One month.",
    "phone": "+919876543210"
  }'
```

### Outbound Call

```bash
curl -X POST http://localhost:8000/calls/outbound \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $API_AUTH_TOKEN" \
  -d '{"phone": "+919876543210"}'
```

## Incoming Call Flow

1. Caller dials ExoPhone number
2. Exotel routes call to FastAPI via WebSocket
3. AI greets: *"Hello! Thank you for calling. How can I help you today?"*
4. Caller speaks (Malayalam/English/mixed)
5. Sarvam STT transcribes in real-time
6. GPT-4o-mini generates contextual response
7. Sarvam TTS converts response to speech
8. Caller hears AI response
9. Steps 4-8 repeat until conversation completes
10. On call end:
    - Full transcript → LLM extraction
    - Structured data → Frappe CRM Lead (create or update)
    - Follow-up ToDo created if needed

## Outgoing Call Flow

1. `POST /calls/outbound` with phone number
2. Exotel calls the number
3. When answered, same AI pipeline handles the conversation
4. Post-call processing identical to incoming calls

## Malayalam + English Support

The agent handles:
- Pure English: *"I need an e-commerce website"*
- Pure Malayalam: *"എനിക്ക് ഒരു website വേണം"*
- Code-mixed: *"എനിക്ക് ഒരു website വേണം, but ecommerce അല്ല"*

The AI responds naturally in the same language style as the caller.

## Frappe CRM Data

### Lead Fields

| Field | Description |
|---|---|
| Lead Name | Caller's name (if provided) |
| Phone | Caller's phone number |
| Language | Detected language |
| Intent / Service | Service category |
| Requirement | Detailed requirement |
| Budget | Approximate budget (₹) |
| Timeline | Expected timeline |
| Lead Category | Hot / Warm / Cold / Not Interested |
| AI Summary | AI-generated conversation summary |

### Lead Classification

| Category | Criteria |
|---|---|
| **Hot** | Clear requirement + budget + timeline |
| **Warm** | Interested but missing some info |
| **Cold** | General enquiry |
| **Not Interested** | Explicitly declined |

## Docker

```bash
docker compose up --build
```

- Dashboard: `http://localhost:3000`
- Voice-agent API: `http://localhost:8000`
- Frappe CRM: `http://localhost:8080`
- PostgreSQL: `localhost:5434`

The Compose credentials are development defaults. Replace all database and Frappe administrator passwords before using the stack on a shared network.

## Verification

```bash
# Backend unit tests
python -m unittest discover -s tests -v

# Frontend checks
cd frontend
npm run lint
npm run build

# Validate container configuration
docker compose config --quiet
```

## Demo Flow (5-8 minutes)

1. **Show architecture** — explain the pipeline
2. **Show Frappe CRM** — empty leads list
3. **Make a real call** — speak Malayalam/English
4. **Show logs** — real-time processing visible
5. **Check Frappe CRM** — new lead with all fields
6. **Show follow-up ToDo** — automatically created
7. **Outbound call** (bonus) — trigger via API
8. **Show code structure** — clean, organized

## Known Limitations

- **Latency**: ~1-2 second delay between speech and response (STT + LLM + TTS)
- **Language detection**: Uses Unicode heuristic; may occasionally misdetect
- **Frappe custom fields**: Requires one-time setup via script
- **Exotel dependency**: AgentStream must be enabled on your account
- **Voice WebSocket trust**: Restrict `/voice` at the network edge to Exotel source traffic; secrets should not be placed in WebSocket query strings
- **Post-call processing**: Runs before the WebSocket handler exits; a durable job queue is recommended for high-volume production use

## Error Handling

- **Sarvam failure**: Logs error, sends fallback "Could you repeat that?" response
- **Frappe failure**: Never crashes the call; data preserved in logs for retry
- **Caller hangs up**: Processes whatever transcript exists
- **LLM timeout**: Returns predefined fallback response
