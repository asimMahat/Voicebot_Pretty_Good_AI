"""
Twilio call management — initiating outbound calls and controlling them.
"""

import asyncio
import logging
from functools import partial

from twilio.rest import Client
from twilio.twiml.voice_response import VoiceResponse, Connect

from config import (
    TWILIO_ACCOUNT_SID,
    TWILIO_AUTH_TOKEN,
    TWILIO_PHONE_NUMBER,
    TARGET_PHONE_NUMBER,
    MAX_CALL_DURATION,
)

logger = logging.getLogger(__name__)

_client: Client | None = None


def _get_client() -> Client:
    global _client
    if _client is None:
        _client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
    return _client


def _build_twiml(public_url: str, scenario_id: str) -> str:
    """
    Build TwiML that connects the call to our Media Streams WebSocket.

    The ``scenario_id`` is passed as a custom parameter so the server
    knows which patient persona to load.
    """
    response = VoiceResponse()
    connect = Connect()
    # Strip protocol for the WSS URL
    ws_host = public_url.replace("https://", "").replace("http://", "")
    stream = connect.stream(url=f"wss://{ws_host}/media-stream")
    stream.parameter(name="scenario_id", value=scenario_id)
    response.append(connect)
    return str(response)


def make_call(public_url: str, scenario_id: str) -> str:
    """
    Place an outbound call to the target number.

    Returns the Twilio Call SID.
    """
    client = _get_client()
    twiml = _build_twiml(public_url, scenario_id)

    logger.info(
        "Placing call → %s (scenario: %s)", TARGET_PHONE_NUMBER, scenario_id
    )

    call = client.calls.create(
        to=TARGET_PHONE_NUMBER,
        from_=TWILIO_PHONE_NUMBER,
        twiml=twiml,
        timeout=30,
        time_limit=MAX_CALL_DURATION,
        record=True,
        recording_channels="dual",
        status_callback=f"{public_url}/call-status",
        status_callback_event=["completed"],
    )

    logger.info("Call created — SID: %s", call.sid)
    return call.sid


async def hangup_call(call_sid: str) -> None:
    """End a call in progress (async-safe wrapper around sync Twilio client)."""
    client = _get_client()
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(
        None,
        partial(client.calls(call_sid).update, status="completed"),
    )


def get_call_status(call_sid: str) -> str:
    """Fetch the current status of a call."""
    client = _get_client()
    call = client.calls(call_sid).fetch()
    return call.status


async def get_call_details(call_sid: str) -> dict | None:
    """
    Fetch full call details from Twilio API including status, duration, and end reason.
    
    Returns a dict with call information, or None if the call doesn't exist.
    """
    try:
        client = _get_client()
        loop = asyncio.get_running_loop()
        call = await loop.run_in_executor(None, lambda: client.calls(call_sid).fetch())
        
        return {
            "sid": call.sid,
            "status": call.status,
            "duration": call.duration,  # seconds
            "direction": call.direction,
            "start_time": str(call.start_time),
            "end_time": str(call.end_time) if call.end_time else None,
            # Who ended the call: "caller" or "callee" (based on SIP BYE direction)
            "ended_by": getattr(call, "ended_by", None),
            # Twilio may provide these fields:
            "subresource_uris": call.subresource_uris,
            # Check for any error codes or reasons
            "error_code": getattr(call, "error_code", None),
            "error_message": getattr(call, "error_message", None),
        }
    except Exception as e:
        logger.warning("Failed to fetch call details for %s: %s", call_sid, e)
        return None
