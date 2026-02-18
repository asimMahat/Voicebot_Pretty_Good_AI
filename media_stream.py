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

from starlette.websockets import WebSocket

from deepgram_stt import DeepgramSTT
from deepgram_tts import synthesize_stream
from llm_service import get_patient_response
from transcript import TranscriptLogger

logger = logging.getLogger(__name__)

MULAW_FRAME_SIZE = 160  # 20 ms of μ-law audio at 8 kHz


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
            scenario["id"], scenario.get("name", "")
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

        # Control
        self._stop = asyncio.Event()
        self._tasks: list[asyncio.Task] = []

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

        self._tasks = [
            asyncio.create_task(self._twilio_receiver(), name="twilio_rx"),
            asyncio.create_task(self._audio_sender(), name="audio_tx"),
        ]

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
        try:
            async for raw in self.ws.iter_text():
                if self._stop.is_set():
                    break

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
                    logger.info("Twilio stream stopped")
                    break

        except Exception:
            logger.exception("Twilio receiver error")
        finally:
            self._stop.set()

    # ── STT callback ────────────────────────────────────────────────────

    async def _on_transcript(self, text: str, is_utterance_end: bool) -> None:
        """
        Called by DeepgramSTT whenever a transcript result arrives.

        We accumulate ``is_final`` fragments and generate a response once
        ``speech_final`` or ``UtteranceEnd`` signals the speaker stopped.
        """
        if text:
            self._accumulated_text += (" " + text) if self._accumulated_text else text

        if is_utterance_end and self._accumulated_text.strip():
            full_text = self._accumulated_text.strip()
            self._accumulated_text = ""

            logger.info("Agent said: %s", full_text)
            self.transcript_logger.add_message("agent", full_text)
            self.conversation_history.append({"role": "user", "content": full_text})

            # Cancel any in-flight response and start a new one
            if self._speak_task and not self._speak_task.done():
                self._speak_task.cancel()
            self._speak_task = asyncio.create_task(self._generate_and_speak())

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

            if clean:
                self.transcript_logger.add_message("bot", clean)
                self.conversation_history.append(
                    {"role": "assistant", "content": clean}
                )

                # Stream TTS audio into the playback queue
                self._is_speaking = True
                self._barge_in.clear()
                voice = self.scenario.get("voice", "aura-asteria-en")

                async for chunk in synthesize_stream(clean, voice):
                    if self._barge_in.is_set():
                        logger.info("Barge-in detected — stopping TTS playback")
                        break
                    # Split into 20 ms frames for Twilio
                    for i in range(0, len(chunk), MULAW_FRAME_SIZE):
                        frame = chunk[i : i + MULAW_FRAME_SIZE]
                        await self._audio_queue.put(frame)

                # Sentinel: end-of-utterance
                await self._audio_queue.put(None)

            if end_call:
                logger.info("End-of-call signal received — hanging up in 2 s")
                await asyncio.sleep(2)
                await self._hangup()

        except Exception:
            logger.exception("Error in generate_and_speak")

    # ── audio sender (Twilio outbound) ──────────────────────────────────

    async def _audio_sender(self) -> None:
        """
        Pull frames from the audio queue and push them to Twilio at ~20 ms
        intervals to maintain natural playback cadence.
        """
        while not self._stop.is_set():
            try:
                frame = await asyncio.wait_for(
                    self._audio_queue.get(), timeout=0.1
                )
            except asyncio.TimeoutError:
                continue

            if frame is None:
                # End-of-utterance sentinel
                self._is_speaking = False
                continue

            if self.stream_sid:
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
                    break

                # Pace at ~20 ms per frame
                await asyncio.sleep(0.02)

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

        if self.call_sid:
            try:
                await hangup_call(self.call_sid)
                logger.info("Call %s hung up", self.call_sid)
            except Exception:
                logger.exception("Failed to hang up call %s", self.call_sid)
        self._stop.set()

    # ── cleanup ─────────────────────────────────────────────────────────

    async def _cleanup(self) -> None:
        """Release resources and persist the transcript."""
        self._stop.set()

        if self._stt:
            await self._stt.close()

        for t in self._tasks:
            if not t.done():
                t.cancel()

        self.transcript_logger.save()
        logger.info(
            "Call finished — scenario=%s, messages=%d",
            self.scenario["id"],
            len(self.transcript_logger.messages),
        )
