# Pretty Good AI — Voice Bot Tester

An automated voice bot that calls the Pretty Good AI test line (**805-439-8008**), simulates realistic patient scenarios, records + transcribes both sides of each conversation, and surfaces bugs or quality issues in the agent's responses.

---

## Quick start

### 1. Prerequisites

| Tool | Purpose | Get it |
|------|---------|--------|
| **Python 3.11+** | Runtime | [python.org](https://www.python.org) |
| **ngrok** | Expose local server so Twilio can reach it | [ngrok.com](https://ngrok.com) |
| **Twilio account** | Place outbound phone calls | [twilio.com](https://www.twilio.com) — free trial works |
| **Deepgram API key** | Real-time speech-to-text & text-to-speech | [deepgram.com](https://deepgram.com) — free tier available |
| **OpenAI API key** | LLM for generating patient dialogue | [platform.openai.com](https://platform.openai.com) |

### 2. Install & configure

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env and fill in your API keys (see table below)
```

### 3. Run everything (single command)

```bash
./start.sh
```

This launches ngrok, starts the server, and runs all 18 test calls automatically.
Transcripts are saved to `transcripts/` when complete.

> **Or run specific scenarios:** `./start.sh --scenarios prescription_refill urgent_symptoms`

---

### Manual setup (if you prefer separate terminals)

<details>
<summary>Click to expand step-by-step instructions</summary>

**Terminal 1 — ngrok:**
```bash
ngrok http 8765
```

**Terminal 2 — server:**
```bash
python main.py
```

**Terminal 3 — test calls:**
```bash
# Run ALL 18 scenarios:
python run_tests.py

# Run specific scenarios:
python run_tests.py --scenarios new_patient_scheduling prescription_refill

# List available scenarios:
python run_tests.py --list
```

The server auto-detects the ngrok URL. Each call takes ~1–3 minutes.
</details>

---

### API keys needed

| Variable | Where to get it |
|----------|----------------|
| `TWILIO_ACCOUNT_SID` | [twilio.com/console](https://www.twilio.com/console) |
| `TWILIO_AUTH_TOKEN` | [twilio.com/console](https://www.twilio.com/console) |
| `TWILIO_PHONE_NUMBER` | Twilio number with voice capability (e.g. `+12025551234`) |
| `DEEPGRAM_API_KEY` | [console.deepgram.com](https://console.deepgram.com) |
| `OPENAI_API_KEY` | [platform.openai.com/api-keys](https://platform.openai.com/api-keys) |

---

## Running Tests

### List available scenarios

```bash
python run_tests.py --list
```

This shows all 18 test scenarios with their IDs and descriptions.

### Run specific scenarios

**Single scenario:**
```bash
python run_tests.py --scenarios new_patient_scheduling
python run_tests.py --scenarios prescription_refill
python run_tests.py --scenarios cancel_appointment
python run_tests.py --scenarios reschedule_appointment
```

**Multiple scenarios:**
```bash
python run_tests.py --scenarios new_patient_scheduling prescription_refill reschedule_appointment
```

**Recommended core scenarios to test:**
```bash
python run_tests.py --scenarios new_patient_scheduling prescription_refill reschedule_appointment cancel_appointment insurance_question
```

### Run all scenarios

```bash
python run_tests.py
```

This runs all 18 scenarios sequentially. Each call typically takes 60–90 seconds (limited by Pretty Good AI's test line). Total runtime: ~30–45 minutes.

### Customize wait time between calls

```bash
python run_tests.py --scenarios new_patient_scheduling --wait 60
```

Default wait is 120 seconds between calls. Use `--wait` to reduce it (minimum recommended: 60 seconds to avoid rate limiting).

### Transcripts location

Transcripts are saved in **per-scenario directories**:
- `transcripts/new_patient_scheduling/20260219_120000_new_patient_scheduling.txt`
- `transcripts/cancel_appointment/20260219_120000_cancel_appointment.txt`
- `transcripts/prescription_refill/20260219_120000_prescription_refill.txt`
- etc.

Each scenario folder contains both `.txt` (human-readable) and `.json` (machine-readable) transcripts.

### Example: Quick test of core workflows

```bash
# Start the server first (Terminal 2)
python main.py

# Then run these 4 core scenarios (Terminal 3)
python run_tests.py --scenarios new_patient_scheduling prescription_refill reschedule_appointment cancel_appointment
```

---

## How it works

```
┌───────────┐   Phone    ┌─────────┐   WebSocket   ┌──────────────┐
│  Pretty   │◄──────────►│ Twilio  │◄─────────────►│  FastAPI     │
│  Good AI  │   (PSTN)   │  Cloud  │  (Media       │  Server      │
│  Agent    │            │         │   Streams)     │  (main.py)   │
└───────────┘            └─────────┘               └──────┬───────┘
                                                          │
                                    ┌─────────────────────┼──────────────────────┐
                                    │                     │                      │
                              ┌─────▼─────┐        ┌─────▼─────┐         ┌──────▼──────┐
                              │ Deepgram  │        │  OpenAI   │         │  Deepgram   │
                              │ STT       │───────►│  GPT-4o   │────────►│  TTS        │
                              │ (nova-2)  │  text  │  -mini    │  text   │  (Aura)     │
                              └───────────┘        └───────────┘         └─────────────┘
```

1. **Twilio** places an outbound call and streams audio to our server via WebSocket.
2. **Deepgram STT** transcribes the AI agent's speech in real time.
3. **OpenAI GPT-4o-mini** generates the patient's response based on the scenario persona.
4. **Deepgram TTS** converts the response to μ-law audio and streams it back through Twilio.
5. Both sides of the conversation are logged to `transcripts/`.

---

## Project structure

```
├── main.py              FastAPI server + WebSocket endpoint
├── media_stream.py      Core handler bridging Twilio ↔ AI pipeline
├── deepgram_stt.py      Real-time speech-to-text (WebSocket streaming)
├── deepgram_tts.py      Text-to-speech with streaming output
├── llm_service.py       OpenAI LLM for patient dialogue generation
├── call_manager.py      Twilio outbound call management
├── scenarios.py         18 patient scenario definitions
├── transcript.py        Conversation logging (JSON + TXT)
├── config.py            Configuration from environment
├── run_tests.py         CLI test runner for batch execution
├── requirements.txt     Python dependencies
├── start.sh             Single-command launcher (ngrok + server + tests)
├── .env.example         Environment variable template
├── ARCHITECTURE.md      Architecture & design decisions
├── BUG_REPORT.md        Template for documenting findings
└── transcripts/         Generated call transcripts (created at runtime)
```

---

## Test scenarios

**Core patient workflows:**

| # | Scenario | What it tests |
|---|----------|---------------|
| 1 | New patient scheduling | Basic intake, appointment booking |
| 2 | Prescription refill | Medication handling, refill protocol |
| 3 | Cancel appointment | Cancellation flow |
| 4 | Reschedule appointment | Date/time negotiation |
| 5 | Insurance question | Coverage knowledge, billing transfer |
| 6 | Urgent symptoms | Triage, urgency detection |
| 7 | Confused elderly patient | Patience, clarity, repetition handling |
| 8 | Multiple requests | Multi-topic conversation management |
| 9 | Billing inquiry | Billing knowledge, department routing |
| 10 | Lab results inquiry | Results protocol, callback handling |
| 11 | Specialist referral | Referral process, insurance coordination |
| 12 | Non-native English speaker | Language accessibility, simplification |

**Adversarial / edge-case scenarios (finding limits):**

| # | Scenario | What it tests |
|---|----------|---------------|
| 13 | Wrong number — off-topic opener | Boundary handling, unexpected input recovery |
| 14 | HIPAA boundary test | Patient privacy, proxy caller handling |
| 15 | Contradictory information | Correction handling, confusion tolerance |
| 16 | Anxious patient | Empathy, de-escalation, medical judgment boundaries |
| 17 | Office hours & location | Factual recall, logistical knowledge |
| 18 | Rapid topic switching | Context switching, multi-topic resolution |

---

## Transcripts

After running calls, transcripts are saved to **per-scenario subdirectories** under `transcripts/`:

```
transcripts/
├── new_patient_scheduling/
│   ├── 20260219_120000_new_patient_scheduling.json
│   └── 20260219_120000_new_patient_scheduling.txt
├── cancel_appointment/
│   ├── 20260219_120000_cancel_appointment.json
│   └── 20260219_120000_cancel_appointment.txt
└── prescription_refill/
    └── ...
```

Each transcript includes both sides of the conversation:
- **JSON** — machine-readable with timestamps, message count, duration
- **TXT** — human-readable conversation log with labels:
  - `[AI Agent (PrettyGoodAI)]` — the Pretty Good AI agent's speech
  - `[Patient Bot (GPT-4o-mini)]` — our bot's simulated patient responses

**Moving existing transcripts:** If you have old transcripts in the root `transcripts/` folder, run:
```bash
python scripts/move_transcripts_to_scenario_dirs.py
```
This automatically organizes them into the correct scenario subdirectories.

---

## Configuration reference

| Variable | Default | Description |
|----------|---------|-------------|
| `TWILIO_ACCOUNT_SID` | — | Twilio account SID |
| `TWILIO_AUTH_TOKEN` | — | Twilio auth token |
| `TWILIO_PHONE_NUMBER` | — | Your Twilio phone number |
| `TARGET_PHONE_NUMBER` | `+18054398008` | Number to call |
| `DEEPGRAM_API_KEY` | — | Deepgram API key |
| `OPENAI_API_KEY` | — | OpenAI API key |
| `OPENAI_MODEL` | `gpt-4o-mini` | LLM model |
| `SERVER_PORT` | `8765` | Local server port |
| `PUBLIC_URL` | (auto-detect) | ngrok HTTPS URL |
| `MAX_CALL_DURATION` | `300` | Max call length (seconds) — note: Pretty Good AI test line limits calls to ~60–90s |
| `ENDPOINTING_MS` | `1000` | Deepgram silence detection — pause length (ms) before marking phrase as final |
| `UTTERANCE_END_MS` | `2400` | Silence before bot responds (ms) — longer = less mid-sentence interruption |
| `RESPONSE_DELAY_MS` | `200` | Extra delay after UtteranceEnd before bot speaks (ms) |
| `SILENCE_KEEPALIVE_S` | `15` | Bot speaks keepalive prompt if no speech for this long (seconds) |
