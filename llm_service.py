"""
OpenAI LLM service — generates patient responses given conversation context.
"""

import logging
from openai import AsyncOpenAI
from config import OPENAI_API_KEY, OPENAI_MODEL

logger = logging.getLogger(__name__)

_client: AsyncOpenAI | None = None


def _get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(api_key=OPENAI_API_KEY)
    return _client


async def get_patient_response(
    conversation_history: list[dict],
    system_prompt: str,
) -> str:
    """
    Generate the next patient utterance.

    Parameters
    ----------
    conversation_history : list[dict]
        Messages so far. "user" role = the AI agent; "assistant" role = our bot.
    system_prompt : str
        The scenario-specific persona instructions.

    Returns
    -------
    str
        The patient's next line of dialogue.  May contain ``[END_CALL]``
        to signal the bot should hang up after speaking.
    """
    client = _get_client()

    messages = [{"role": "system", "content": system_prompt}]
    messages.extend(conversation_history)

    try:
        response = await client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=messages,
            max_tokens=200,
            temperature=0.8,
        )
        text = response.choices[0].message.content or ""
        logger.debug("LLM response: %s", text)
        return text.strip()

    except Exception:
        logger.exception("LLM request failed")
        return "Sorry, could you repeat that?"
