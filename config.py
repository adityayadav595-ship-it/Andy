from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).resolve().parent
PAIRS_FILE = ROOT / "data" / "pairs.json"
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
MARKET_DATA_API_URL = os.getenv("MARKET_DATA_API_URL", "").rstrip("/")
MARKET_DATA_API_KEY = os.getenv("MARKET_DATA_API_KEY", "").strip()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1-mini").strip()
VOICE_REPLY_MODE = os.getenv("VOICE_REPLY_MODE", "text").strip().lower()
TTS_API_URL = os.getenv("TTS_API_URL", "").rstrip("/")
TTS_API_KEY = os.getenv("TTS_API_KEY", "").strip()
ADMIN_IDS = {int(value) for value in os.getenv("ADMIN_TELEGRAM_IDS", "").split(",") if value.strip().isdigit()}
MAX_CANDLE_AGE_SECONDS = 90
SCAN_PAIR_LIMIT = 20
