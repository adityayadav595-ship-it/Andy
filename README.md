# ULTRON · Quotex Market Assistant

A GitHub-ready Telegram bot with an original, cinematic **ULTRON-style** personality. It answers trading questions, lists configured Quotex instruments, scans supported pairs, and returns a transparent technical-analysis summary.

> **Important:** This bot is an educational market-analysis tool, not financial advice. It must never promise accuracy, profits, recovery, or "sure-shot" trades. It returns **NO TRADE** whenever its data is missing, stale, or the setup is weak.

## What it does

- `/pairs` — browse all configured Normal, OTC, Crypto, Commodity and Index pairs
- `/signal <pair>` — one-pair analysis using EMA 9/21, RSI 14, candle momentum and volatility
- `/scan` — scans configured active pairs and lists only strong, fresh setups
- `/market` — market-status overview
- `/help` — command guide
- Natural-language chat — concise, original ULTRON-style trading education replies
- Optional voice notes via a user-controlled TTS bridge using an original dark robotic voice
- Inline buttons for categories, pair selection, scan and market status

## How signal data works

Quotex OTC prices are proprietary. To avoid fabricated signals, this repo does **not** automate a Quotex login or pretend to have its data. Instead, it expects a trusted candle-data bridge that you control (for example, an approved data provider or your own read-only bridge).

Set `MARKET_DATA_API_URL` to an endpoint that accepts:

```text
GET /candles?symbol=EURUSD_OTC&interval=60&limit=80
```

and responds with:

```json
{
  "symbol": "EURUSD_OTC",
  "source": "Your approved feed",
  "candles": [
    {"timestamp": 1760000000, "open": 1.1, "high": 1.11, "low": 1.09, "close": 1.105}
  ]
}
```

Each request needs at least 35 one-minute candles. Freshness must be under 90 seconds. If either requirement fails, the bot replies **NO TRADE — data unavailable/stale**.

## Setup

1. Create a Telegram bot with **@BotFather** and copy its token.
2. Copy `.env.example` to `.env` and fill the values locally or in your deployment environment.
3. Update `data/pairs.json` with the exact instrument names currently visible in your Quotex account. Keep `active: true` only for instruments your data bridge supports.
4. Install and run:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

## Environment variables

| Variable | Required | Purpose |
| --- | --- | --- |
| `TELEGRAM_BOT_TOKEN` | Yes | BotFather token; keep it secret |
| `MARKET_DATA_API_URL` | Yes for signals | Your candle-data bridge endpoint |
| `MARKET_DATA_API_KEY` | Optional | Sent as `X-API-Key` to the bridge |
| `OPENAI_API_KEY` | Optional | Enables richer natural-language replies |
| `OPENAI_MODEL` | Optional | Defaults to `gpt-4.1-mini` |
| `VOICE_REPLY_MODE` | Optional | Set to `voice` to send TTS voice notes; defaults to text |
| `TTS_API_URL` / `TTS_API_KEY` | Required for voice mode | Your original-voice TTS bridge; must return OGG/Opus audio |
| `ADMIN_TELEGRAM_IDS` | Optional | Comma-separated IDs allowed to use `/reloadpairs` |

Never commit `.env`, bot tokens, data-provider keys or user chats to GitHub. Configure them as repository/deployment secrets.

### Voice bridge contract

For voice mode, your bridge should accept `POST /synthesize` with `{ "text": "…", "voice": "ultron_original", "format": "ogg_opus" }` and return audio/ogg bytes. Use an original synthetic voice or one you have rights to; do not use an actor or film-character voice clone.

## Deployment

GitHub stores the project. A Telegram bot needs an always-on runtime, so deploy this repo to Render, Railway, Fly.io, or a VPS. `render.yaml` and `Dockerfile` are included for a worker deployment. Add the environment variables above in the host dashboard; do not paste secrets into source code.

## Safety behaviour

- No martingale, account-recovery or guaranteed-return advice
- Risk reminders: small fixed risk, daily loss limit, pause after consecutive losses
- No analysis when data is stale, illiquid or contradictory
- Every direction is presented as a setup observation, never an instruction to trade
