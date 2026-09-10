from __future__ import annotations

from config import OPENAI_API_KEY, OPENAI_MODEL

SYSTEM_PROMPT = """You are ULTRON, an original, cinematic but non-infringing Telegram market assistant. Speak in concise, calm Hinglish. Teach rather than command. Never promise profits, signal accuracy, recovery, or certainty. Never encourage martingale, revenge trading, borrowing, or high-risk behaviour. For individual trade questions, say that only fresh data and the /signal command can provide a technical observation, and users must make their own decision. Keep replies under 110 words."""


async def reply_to_chat(message: str) -> str:
    if not OPENAI_API_KEY:
        return (
            "ULTRON online. Main market concepts, risk rules aur bot commands explain kar sakta hoon. "
            "Fresh technical observation ke liye /signal PAIR use karo—for example: /signal EURUSD_OTC."
        )
    try:
        from openai import AsyncOpenAI
        client = AsyncOpenAI(api_key=OPENAI_API_KEY)
        response = await client.responses.create(
            model=OPENAI_MODEL,
            instructions=SYSTEM_PROMPT,
            input=message,
            max_output_tokens=220,
        )
        return response.output_text.strip()
    except Exception:
        return "ULTRON communication core is temporarily unavailable. Try /help or /signal PAIR."
