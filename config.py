"""
Configuration management — loads settings from environment variables.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

# Always load .env from the directory containing this file (project root).
# So the app finds the same .env no matter where you start the server from.
_env_path = Path(__file__).resolve().parent / ".env"
load_dotenv(dotenv_path=_env_path)


def _getenv(key: str, default: str = "") -> str:
    """Get env var and strip whitespace (stops trailing newline/space in .env from breaking keys)."""
    return (os.getenv(key) or default).strip()


# ── Twilio ──────────────────────────────────────────────────────────────
TWILIO_ACCOUNT_SID: str = _getenv("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN: str = _getenv("TWILIO_AUTH_TOKEN", "")
TWILIO_PHONE_NUMBER: str = _getenv("TWILIO_PHONE_NUMBER", "")

# ── Target ──────────────────────────────────────────────────────────────
TARGET_PHONE_NUMBER: str = _getenv("TARGET_PHONE_NUMBER", "")

# ── Deepgram ────────────────────────────────────────────────────────────
DEEPGRAM_API_KEY: str = _getenv("DEEPGRAM_API_KEY", "")

# ── OpenAI ──────────────────────────────────────────────────────────────
OPENAI_API_KEY: str = _getenv("OPENAI_API_KEY", "")
OPENAI_MODEL: str = _getenv("OPENAI_MODEL", "gpt-4o-mini")

# ── Server ──────────────────────────────────────────────────────────────
SERVER_HOST: str = _getenv("SERVER_HOST", "0.0.0.0")
SERVER_PORT: int = int(_getenv("SERVER_PORT", "8765"))
PUBLIC_URL: str = _getenv("PUBLIC_URL", "")

# ── Call settings ───────────────────────────────────────────────────────
MAX_CALL_DURATION: int = int(_getenv("MAX_CALL_DURATION", "300"))
ENDPOINTING_MS: int = int(_getenv("ENDPOINTING_MS", "1000"))
UTTERANCE_END_MS: int = int(_getenv("UTTERANCE_END_MS", "2400"))  # ms silence before we respond (longer = less mid-sentence cut-off)
RESPONSE_DELAY_MS: int = int(_getenv("RESPONSE_DELAY_MS", "200"))
SPEECH_FINAL_DELAY_MS: int = int(_getenv("SPEECH_FINAL_DELAY_MS", "1200"))
SILENCE_KEEPALIVE_S: float = float(_getenv("SILENCE_KEEPALIVE_S", "15"))
# How often to send silence to Twilio when we have no speech (keeps stream alive; prevents cutoffs)
MEDIA_SILENCE_INTERVAL_MS: int = int(_getenv("MEDIA_SILENCE_INTERVAL_MS", "100"))


def detect_ngrok_url() -> str:
    """Auto-detect ngrok public URL by querying its local API."""
    if PUBLIC_URL:
        return PUBLIC_URL
    try:
        import httpx
        resp = httpx.get("http://localhost:4040/api/tunnels", timeout=2.0)
        tunnels = resp.json().get("tunnels", [])
        for tunnel in tunnels:
            if tunnel.get("proto") == "https":
                return tunnel["public_url"]
    except Exception:
        pass
    return ""


def validate_config() -> list[str]:
    """Return a list of missing required config values."""
    missing = []
    if not TWILIO_ACCOUNT_SID:
        missing.append("TWILIO_ACCOUNT_SID")
    if not TWILIO_AUTH_TOKEN:
        missing.append("TWILIO_AUTH_TOKEN")
    if not TWILIO_PHONE_NUMBER:
        missing.append("TWILIO_PHONE_NUMBER")
    if not DEEPGRAM_API_KEY:
        missing.append("DEEPGRAM_API_KEY")
    if not OPENAI_API_KEY:
        missing.append("OPENAI_API_KEY")
    return missing
