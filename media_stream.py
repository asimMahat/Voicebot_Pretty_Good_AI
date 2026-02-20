"""
Media Stream Handler — the heart of the voice bot.

Bridges a Twilio Media Streams WebSocket connection to:
  • Deepgram STT  (inbound audio → text)
  • OpenAI LLM    (text → patient response)
  • Deepgram TTS  (response → outbound audio)

The handler owns the full lifecycle of a single phone call.
"""

import asyncio
import base64
import json
import logging
import os
import time
from pathlib import Path

from starlette.websockets import WebSocket, WebSocketDisconnect

from config import (
    RESPONSE_DELAY_MS,
    SPEECH_FINAL_DELAY_MS,
    SILENCE_KEEPALIVE_S,
    MEDIA_SILENCE_INTERVAL_MS,
    OPENAI_MODEL,
)
from deepgram_stt import DeepgramSTT, SttEvent
from deepgram_tts import synthesize_stream
from llm_service import get_patient_response
from transcript import TranscriptLogger

logger = logging.getLogger(__name__)

# Directory for TTS audio debug logs
TTS_AUDIO_DIR = Path("tts_audio_logs")
TTS_AUDIO_DIR.mkdir(exist_ok=True)

RESPONSE_DELAY = RESPONSE_DELAY_MS / 1000.0
SPEECH_FINAL_DELAY = SPEECH_FINAL_DELAY_MS / 1000.0
SILENCE_INTERVAL = MEDIA_SILENCE_INTERVAL_MS / 1000.0  # seconds between silence frames when idle

KEEPALIVE_PROMPTS = [
    "I'm still here.",
    "Hello? Are you still there?",
    "I'm still on the line.",
]

MULAW_FRAME_SIZE = 160  # 20 ms of μ-law audio at 8 kHz
SILENCE_FRAME = b"\xff" * MULAW_FRAME_SIZE  # μ-law silence (0xFF = zero amplitude)


class MediaStreamHandler:
    """
    Manages one call's real-time audio pipeline.

    Lifecycle:
        1. Twilio opens a WebSocket and starts streaming inbound audio.
        2. We forward audio to Deepgram STT; transcription results arrive
           asynchronously.
        3. When the remote speaker finishes an utterance (``speech_final``),
           we send the accumulated transcript to the LLM.
        4. The LLM generates a patient response.
        5. We stream that response through Deepgram TTS and send the resulting
           μ-law audio back to Twilio.
        6. If the LLM output contains ``[END_CALL]``, we hang up gracefully.
    """

    def __init__(self, websocket: WebSocket, scenario: dict) -> None:
        self.ws = websocket
        self.scenario = scenario

        # Twilio identifiers (populated on "start" event)
        self.stream_sid: str | None = None
        self.call_sid: str | None = None

        # Conversation state
        self.conversation_history: list[dict] = []
        self.transcript_logger = TranscriptLogger(
            scenario["id"], scenario.get("name", ""), model_name=OPENAI_MODEL
        )

        # Audio playback state
        self._audio_queue: asyncio.Queue[bytes | None] = asyncio.Queue()
        self._is_speaking = False
        self._barge_in = asyncio.Event()

        # STT
        self._stt: DeepgramSTT | None = None
        self._accumulated_text: str = ""

        # Concurrency: prevent overlapping response generation
        self._response_lock = asyncio.Lock()
        self._speak_task: asyncio.Task | None = None

        # Silence keepalive
        self._last_activity: float = time.monotonic()
        self._keepalive_index: int = 0

        # Control
        self._stop = asyncio.Event()
        self._tasks: list[asyncio.Task] = []
        self._bot_initiated_hangup = False  # True if we called _hangup()
        self._call_end_reason: str | None = None  # twilio_stop_event | websocket_closed | receiver_error_* | None
        self._websocket_close_code: int | None = None  # WebSocket close code (1000=normal, etc.)
        self._websocket_close_reason: str | None = None  # WebSocket close reason string

    # ── public entry point ──────────────────────────────────────────────

    async def run(self) -> None:
        """Drive the call from connect to hangup."""
        self._stt = DeepgramSTT(self._on_transcript)

        try:
            await self._stt.connect()
        except Exception:
            logger.exception("Failed to connect to Deepgram STT — call will end")
            self.transcript_logger.add_message(
                "bot", "[SYSTEM ERROR: Deepgram STT connection failed]"
            )
            self.transcript_logger.save()
            return

        self._last_activity = time.monotonic()

        self._tasks = [
            asyncio.create_task(self._twilio_receiver(), name="twilio_rx"),
            asyncio.create_task(self._audio_sender(), name="audio_tx"),
            asyncio.create_task(self._silence_keepalive(), name="keepalive"),
        ]

        # No initial greeting — let Pretty Good AI's agent speak first.

        try:
            # Wait until any task finishes (usually twilio_rx on hangup)
            done, _ = await asyncio.wait(
                self._tasks, return_when=asyncio.FIRST_COMPLETED
            )
            for t in done:
                if t.exception():
                    logger.error("Task %s failed: %s", t.get_name(), t.exception())
        finally:
            await self._cleanup()

    # ── Twilio WebSocket receiver ───────────────────────────────────────

    async def _twilio_receiver(self) -> None:
        """Read events from the Twilio Media Streams WebSocket."""
        msg_count = 0
        try:
            async for raw in self.ws.iter_text():
                if self._stop.is_set():
                    logger.info("Twilio receiver: stop flag set after %d messages", msg_count)
                    break

                msg_count += 1
                data = json.loads(raw)
                event = data.get("event")

                if event == "media":
                    payload = data["media"]["payload"]
                    audio_bytes = base64.b64decode(payload)
                    if self._stt:
                        await self._stt.send_audio(audio_bytes)

                elif event == "start":
                    self.stream_sid = data["start"]["streamSid"]
                    self.call_sid = data["start"].get("callSid")
                    logger.info(
                        "Stream started — sid=%s call=%s",
                        self.stream_sid,
                        self.call_sid,
                    )

                elif event == "stop":
                    # Log full stop payload for debugging (Twilio may send custom params)
                    stop_payload = data.get("stop", data)
                    logger.warning(
                        "REMOTE HANGUP: Twilio 'stop' event after %d messages — "
                        "Pretty Good AI or Twilio ended the call. payload=%s",
                        msg_count,
                        stop_payload,
                    )
                    self._call_end_reason = "twilio_stop_event"
                    break

            else:
                # Loop ended without break = WebSocket closed without "stop" event
                logger.warning(
                    "REMOTE HANGUP: WebSocket closed after %d messages (no 'stop' event) — "
                    "connection dropped by remote or network",
                    msg_count,
                )
                self._call_end_reason = "websocket_closed"

        except WebSocketDisconnect as e:
            # WebSocket closed with a close code/reason
            # Common codes: 1000=normal, 1001=going_away, 1006=abnormal_close, 1011=server_error
            self._websocket_close_code = e.code
            self._websocket_close_reason = e.reason or ""
            logger.warning(
                "REMOTE HANGUP: WebSocket disconnected after %d messages — "
                "close_code=%d reason=%r",
                msg_count,
                e.code,
                e.reason,
            )
            self._call_end_reason = f"websocket_disconnect_code_{e.code}"
            if not self._stop.is_set():
                logger.info("Call ended by remote side (WebSocket disconnect)")

        except Exception as e:
            logger.exception(
                "Twilio receiver error after %d messages: %s", msg_count, e
            )
            self._call_end_reason = f"receiver_error_{type(e).__name__}"
        finally:
            logger.info("Twilio receiver exiting (%d messages received)", msg_count)
            if not self._stop.is_set():
                logger.info("Call ended by remote side (not bot-initiated)")
            self._stop.set()

    # ── STT callback ────────────────────────────────────────────────────

    async def _on_transcript(self, text: str, event: SttEvent) -> None:
        """
        Called by DeepgramSTT whenever a transcript result arrives.

        Strategy: only respond on UTTERANCE_END (long silence confirmed).
        FINAL / SPEECH_FINAL just accumulate text and cancel any pending
        response, since the agent may still be mid-turn with natural pauses
        between sentences.
        """
        self._last_activity = time.monotonic()

        if text:
            self._accumulated_text += (" " + text) if self._accumulated_text else text
            if self._speak_task and not self._speak_task.done():
                self._speak_task.cancel()
                self._speak_task = None
            logger.debug("Accumulated: %s", self._accumulated_text)

        if event == SttEvent.UTTERANCE_END and self._accumulated_text.strip():
            if self._speak_task and not self._speak_task.done():
                self._speak_task.cancel()
            self._speak_task = asyncio.create_task(
                self._delayed_respond(RESPONSE_DELAY)
            )

    async def _delayed_respond(self, delay: float) -> None:
        """Wait *delay* seconds, then log the agent's utterance and respond."""
        try:
            await asyncio.sleep(delay)
        except asyncio.CancelledError:
            return

        full_text = self._accumulated_text.strip()
        if not full_text:
            return
        self._accumulated_text = ""

        self._last_activity = time.monotonic()

        logger.info("Agent said: %s", full_text)
        self.transcript_logger.add_message("agent", full_text)
        self.conversation_history.append({"role": "user", "content": full_text})

        await self._generate_and_speak()

    # ── initial greeting ────────────────────────────────────────────

    async def _send_initial_greeting(self) -> None:
        """
        Speak a short greeting when the call connects.

        This serves two purposes:
          1. Keeps the Twilio media stream alive by sending outbound audio.
          2. Prompts the Pretty Good AI agent to begin its flow.
        """
        await asyncio.sleep(1.5)  # small delay for the call to fully connect
        if self._stop.is_set():
            return

        greeting = self.scenario.get(
            "opening_line", "Hi, I'm calling about an appointment."
        )
        logger.info("Sending initial greeting: %s", greeting)
        self.transcript_logger.add_message("bot", greeting)
        self.conversation_history.append({"role": "assistant", "content": greeting})

        voice = self.scenario.get("voice", "aura-asteria-en")
        self._is_speaking = True
        try:
            async for chunk in synthesize_stream(greeting, voice):
                for i in range(0, len(chunk), MULAW_FRAME_SIZE):
                    frame = chunk[i : i + MULAW_FRAME_SIZE]
                    await self._audio_queue.put(frame)
            await self._audio_queue.put(None)
        except Exception:
            logger.exception("Failed to send initial greeting")
            self._is_speaking = False

        self._last_activity = time.monotonic()

    # ── silence keepalive ────────────────────────────────────────────

    async def _silence_keepalive(self) -> None:
        """If nobody has spoken for a while, say something to keep the call alive."""
        while not self._stop.is_set():
            await asyncio.sleep(3)
            elapsed = time.monotonic() - self._last_activity
            if elapsed >= SILENCE_KEEPALIVE_S and not self._is_speaking:
                prompt = KEEPALIVE_PROMPTS[self._keepalive_index % len(KEEPALIVE_PROMPTS)]
                self._keepalive_index += 1
                logger.info("Silence keepalive: %s", prompt)

                self._last_activity = time.monotonic()
                voice = self.scenario.get("voice", "aura-asteria-en")
                self._is_speaking = True
                async for chunk in synthesize_stream(prompt, voice):
                    for i in range(0, len(chunk), MULAW_FRAME_SIZE):
                        frame = chunk[i : i + MULAW_FRAME_SIZE]
                        await self._audio_queue.put(frame)
                await self._audio_queue.put(None)

    # ── response generation + TTS ───────────────────────────────────────

    async def _generate_and_speak(self) -> None:
        """Get LLM response, stream TTS audio to Twilio."""
        try:
            async with self._response_lock:
                await self._do_generate_and_speak()
        except asyncio.CancelledError:
            logger.debug("Response generation cancelled (barge-in)")
            await self._clear_audio()

    async def _do_generate_and_speak(self) -> None:
        """Inner logic for response generation (runs under lock)."""
        # Interrupt any current playback (barge-in)
        await self._clear_audio()

        try:
            response = await get_patient_response(
                self.conversation_history,
                self.scenario["system_prompt"],
            )

            end_call = "[END_CALL]" in response
            clean = response.replace("[END_CALL]", "").strip()

            if end_call:
                logger.warning(
                    "[END_CALL] detected in LLM response — bot will hang up. "
                    "Full response: %s",
                    response,
                )

            if clean:
                self.transcript_logger.add_message("bot", clean)
                self.conversation_history.append(
                    {"role": "assistant", "content": clean}
                )

                # Stream TTS audio into the playback queue + log to file
                self._is_speaking = True
                self._barge_in.clear()
                voice = self.scenario.get("voice", "aura-asteria-en")

                # Create audio log file for this utterance
                timestamp = time.strftime("%Y%m%d_%H%M%S")
                audio_log_path = (
                    TTS_AUDIO_DIR
                    / f"{timestamp}_{self.scenario['id']}_{len(self.conversation_history)}.mulaw"
                )
                audio_bytes = bytearray()

                async for chunk in synthesize_stream(clean, voice):
                    if self._barge_in.is_set():
                        logger.info("Barge-in detected — stopping TTS playback")
                        break
                    audio_bytes.extend(chunk)
                    # Split into 20 ms frames for Twilio
                    for i in range(0, len(chunk), MULAW_FRAME_SIZE):
                        frame = chunk[i : i + MULAW_FRAME_SIZE]
                        await self._audio_queue.put(frame)

                # Save audio to file for debugging
                if audio_bytes:
                    with open(audio_log_path, "wb") as f:
                        f.write(audio_bytes)
                    logger.debug(
                        "TTS audio saved → %s (%d bytes, text: %s)",
                        audio_log_path.name,
                        len(audio_bytes),
                        clean[:50],
                    )

                # Sentinel: end-of-utterance
                await self._audio_queue.put(None)

            if end_call:
                logger.warning(
                    "Bot-initiated hangup: [END_CALL] signal — hanging up in 2 s"
                )
                await asyncio.sleep(2)
                await self._hangup()

        except Exception:
            logger.exception("Error in generate_and_speak")

    # ── audio sender (Twilio outbound) ──────────────────────────────────

    async def _audio_sender(self) -> None:
        """
        Pull frames from the audio queue and push them to Twilio at ~20 ms
        intervals to maintain natural playback cadence.

        When the queue is empty, send silence frames at SILENCE_INTERVAL to keep
        the Twilio Media Stream (and any proxy/ngrok) alive and prevent cutoffs.
        """
        silence_interval = max(0.05, SILENCE_INTERVAL)  # at least 50 ms
        while not self._stop.is_set():
            try:
                frame = await asyncio.wait_for(
                    self._audio_queue.get(), timeout=silence_interval
                )
            except asyncio.TimeoutError:
                # Send a silence frame to keep stream alive (prevents proxy/Twilio idle disconnect)
                if self.stream_sid:
                    await self._send_frame(SILENCE_FRAME)
                continue

            if frame is None:
                self._is_speaking = False
                continue

            await self._send_frame(frame)
            await asyncio.sleep(0.02)

    async def _send_frame(self, frame: bytes) -> None:
        """Send a single audio frame to Twilio."""
        if not self.stream_sid:
            return
        payload = base64.b64encode(frame).decode("ascii")
        msg = {
            "event": "media",
            "streamSid": self.stream_sid,
            "media": {"payload": payload},
        }
        try:
            await self.ws.send_json(msg)
        except Exception:
            logger.warning("Failed to send audio frame to Twilio")

    # ── barge-in / clear ────────────────────────────────────────────────

    async def _clear_audio(self) -> None:
        """Flush the playback queue and tell Twilio to clear its buffer."""
        self._barge_in.set()

        # Drain the queue
        while not self._audio_queue.empty():
            try:
                self._audio_queue.get_nowait()
            except asyncio.QueueEmpty:
                break

        # Ask Twilio to drop any buffered audio
        if self.stream_sid:
            try:
                await self.ws.send_json(
                    {"event": "clear", "streamSid": self.stream_sid}
                )
            except Exception:
                pass

        self._is_speaking = False

    # ── call control ────────────────────────────────────────────────────

    async def _hangup(self) -> None:
        """End the Twilio call via REST API."""
        from call_manager import hangup_call

        self._bot_initiated_hangup = True
        self._call_end_reason = "bot_hangup"
        if self.call_sid:
            logger.warning(
                "BOT-INITIATED HANGUP: Calling Twilio API to end call %s",
                self.call_sid,
            )
            try:
                await hangup_call(self.call_sid)
                logger.warning("Call %s successfully hung up by bot", self.call_sid)
            except Exception:
                logger.exception("Failed to hang up call %s", self.call_sid)
        else:
            logger.warning("BOT-INITIATED HANGUP: No call_sid available")
        self._stop.set()

    # ── cleanup ─────────────────────────────────────────────────────────

    async def _cleanup(self) -> None:
        """Release resources and persist the transcript."""
        self._stop.set()

        # ----- DEBUG: Unmissable call-end summary (check SERVER terminal, not test runner) -----
        ended_by = "bot" if self._bot_initiated_hangup else "remote"
        reason = self._call_end_reason or ("bot_hangup" if self._bot_initiated_hangup else "unknown")
        logger.warning(
            "========== CALL END ========== ended_by=%s reason=%s scenario=%s",
            ended_by,
            reason,
            self.scenario["id"],
        )
        if self._bot_initiated_hangup:
            logger.warning("  -> Bot ended call (LLM returned [END_CALL])")
        else:
            logger.warning(
                "  -> Remote ended call (Pretty Good AI agent or Twilio). reason=%s",
                reason,
            )
            if self._websocket_close_code is not None:
                logger.warning(
                    "  -> WebSocket close_code=%d reason=%r",
                    self._websocket_close_code,
                    self._websocket_close_reason or "(none)",
                )
            
            # Query Twilio API for call details to understand why Twilio ended it
            if self.call_sid:
                from call_manager import get_call_details
                call_details = await get_call_details(self.call_sid)
                if call_details:
                    ended_by_twilio = call_details.get("ended_by")
                    logger.warning(
                        "  -> Twilio call details: status=%s duration=%ss ended_by=%s error_code=%s error_message=%s",
                         call_details.get("status"),
                        call_details.get("duration"),
                        ended_by_twilio or "(unknown)",
                        call_details.get("error_code"),
                        call_details.get("error_message"),
                    )
                    if ended_by_twilio:
                        if ended_by_twilio == "caller":
                            logger.warning("  -> 📞 Twilio says: Caller (our bot) ended the call")
                        elif ended_by_twilio == "callee":
                            logger.warning("  -> 📞 Twilio says: Callee (Pretty Good AI agent) ended the call")
                    if call_details.get("error_code") or call_details.get("error_message"):
                        logger.warning(
                            "  -> ⚠️  Twilio error: code=%s message=%s",
                            call_details.get("error_code"),
                            call_details.get("error_message"),
                        )
        # ----------------------------------------------------------------------------------------

        if self._stt:
            await self._stt.close()

        for t in self._tasks:
            if not t.done():
                t.cancel()

        remaining = self._accumulated_text.strip()
        if remaining:
            logger.info("Agent said (end-of-call): %s", remaining)
            self.transcript_logger.add_message("agent", remaining)
            self._accumulated_text = ""

        self.transcript_logger.save()

        logger.info(
            "Call finished — scenario=%s, messages=%d, ended_by=%s, reason=%s",
            self.scenario["id"],
            len(self.transcript_logger.messages),
            ended_by,
            reason,
        )
