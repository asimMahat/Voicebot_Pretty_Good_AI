"""
Configuration management — loads settings from environment variables.
"""

import os
from dotenv import load_dotenv

load_dotenv()

# ── Twilio ──────────────────────────────────────────────────────────────
TWILIO_ACCOUNT_SID: str = os.getenv("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN: str = os.getenv("TWILIO_AUTH_TOKEN", "")
TWILIO_PHONE_NUMBER: str = os.getenv("TWILIO_PHONE_NUMBER", "")  # Your Twilio number

# ── Target ──────────────────────────────────────────────────────────────
TARGET_PHONE_NUMBER: str = os.getenv("TARGET_PHONE_NUMBER", "+18054398008")

# ── Deepgram ────────────────────────────────────────────────────────────
DEEPGRAM_API_KEY: str = os.getenv("DEEPGRAM_API_KEY", "")

# ── OpenAI ──────────────────────────────────────────────────────────────
OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

# ── Server ──────────────────────────────────────────────────────────────
SERVER_HOST: str = os.getenv("SERVER_HOST", "0.0.0.0")
SERVER_PORT: int = int(os.getenv("SERVER_PORT", "8765"))
PUBLIC_URL: str = os.getenv("PUBLIC_URL", "")  # ngrok HTTPS URL

# ── Call settings ───────────────────────────────────────────────────────
MAX_CALL_DURATION: int = int(os.getenv("MAX_CALL_DURATION", "180"))  # seconds
ENDPOINTING_MS: int = int(os.getenv("ENDPOINTING_MS", "300"))  # Deepgram silence detection
UTTERANCE_END_MS: int = int(os.getenv("UTTERANCE_END_MS", "1200"))  # Deepgram utterance end


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
