from __future__ import annotations

import asyncio
from io import BytesIO
import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes, MessageHandler, filters

from config import ADMIN_IDS, BOT_TOKEN, SCAN_PAIR_LIMIT, VOICE_REPLY_MODE
from services.chat import reply_to_chat
from services.market_data import MarketDataUnavailable, fetch_candles
from services.pairs import active_pairs, pair_by_symbol
from services.signal_engine import Analysis, analyse
from services.voice import synthesize_voice

logging.basicConfig(format="%(asctime)s %(levelname)s %(name)s %(message)s", level=logging.INFO)

WELCOME = """⚙️ *ULTRON Market Assistant online*

I analyse only fresh, configured candle data. No guaranteed calls, no martingale and no fake certainty.

Choose an action below or type `/signal EURUSD_OTC`."""


def main_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 Scan market", callback_data="scan"), InlineKeyboardButton("📌 Pairs", callback_data="pairs")],
        [InlineKeyboardButton("🛡 Market rules", callback_data="rules"), InlineKeyboardButton("ℹ️ Help", callback_data="help")],
    ])


def format_analysis(label: str, analysis: Analysis, source: str) -> str:
    reasons = "\n".join(f"• {reason}" for reason in analysis.reasons)
    return (
        f"⚙️ *ULTRON Analysis — {label}*\n\n"
        f"Status: *{analysis.label}*\n"
        f"Setup strength: *{analysis.confidence}/100*\n\n"
        f"{reasons}\n\n"
        f"⚠️ {analysis.caution}\n"
        f"Data: `{source}` | 1-minute candles"
    )


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.effective_message.reply_text(WELCOME, parse_mode="Markdown", reply_markup=main_keyboard())


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.effective_message.reply_text(
        "*Commands*\n"
        "`/pairs` — configured active instruments\n"
        "`/signal EURUSD_OTC` — fresh technical observation\n"
        "`/scan` — scan active instruments\n"
        "`/market` — safety rules\n\n"
        "Use the exact pair label shown in /pairs. If data is stale or missing, ULTRON will return NO TRADE.",
        parse_mode="Markdown",
    )


async def pairs_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    pairs = active_pairs()
    by_category: dict[str, list[str]] = {}
    for pair in pairs:
        by_category.setdefault(pair.category, []).append(pair.label)
    text = "*Configured active pairs*\n\n" + "\n".join(
        f"*{category}*\n" + " · ".join(labels) for category, labels in by_category.items()
    )
    await update.effective_message.reply_text(text, parse_mode="Markdown")


async def signal_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.effective_message.reply_text("Usage: `/signal EURUSD_OTC`\nCheck `/pairs` for configured names.", parse_mode="Markdown")
        return
    pair = pair_by_symbol("".join(context.args))
    if not pair:
        await update.effective_message.reply_text("That pair is not configured or active. Use /pairs for the exact name.")
        return
    await analyse_and_send(update, pair.symbol, pair.label)


async def analyse_and_send(update: Update, symbol: str, label: str) -> None:
    try:
        series = await fetch_candles(symbol)
        analysis = analyse(series)
        await update.effective_message.reply_text(format_analysis(label, analysis, series.source), parse_mode="Markdown")
    except MarketDataUnavailable as error:
        await update.effective_message.reply_text(f"⚙️ *ULTRON — NO TRADE*\n\n{error}\n\nData integrity comes before any analysis.", parse_mode="Markdown")


async def scan_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    candidates = active_pairs()[:SCAN_PAIR_LIMIT]
    await update.effective_message.reply_text(f"⚙️ Scanning {len(candidates)} configured pairs…")

    async def one(pair):
        try:
            return pair, analyse(await fetch_candles(pair.symbol))
        except MarketDataUnavailable:
            return pair, None

    results = await asyncio.gather(*(one(pair) for pair in candidates))
    setups = [(pair, analysis) for pair, analysis in results if analysis and analysis.label != "NO TRADE"]
    if not setups:
        await update.effective_message.reply_text("⚙️ *Scan complete — NO TRADE*\nNo strong, fresh setup found. Waiting is a valid decision.", parse_mode="Markdown")
        return
    text = "⚙️ *ULTRON Scan — fresh observations*\n\n" + "\n".join(
        f"• *{pair.label}*: {analysis.label} ({analysis.confidence}/100)" for pair, analysis in setups
    ) + "\n\nUse `/signal PAIR` to see reasons. Observations only—not trade instructions."
    await update.effective_message.reply_text(text, parse_mode="Markdown")


async def market_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.effective_message.reply_text(
        "🛡 *ULTRON market protocol*\n\n"
        "• Fixed small risk per attempt\n• Stop after two consecutive losses\n• No martingale or recovery chasing\n• Skip volatile, stale or mixed setups\n• A signal is analysis—not certainty\n\nCapital protection is the first objective.",
        parse_mode="Markdown",
    )


async def reload_pairs(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id if update.effective_user else 0
    if user_id not in ADMIN_IDS:
        await update.effective_message.reply_text("Admin-only command.")
        return
    await update.effective_message.reply_text(f"Reload complete: {len(active_pairs())} active pairs configured.")


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    if query.data == "pairs":
        await pairs_command(update, context)
    elif query.data == "scan":
        await scan_command(update, context)
    elif query.data == "rules":
        await market_command(update, context)
    else:
        await help_command(update, context)


async def chat_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    answer = await reply_to_chat(update.effective_message.text)
    if VOICE_REPLY_MODE == "voice":
        audio = await synthesize_voice(answer)
        if audio:
            voice = BytesIO(audio)
            voice.name = "ultron.ogg"
            await update.effective_message.reply_voice(voice=voice, caption=answer)
            return
    await update.effective_message.reply_text(answer)


def run() -> None:
    if not BOT_TOKEN:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is missing. Add it to .env or deployment secrets.")
    application = Application.builder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("pairs", pairs_command))
    application.add_handler(CommandHandler("signal", signal_command))
    application.add_handler(CommandHandler("scan", scan_command))
    application.add_handler(CommandHandler("market", market_command))
    application.add_handler(CommandHandler("reloadpairs", reload_pairs))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, chat_handler))
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    run()
