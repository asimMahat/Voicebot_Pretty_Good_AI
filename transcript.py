"""
Conversation transcript logger.

Stores both sides of each call in JSON (machine-readable) and TXT
(human-readable) formats. Each scenario has its own subdirectory under
``transcripts/``, e.g. ``transcripts/cancel_appointment/``.
"""

import json
import os
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

TRANSCRIPTS_DIR = "transcripts"


def _scenario_dir(scenario_id: str) -> str:
    """Return transcripts subdirectory for this scenario (e.g. transcripts/cancel_appointment)."""
    return os.path.join(TRANSCRIPTS_DIR, scenario_id)


class TranscriptLogger:
    """
    Accumulates messages during a call and persists them on :meth:`save`.
    """

    def __init__(self, scenario_id: str, scenario_name: str = "") -> None:
        self.scenario_id = scenario_id
        self.scenario_name = scenario_name or scenario_id
        self.messages: list[dict] = []
        self.start_time = datetime.now()
        os.makedirs(_scenario_dir(scenario_id), exist_ok=True)

    def add_message(self, speaker: str, text: str) -> None:
        """
        Record a single utterance.

        Parameters
        ----------
        speaker : str
            ``"agent"`` for the Pretty Good AI system, ``"bot"`` for our patient bot.
        text : str
            What was said.
        """
        entry = {
            "speaker": speaker,
            "text": text,
            "timestamp": datetime.now().isoformat(),
        }
        self.messages.append(entry)
        label = "AI Agent (PrettyGoodAI)" if speaker == "agent" else "Patient Bot (GPT-4o-mini)"
        logger.info("[%s] %s", label, text)

    def save(self) -> str:
        """Write JSON + TXT transcript files.  Returns the JSON file path."""
        end_time = datetime.now()
        duration = (end_time - self.start_time).total_seconds()
        timestamp = self.start_time.strftime("%Y%m%d_%H%M%S")

        base = f"{timestamp}_{self.scenario_id}"
        scenario_path = _scenario_dir(self.scenario_id)
        json_path = os.path.join(scenario_path, f"{base}.json")
        txt_path = os.path.join(scenario_path, f"{base}.txt")

        # ── JSON ────────────────────────────────────────────────────────
        payload = {
            "scenario_id": self.scenario_id,
            "scenario_name": self.scenario_name,
            "start_time": self.start_time.isoformat(),
            "end_time": end_time.isoformat(),
            "duration_seconds": round(duration, 1),
            "message_count": len(self.messages),
            "messages": self.messages,
        }
        with open(json_path, "w") as f:
            json.dump(payload, f, indent=2)

        # ── Human-readable TXT ──────────────────────────────────────────
        with open(txt_path, "w") as f:
            f.write(f"Call Transcript — {self.scenario_name}\n")
            f.write(f"Date     : {self.start_time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"Duration : {duration:.1f}s\n")
            f.write(f"Scenario : {self.scenario_id}\n")
            f.write("=" * 64 + "\n\n")
            for msg in self.messages:
                label = "AI Agent (PrettyGoodAI)  " if msg["speaker"] == "agent" else "Patient Bot (GPT-4o-mini)"
                f.write(f"[{label}]: {msg['text']}\n\n")

        logger.info(
            "Transcript saved → %s (%d messages, %.1fs)",
            json_path,
            len(self.messages),
            duration,
        )
        return json_path
