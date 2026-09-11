from __future__ import annotations

import asyncio
import logging
from io import BytesIO

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes, MessageHandler, filters

from config import ADMIN_IDS, ALERT_SCAN_SECONDS, BOT_TOKEN, SCAN_PAIR_LIMIT, VOICE_REPLY_MODE
from services.chat import reply_to_chat
from services.market_data import MarketDataUnavailable, fetch_candles
from services.pairs import active_pairs, pair_by_symbol
from services.signal_engine import Analysis, analyse
from services.storage import add_watch, alert_subscriptions, ensure_user, get_watchlist, remove_watch, set_alerts
from services.voice import synthesize_voice

logging.basicConfig(format="%(asctime)s %(levelname)s %(name)s %(message)s", level=logging.INFO)
log = logging.getLogger(__name__)
last_alert: dict[tuple[int, str], str] = {}

WELCOME = """⚙️ *ULTRON POWERPLAY online*

I read only fresh configured candle data. I filter trend → zone → candle → timing → risk, and I block unclear/volatile conditions.

No guaranteed calls. No martingale. No forced entry."""


def main_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🏏 Powerplay scan", callback_data="scan"), InlineKeyboardButton("📌 Pairs", callback_data="pairs")],
        [InlineKeyboardButton("🔔 Alerts", callback_data="alerts"), InlineKeyboardButton("🛡 Rules", callback_data="rules")],
        [InlineKeyboardButton("ℹ️ Help", callback_data="help")],
    ])


def format_analysis(label: str, analysis: Analysis, source: str) -> str:
    reasons = "\n".join(f"• {reason}" for reason in analysis.reasons)
    return (
        f"⚙️ *ULTRON — {label}*\n\n"
        f"Market state: *{analysis.market_state}*\n"
        f"Filter quality: *{analysis.quality}*\n"
        f"Call: *{analysis.label}*\n\n{reasons}\n\n"
        f"⚠️ {analysis.caution}\n"
        f"Data: `{source}` | 1-minute candles"
    )


def user_id(update: Update) -> int:
    return update.effective_chat.id


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    ensure_user(user_id(update))
    await update.effective_message.reply_text(WELCOME, parse_mode="Markdown", reply_markup=main_keyboard())


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.effective_message.reply_text(
        "*ULTRON commands*\n"
        "`/pairs` — active instruments\n"
        "`/signal EURUSD_OTC` — full market filter\n"
        "`/scan` — selected fresh observations\n"
        "`/watch EURUSD_OTC` — add pair to your watchlist\n"
        "`/unwatch EURUSD_OTC` — remove it\n"
        "`/watchlist` — view your list\n"
        "`/alerts on` or `/alerts off` — private watchlist alerts\n"
        "`/strategy` — Powerplay rules\n\n"
        "If data is stale, stretched or mixed, ULTRON returns NO TRADE.",
        parse_mode="Markdown",
    )


async def pairs_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    by_category: dict[str, list[str]] = {}
    for pair in active_pairs():
        by_category.setdefault(pair.category, []).append(pair.label)
    text = "*Configured active pairs*\n\n" + "\n".join(f"*{category}*\n" + " · ".join(labels) for category, labels in by_category.items())
    await update.effective_message.reply_text(text, parse_mode="Markdown")


async def signal_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.effective_message.reply_text("Usage: `/signal EURUSD_OTC`", parse_mode="Markdown")
        return
    pair = pair_by_symbol("".join(context.args))
    if not pair:
        await update.effective_message.reply_text("Pair not configured. Use /pairs for the exact name.")
        return
    await analyse_and_send(update, pair.symbol, pair.label)


async def analyse_and_send(update: Update, symbol: str, label: str) -> None:
    try:
        series = await fetch_candles(symbol)
        await update.effective_message.reply_text(format_analysis(label, analyse(series), series.source), parse_mode="Markdown")
    except MarketDataUnavailable as error:
        await update.effective_message.reply_text(f"⚙️ *ULTRON — NO TRADE*\n\n{error}\n\nData integrity comes before analysis.", parse_mode="Markdown")


async def scan_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    candidates = active_pairs()[:SCAN_PAIR_LIMIT]
    await update.effective_message.reply_text(f"🏏 Checking {len(candidates)} active pairs…")

    async def one(pair):
        try:
            return pair, analyse(await fetch_candles(pair.symbol))
        except MarketDataUnavailable:
            return pair, None

    results = await asyncio.gather(*(one(pair) for pair in candidates))
    selected = [(pair, analysis) for pair, analysis in results if analysis and analysis.quality in {"Selected", "Qualified"}]
    if not selected:
        await update.effective_message.reply_text("🏏 *Strategic timeout — NO TRADE*\nNo selected setup is fresh right now. Patience protects capital.", parse_mode="Markdown")
        return
    text = "🏏 *ULTRON POWERPLAY — selected observations*\n\n" + "\n".join(
        f"• *{pair.label}*: {analysis.label.replace('POWERPLAY — ', '')} — {analysis.quality}" for pair, analysis in selected
    ) + "\n\nUse `/signal PAIR` for structure and reasons. This is analysis, not a trade instruction."
    await update.effective_message.reply_text(text, parse_mode="Markdown")


async def watch_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    pair = pair_by_symbol("".join(context.args)) if context.args else None
    if not pair:
        await update.effective_message.reply_text("Usage: `/watch EURUSD_OTC`", parse_mode="Markdown")
        return
    add_watch(user_id(update), pair.symbol)
    await update.effective_message.reply_text(f"🔔 {pair.label} added. Use `/alerts on` to receive selected observations.", parse_mode="Markdown")


async def unwatch_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    pair = pair_by_symbol("".join(context.args)) if context.args else None
    if not pair:
        await update.effective_message.reply_text("Usage: `/unwatch EURUSD_OTC`", parse_mode="Markdown")
        return
    remove_watch(user_id(update), pair.symbol)
    await update.effective_message.reply_text(f"{pair.label} removed from your watchlist.")


async def watchlist_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    symbols = get_watchlist(user_id(update))
    await update.effective_message.reply_text("🔔 *Your watchlist*\n\n" + ("\n".join(f"• `{symbol}`" for symbol in symbols) if symbols else "Empty. Add one with `/watch EURUSD_OTC`"), parse_mode="Markdown")


async def alerts_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    setting = context.args[0].lower() if context.args else ""
    if setting not in {"on", "off"}:
        await update.effective_message.reply_text("Usage: `/alerts on` or `/alerts off`", parse_mode="Markdown")
        return
    set_alerts(user_id(update), setting == "on")
    await update.effective_message.reply_text("🔔 Alerts enabled for your watchlist." if setting == "on" else "🔕 Alerts paused.")


async def strategy_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.effective_message.reply_text(
        "🏏 *ADI POWERPLAY protocol*\n\n"
        "1. Structure: UP, DOWN, RANGE or TRANSITION\n"
        "2. Zone: do not chase stretched price\n"
        "3. Candle: momentum or rejection confirmation\n"
        "4. Timing: no late/FOMO entries\n"
        "5. Risk: fixed small risk; stop after 2 losses\n\n"
        "*Wicket Alert* = unstable/no-trade condition.", parse_mode="Markdown")


async def market_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await strategy_command(update, context)


async def reload_pairs(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user.id not in ADMIN_IDS:
        await update.effective_message.reply_text("Admin-only command.")
        return
    await update.effective_message.reply_text(f"Reload complete: {len(active_pairs())} active pairs configured.")


async def alert_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    for chat_id, symbols in alert_subscriptions().items():
        for symbol in symbols:
            pair = pair_by_symbol(symbol)
            if not pair:
                continue
            try:
                series = await fetch_candles(pair.symbol)
                analysis = analyse(series)
            except MarketDataUnavailable:
                continue
            key, signature = (chat_id, symbol), f"{analysis.label}:{series.candles[-1].timestamp}"
            if analysis.quality not in {"Selected", "Qualified"} or last_alert.get(key) == signature:
                continue
            last_alert[key] = signature
            try:
                await context.bot.send_message(chat_id, format_analysis(pair.label, analysis, series.source), parse_mode="Markdown")
            except Exception:
                log.exception("Could not deliver alert to %s", chat_id)


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    handlers = {"pairs": pairs_command, "scan": scan_command, "rules": strategy_command, "help": help_command}
    if query.data == "alerts":
        await query.message.reply_text("Enable private alerts with `/alerts on`, then add a pair using `/watch EURUSD_OTC`.", parse_mode="Markdown")
    else:
        await handlers[query.data](update, context)


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
    for command, handler in [("start", start), ("help", help_command), ("pairs", pairs_command), ("signal", signal_command), ("scan", scan_command), ("watch", watch_command), ("unwatch", unwatch_command), ("watchlist", watchlist_command), ("alerts", alerts_command), ("strategy", strategy_command), ("market", market_command), ("reloadpairs", reload_pairs)]:
        application.add_handler(CommandHandler(command, handler))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, chat_handler))
    application.job_queue.run_repeating(alert_job, interval=ALERT_SCAN_SECONDS, first=20, name="watchlist-alerts")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    run()
