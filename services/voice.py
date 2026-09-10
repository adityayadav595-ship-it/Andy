from __future__ import annotations

import httpx

from config import TTS_API_KEY, TTS_API_URL


async def synthesize_voice(text: str) -> bytes | None:
    """Get OGG/Opus bytes from a user-controlled original-voice TTS bridge."""
    if not TTS_API_URL:
        return None
    headers = {"X-API-Key": TTS_API_KEY} if TTS_API_KEY else {}
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(
                f"{TTS_API_URL}/synthesize",
                json={"text": text, "voice": "ultron_original", "format": "ogg_opus"},
                headers=headers,
            )
            response.raise_for_status()
            return response.content
    except httpx.HTTPError:
        return None
