"""
Deepgram real-time Speech-to-Text via WebSocket.

Streams raw μ-law audio from Twilio and returns transcription events.
"""

import asyncio
import json
import logging
from typing import Callable, Awaitable

import websockets
from websockets.asyncio.client import ClientConnection

from config import DEEPGRAM_API_KEY, ENDPOINTING_MS, UTTERANCE_END_MS

logger = logging.getLogger(__name__)

# Callback signature: (transcript_text: str, is_utterance_end: bool) -> None
TranscriptCallback = Callable[[str, bool], Awaitable[None]]


class DeepgramSTT:
    """
    Manages a persistent WebSocket to Deepgram's streaming STT API.

    Audio is pushed via :meth:`send_audio`; transcription results trigger
    the callback passed at construction.
    """

    def __init__(self, on_transcript: TranscriptCallback) -> None:
        self._on_transcript = on_transcript
        self._ws: ClientConnection | None = None
        self._running = False
        self._recv_task: asyncio.Task | None = None
        self._keepalive_task: asyncio.Task | None = None

    # ── lifecycle ───────────────────────────────────────────────────────

    async def connect(self) -> None:
        """Open the WebSocket connection to Deepgram."""
        params = "&".join([
            "encoding=mulaw",
            "sample_rate=8000",
            "channels=1",
            "model=nova-2",
            "punctuate=true",
            f"endpointing={ENDPOINTING_MS}",
            "interim_results=false",
            f"utterance_end_ms={UTTERANCE_END_MS}",
            "vad_events=true",
        ])
        url = f"wss://api.deepgram.com/v1/listen?{params}"

        extra_headers = {"Authorization": f"Token {DEEPGRAM_API_KEY}"}

        self._ws = await websockets.connect(
            url,
            additional_headers=extra_headers,
            ping_interval=20,
            ping_timeout=10,
        )
        self._running = True
        self._recv_task = asyncio.create_task(self._receive_loop())
        self._keepalive_task = asyncio.create_task(self._keepalive_loop())
        logger.info("Deepgram STT connected")

    async def close(self) -> None:
        """Gracefully shut down the connection."""
        self._running = False
        if self._ws:
            try:
                await self._ws.send(json.dumps({"type": "CloseStream"}))
                await self._ws.close()
            except Exception:
                pass
        if self._recv_task:
            self._recv_task.cancel()
        if self._keepalive_task:
            self._keepalive_task.cancel()
        logger.info("Deepgram STT closed")

    # ── audio input ─────────────────────────────────────────────────────

    async def send_audio(self, audio_bytes: bytes) -> None:
        """Forward a chunk of μ-law audio to Deepgram."""
        if self._ws and self._running:
            try:
                await self._ws.send(audio_bytes)
            except Exception:
                logger.warning("Failed to send audio to Deepgram")

    # ── internal loops ──────────────────────────────────────────────────

    async def _receive_loop(self) -> None:
        """Read transcription results from Deepgram and fire callbacks."""
        assert self._ws is not None
        try:
            async for raw in self._ws:
                if not self._running:
                    break
                data = json.loads(raw)
                msg_type = data.get("type", "")

                if msg_type == "Results":
                    alt = data["channel"]["alternatives"][0]
                    transcript: str = alt.get("transcript", "")
                    is_final: bool = data.get("is_final", False)
                    speech_final: bool = data.get("speech_final", False)

                    if transcript and is_final:
                        await self._on_transcript(transcript, speech_final)

                elif msg_type == "UtteranceEnd":
                    # Deepgram signals a long silence — treat as turn end.
                    await self._on_transcript("", True)

        except websockets.exceptions.ConnectionClosed:
            logger.info("Deepgram STT WebSocket closed")
        except Exception:
            logger.exception("Deepgram STT receive error")
        finally:
            self._running = False

    async def _keepalive_loop(self) -> None:
        """Send periodic keepalive messages to prevent idle timeout."""
        try:
            while self._running:
                await asyncio.sleep(8)
                if self._ws and self._running:
                    await self._ws.send(json.dumps({"type": "KeepAlive"}))
        except asyncio.CancelledError:
            pass
        except Exception:
            pass
