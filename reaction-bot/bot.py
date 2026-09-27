"""Channel reaction automation. Configure credentials through environment variables."""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import random
import re
import signal
from collections import deque
from contextlib import AsyncExitStack
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from telegram import Bot, ReactionTypeEmoji
from telegram.error import Conflict, NetworkError, RetryAfter, TelegramError

LOG = logging.getLogger("adi_bot")
EMOJI_WEIGHTS = {"❤️": 40, "🔥": 25, "👍": 15, "🏆": 10, "💯": 10}
INITIAL_DELAY = 60
SINGLE_POST_DELAY = 120
MULTI_POST_DELAY = 30
MAX_CONCURRENT_REACTIONS = 5
MAX_ACTIVE_POSTS = 100
TOKEN_PATTERN = re.compile(r"\d{5,}:[A-Za-z0-9_-]{20,}")


class ConfigError(ValueError):
    pass


@dataclass(frozen=True)
class Config:
    tokens: tuple[str, ...] = field(repr=False)
    channels: tuple[int | str, ...]


def load_config(environ=None):
    env = os.environ if environ is None else environ
    tokens = tuple(dict.fromkeys(filter(None, re.split(r"[\s,]+", env.get("BOT_TOKENS", "").strip()))))
    if not tokens:
        raise ConfigError("Set the BOT_TOKENS secret: one new bot token per line.")
    if any(not TOKEN_PATTERN.fullmatch(token) for token in tokens):
        raise ConfigError("BOT_TOKENS has an invalid entry. Use bare tokens, without quotes or brackets.")
    raw_channels = re.split(r"[\s,]+", env.get("TARGET_CHANNEL_IDS", "").strip())
    channels = []
    for item in filter(None, raw_channels):
        if re.fullmatch(r"-\d+", item):
            channels.append(int(item))
        elif re.fullmatch(r"@[A-Za-z0-9_]+", item):
            channels.append(item)
        else:
            raise ConfigError("TARGET_CHANNEL_IDS needs a negative channel ID or @channelusername, not an invite link.")
    if not channels:
        raise ConfigError("Set TARGET_CHANNEL_IDS to your new channel ID or @channelusername.")
    return Config(tokens, tuple(dict.fromkeys(channels)))


class RedactingFormatter(logging.Formatter):
    def format(self, record):
        return TOKEN_PATTERN.sub("[REDACTED_TOKEN]", super().format(record))


def setup_logging():
    handler = logging.StreamHandler()
    handler.setFormatter(RedactingFormatter("%(asctime)s | %(levelname)s | %(message)s"))
    logging.basicConfig(level=logging.INFO, handlers=[handler], force=True)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


def retry_seconds(error):
    delay = error.retry_after
    return (delay.total_seconds() if isinstance(delay, timedelta) else float(delay)) + 1


def allowed_weights(chat):
    available = getattr(chat, "available_reactions", None)
    if available is None:
        return dict(EMOJI_WEIGHTS)
    allowed = {reaction.emoji for reaction in available if isinstance(reaction, ReactionTypeEmoji)}
    return {emoji: weight for emoji, weight in EMOJI_WEIGHTS.items() if emoji in allowed}


class ReactionRunner:
    def __init__(self, bots_by_chat, weights_by_chat, started_at=None):
        self.bots_by_chat = bots_by_chat
        self.weights_by_chat = weights_by_chat
        self.started_at = started_at or datetime.now(timezone.utc)
        self.semaphore = asyncio.Semaphore(MAX_CONCURRENT_REACTIONS)
        self.bot_locks = {bot.id: asyncio.Lock() for bots in bots_by_chat.values() for bot in bots}
        self.seen = set()
        self.seen_order = deque()
        self.tasks = set()

    def accept_post(self, post):
        if post is None or post.chat_id not in self.bots_by_chat or post.date < self.started_at:
            return False
        # A Telegram album shares reactions: schedule once, not for every album item.
        key = (post.chat_id, post.media_group_id or post.message_id)
        if key in self.seen:
            return False
        if len(self.tasks) >= MAX_ACTIVE_POSTS:
            LOG.warning("Active-post limit reached; this post was skipped.")
            return False
        if len(self.seen_order) >= 10000:
            self.seen.discard(self.seen_order.popleft())
        self.seen.add(key)
        self.seen_order.append(key)
        task = asyncio.create_task(self.react_to_post(post.chat_id, post.message_id))
        self.tasks.add(task)
        task.add_done_callback(self.finished)
        return True

    def finished(self, task):
        self.tasks.discard(task)
        if not task.cancelled() and task.exception() is not None:
            LOG.error("Post processing failed: %s", type(task.exception()).__name__)

    async def react_with_bot(self, bot, chat_id, message_id, emoji):
        # A cooldown applies to this bot across all posts, not just one task.
        async with self.bot_locks[bot.id]:
            for attempt in range(3):
                try:
                    async with self.semaphore:
                        await bot.set_message_reaction(
                            chat_id=chat_id,
                            message_id=message_id,
                            reaction=[ReactionTypeEmoji(emoji=emoji)],
                        )
                    LOG.info("Reaction sent | @%s | %s | post=%s", bot.username, emoji, message_id)
                    return True
                except RetryAfter as error:
                    if attempt == 2:
                        LOG.warning("Reaction skipped after repeated rate limits.")
                        return False
                    delay = retry_seconds(error)
                    LOG.warning("Telegram rate limit; waiting %.1f seconds.", delay)
                    await asyncio.sleep(delay)
                except TelegramError as error:
                    LOG.warning("Reaction not sent (%s); check bot access and allowed reactions.", type(error).__name__)
                    return False
        return False

    async def react_to_post(self, chat_id, message_id):
        LOG.info("New post=%s; reactions start after %s seconds.", message_id, INITIAL_DELAY)
        await asyncio.sleep(INITIAL_DELAY)
        bots = list(self.bots_by_chat[chat_id])
        random.shuffle(bots)
        weights = self.weights_by_chat[chat_id]
        for index, bot in enumerate(bots):
            emoji = random.choices(list(weights), weights=list(weights.values()), k=1)[0]
            await self.react_with_bot(bot, chat_id, message_id, emoji)
            if index < len(bots) - 1:
                delay = MULTI_POST_DELAY if len(self.tasks) > 1 else SINGLE_POST_DELAY
                await asyncio.sleep(delay)
        LOG.info("Finished post=%s.", message_id)

    async def close(self):
        tasks = list(self.tasks)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


async def resolve_channels(listener, bots, channels):
    bots_by_chat = {}
    weights_by_chat = {}
    for target in channels:
        chat = await listener.get_chat(target)
        if chat.type != "channel":
            raise ConfigError("A configured target is not a Telegram channel.")
        weights = allowed_weights(chat)
        if not weights:
            raise ConfigError("Enable at least one configured emoji reaction in the target channel.")
        members = []
        for bot in bots:
            try:
                member = await bot.get_chat_member(chat.id, bot.id)
                if member.status in {"member", "administrator", "creator"}:
                    members.append(bot)
            except TelegramError:
                LOG.warning("A bot cannot access a configured channel; skipped for that channel.")
        if listener not in members:
            raise ConfigError("Add the first valid bot to every target channel so it can receive new posts.")
        bots_by_chat[chat.id] = members
        weights_by_chat[chat.id] = weights
        LOG.info("Channel ready: %s accessible bot(s).", len(members))
    return bots_by_chat, weights_by_chat


async def poll(listener, runner):
    offset = None
    while True:
        try:
            updates = await listener.get_updates(
                offset=offset, timeout=20, allowed_updates=["channel_post"],
                read_timeout=30, connect_timeout=15,
            )
        except Conflict as error:
            raise ConfigError("The listener bot is already running elsewhere. Stop that instance first.") from error
        except RetryAfter as error:
            await asyncio.sleep(retry_seconds(error))
            continue
        except NetworkError:
            LOG.warning("Temporary connection problem; retrying in 5 seconds.")
            await asyncio.sleep(5)
            continue
        for update in updates:
            offset = update.update_id + 1
            runner.accept_post(update.channel_post)


async def run(config, run_minutes):
    # All bots are initialized, used and closed on ONE event loop.
    async with AsyncExitStack() as stack:
        bots = []
        for index, token in enumerate(config.tokens, 1):
            try:
                bot = await stack.enter_async_context(Bot(token=token))
                bots.append(bot)
                LOG.info("Bot %s loaded: @%s", index, bot.username)
            except TelegramError as error:
                LOG.warning("Bot %s unavailable (%s); skipping.", index, type(error).__name__)
        if not bots:
            raise ConfigError("No working bot tokens. Check the BOT_TOKENS secret.")
        listener = bots[0]
        webhook = await listener.get_webhook_info()
        if webhook.url:
            raise ConfigError("This bot has an existing webhook. It was NOT removed. Use a dedicated bot or intentionally reconfigure it first.")
        by_chat, weights = await resolve_channels(listener, bots, config.channels)
        runner = ReactionRunner(by_chat, weights)
        stop = asyncio.Event()
        loop = asyncio.get_running_loop()
        registered_signals = []
        for signum in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(signum, stop.set)
                registered_signals.append(signum)
            except (NotImplementedError, RuntimeError):
                pass
        poll_task = asyncio.create_task(poll(listener, runner))
        stop_task = asyncio.create_task(stop.wait())
        LOG.info("READY - publish a NEW channel post now. Older posts are ignored.")
        if run_minutes:
            LOG.info("Manual test will stop after %s minutes.", run_minutes)
        try:
            done, _ = await asyncio.wait(
                [poll_task, stop_task],
                timeout=run_minutes * 60 if run_minutes else None,
                return_when=asyncio.FIRST_COMPLETED,
            )
            if poll_task in done:
                await poll_task
        finally:
            for task in (poll_task, stop_task):
                task.cancel()
            await asyncio.gather(poll_task, stop_task, return_exceptions=True)
            await runner.close()
            for signum in registered_signals:
                loop.remove_signal_handler(signum)
            LOG.info("Stopped. Unfinished reactions are cancelled, not resumed next run.")


def main():
    setup_logging()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check-config", action="store_true", help="Validate config without contacting Telegram.")
    parser.add_argument("--run-minutes", type=int, default=0, help="Stop after N minutes; 0 means until stopped on your own machine/server.")
    args = parser.parse_args()
    try:
        if args.run_minutes < 0:
            raise ConfigError("--run-minutes cannot be negative.")
        config = load_config()
        if args.check_config:
            LOG.info("Config format OK: %s token(s), %s channel(s). No Telegram requests made.", len(config.tokens), len(config.channels))
            return 0
        asyncio.run(run(config, args.run_minutes))
    except ConfigError as error:
        LOG.error("Configuration: %s", error)
        return 1
    except TelegramError as error:
        LOG.error("Telegram request failed (%s). Check channel access, tokens and network.", type(error).__name__)
        return 1
    except KeyboardInterrupt:
        LOG.info("Stopped by user.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
