"""
Deepgram Text-to-Speech service.

Converts text to μ-law 8 kHz audio suitable for Twilio Media Streams.
Supports both streaming (chunked) and one-shot synthesis.
"""

import logging
from typing import AsyncIterator

import httpx

from config import DEEPGRAM_API_KEY

logger = logging.getLogger(__name__)

TTS_BASE_URL = "https://api.deepgram.com/v1/speak"
CHUNK_SIZE = 3200  # ~200 ms of audio per yield (160 bytes = 20 ms)


def _build_headers() -> dict[str, str]:
    return {
        "Authorization": f"Token {DEEPGRAM_API_KEY}",
        "Content-Type": "application/json",
    }


def _build_params(voice: str) -> dict[str, str]:
    return {
        "model": voice,
        "encoding": "mulaw",
        "sample_rate": "8000",
        "container": "none",
    }


async def synthesize(text: str, voice: str = "aura-asteria-en") -> bytes:
    """
    One-shot synthesis — returns complete μ-law audio bytes.
    """
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            TTS_BASE_URL,
            params=_build_params(voice),
            headers=_build_headers(),
            json={"text": text},
            timeout=15.0,
        )
        resp.raise_for_status()
        return resp.content


async def synthesize_stream(
    text: str,
    voice: str = "aura-asteria-en",
) -> AsyncIterator[bytes]:
    """
    Streaming synthesis — yields μ-law audio chunks as they arrive.

    Each chunk is ``CHUNK_SIZE`` bytes (~200 ms at 8 kHz μ-law).
    This lets us start playing audio before synthesis finishes,
    dramatically reducing perceived latency.
    """
    async with httpx.AsyncClient() as client:
        async with client.stream(
            "POST",
            TTS_BASE_URL,
            params=_build_params(voice),
            headers=_build_headers(),
            json={"text": text},
            timeout=20.0,
        ) as resp:
            resp.raise_for_status()
            async for chunk in resp.aiter_bytes(chunk_size=CHUNK_SIZE):
                yield chunk
