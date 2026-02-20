"""
Pretty Good AI — Voice Bot Tester

FastAPI server that:
  • Exposes a WebSocket endpoint for Twilio Media Streams
  • Provides REST endpoints to trigger test calls
  • Bridges phone audio to the Deepgram + OpenAI AI pipeline
"""

import json
import logging
import os
import sys

from fastapi import FastAPI, WebSocket, HTTPException, Request
from fastapi.responses import JSONResponse
import uvicorn

from config import SERVER_HOST, SERVER_PORT, detect_ngrok_url, validate_config
from call_manager import make_call, get_call_status
from media_stream import MediaStreamHandler
from scenarios import SCENARIOS, get_scenario, list_scenario_ids

# ── Logging ─────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("voicebot")

# ── FastAPI app ─────────────────────────────────────────────────────────
app = FastAPI(
    title="Pretty Good AI — Voice Bot Tester",
    description="Automated voice bot that calls and tests the AI agent",
)

# Resolved at startup
_public_url: str = ""


# ── Events ──────────────────────────────────────────────────────────────

@app.on_event("startup")
async def startup() -> None:
    global _public_url

    # Validate required config
    missing = validate_config()
    if missing:
        logger.error("Missing required config: %s", ", ".join(missing))
        logger.error("Copy .env.example → .env and fill in the values.")
        sys.exit(1)

    # Resolve public URL (manual or auto-detect from ngrok)
    _public_url = detect_ngrok_url()
    if not _public_url:
        logger.error(
            "No PUBLIC_URL set and ngrok not detected. "
            "Start ngrok (ngrok http %d) or set PUBLIC_URL in .env",
            SERVER_PORT,
        )
        sys.exit(1)

    logger.info("Server ready — public URL: %s", _public_url)
    logger.info("Available scenarios: %s", ", ".join(list_scenario_ids()))


# ── WebSocket: Twilio Media Streams ─────────────────────────────────────

@app.websocket("/media-stream")
async def media_stream_endpoint(websocket: WebSocket) -> None:
    """
    Twilio connects here when a call starts.

    Event flow: connected → start (with customParameters) → media … → stop
    """
    await websocket.accept()
    logger.info("Twilio WebSocket connected")

    scenario: dict | None = None

    try:
        # Twilio sends "connected" first, then "start" with metadata
        while scenario is None:
            raw = await websocket.receive_text()
            data = json.loads(raw)
            event = data.get("event")

            if event == "start":
                params = data["start"].get("customParameters", {})
                scenario_id = params.get("scenario_id", "new_patient_scheduling")
                scenario = get_scenario(scenario_id)
                if scenario is None:
                    logger.warning("Unknown scenario %s — using default", scenario_id)
                    scenario = SCENARIOS[0]
                logger.info(
                    "Call started — scenario: %s, stream: %s",
                    scenario["id"],
                    data["start"].get("streamSid"),
                )
                break

            elif event == "connected":
                logger.debug("Twilio protocol connected")

            else:
                logger.warning("Unexpected initial event: %s", event)

        if scenario is None:
            logger.error("Never received start event — closing")
            return

        # Hand off to the handler; it will re-process the start event
        handler = MediaStreamHandler(websocket, scenario)
        handler.stream_sid = data["start"].get("streamSid")
        handler.call_sid = data["start"].get("callSid")
        await handler.run()

    except Exception:
        logger.exception("Media stream error")


# ── REST endpoints ──────────────────────────────────────────────────────

@app.post("/make-call")
async def trigger_call(request: Request) -> JSONResponse:
    """
    Initiate a test call.

    Body: ``{"scenario_id": "prescription_refill"}``
    """
    body = await request.json()
    scenario_id = body.get("scenario_id")

    if not scenario_id:
        raise HTTPException(400, "scenario_id is required")

    scenario = get_scenario(scenario_id)
    if scenario is None:
        raise HTTPException(
            400,
            f"Unknown scenario: {scenario_id}. "
            f"Available: {', '.join(list_scenario_ids())}",
        )

    try:
        call_sid = make_call(_public_url, scenario_id)
    except Exception as exc:
        logger.exception("Failed to place call")
        raise HTTPException(500, f"Twilio error: {exc}") from exc

    return JSONResponse(
        {"call_sid": call_sid, "scenario_id": scenario_id, "status": "initiated"}
    )


@app.get("/call-status/{call_sid}")
async def check_call_status(call_sid: str) -> JSONResponse:
    """Check the status of a call."""
    try:
        status = get_call_status(call_sid)
    except Exception as exc:
        raise HTTPException(404, f"Call not found: {exc}") from exc
    return JSONResponse({"call_sid": call_sid, "status": status})


@app.post("/call-status")
async def call_status_webhook(request: Request) -> JSONResponse:
    """Twilio status callback webhook."""
    form = await request.form()
    call_sid = form.get("CallSid", "unknown")
    status = form.get("CallStatus", "unknown")
    duration = form.get("CallDuration", "0")
    logger.info("Call %s → %s (duration: %ss)", call_sid, status, duration)
    return JSONResponse({"status": "ok"})


@app.get("/scenarios")
async def list_scenarios() -> JSONResponse:
    """List all available test scenarios."""
    summaries = [
        {"id": s["id"], "name": s["name"], "description": s["description"]}
        for s in SCENARIOS
    ]
    return JSONResponse(summaries)


@app.get("/health")
async def health() -> JSONResponse:
    return JSONResponse({"status": "ok", "public_url": _public_url})


# ── Entry point ─────────────────────────────────────────────────────────

if __name__ == "__main__":
    # Reload: restart server when code changes (dev only; set RELOAD=0 to disable)
    reload = os.environ.get("RELOAD", "1").strip().lower() in ("1", "true", "yes")
    uvicorn.run(
        "main:app",
        host=SERVER_HOST,
        port=SERVER_PORT,
        log_level="info",
        reload=reload,
    )
