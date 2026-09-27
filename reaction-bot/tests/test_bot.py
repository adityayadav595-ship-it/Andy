import asyncio
import logging
import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from telegram import ReactionTypeEmoji
from telegram.error import Conflict, RetryAfter, TelegramError

import bot


FAKE_TOKEN = "123456789:" + "A" * 35
SECOND_FAKE_TOKEN = "987654321:" + "B" * 35
BASE_ENV = {"BOT_TOKENS": FAKE_TOKEN, "TARGET_CHANNEL_IDS": "@my_test_channel"}


class ConfigTests(unittest.TestCase):
    def test_newline_and_comma_tokens_deduplicate(self):
        config = bot.load_config({
            "BOT_TOKENS": FAKE_TOKEN + "\n" + SECOND_FAKE_TOKEN + "," + FAKE_TOKEN,
            "TARGET_CHANNEL_IDS": "@my_test_channel\n-1001234567890",
        })
        self.assertEqual(len(config.tokens), 2)
        self.assertEqual(config.channels, ("@my_test_channel", -1001234567890))
        self.assertNotIn(FAKE_TOKEN, repr(config))

    def test_missing_tokens(self):
        with self.assertRaisesRegex(bot.ConfigError, "BOT_TOKENS"):
            bot.load_config({})

    def test_invalid_tokens(self):
        with self.assertRaisesRegex(bot.ConfigError, "invalid entry"):
            bot.load_config({**BASE_ENV, "BOT_TOKENS": "not_a_token"})

    def test_missing_channel(self):
        with self.assertRaisesRegex(bot.ConfigError, "TARGET_CHANNEL_IDS"):
            bot.load_config({"BOT_TOKENS": FAKE_TOKEN})

    def test_reject_invite_link(self):
        with self.assertRaisesRegex(bot.ConfigError, "invite link"):
            bot.load_config({**BASE_ENV, "TARGET_CHANNEL_IDS": "https://t.me/+example"})

    def test_tokens_redacted_in_logs(self):
        formatter = bot.RedactingFormatter("%(message)s")
        record = logging.LogRecord("test", logging.ERROR, "", 0, "url /bot%s/getMe", (FAKE_TOKEN,), None)
        output = formatter.format(record)
        self.assertNotIn(FAKE_TOKEN, output)
        self.assertIn("[REDACTED_TOKEN]", output)

    def test_retry_seconds_accepts_numeric_and_timedelta(self):
        self.assertEqual(bot.retry_seconds(SimpleNamespace(retry_after=2)), 3)
        self.assertEqual(bot.retry_seconds(SimpleNamespace(retry_after=timedelta(seconds=8))), 9)

    def test_filter_supported_reactions(self):
        chat = SimpleNamespace(available_reactions=[ReactionTypeEmoji("❤️")])
        self.assertEqual(bot.allowed_weights(chat), {"❤️": 40})
        self.assertEqual(bot.allowed_weights(SimpleNamespace(available_reactions=[])), {})
        self.assertEqual(bot.allowed_weights(SimpleNamespace(available_reactions=None)), bot.EMOJI_WEIGHTS)


def fake_bot(number=1):
    return SimpleNamespace(
        id=number,
        username=f"test_bot_{number}",
        set_message_reaction=AsyncMock(return_value=True),
        get_chat_member=AsyncMock(return_value=SimpleNamespace(status="administrator")),
    )


class RunnerTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.first = fake_bot(1)
        self.second = fake_bot(2)
        self.runner = bot.ReactionRunner({-100: [self.first, self.second]}, {-100: {"❤️": 40}})

    async def asyncTearDown(self):
        await self.runner.close()

    def post(self, message_id=10, chat_id=-100, media_group_id=None, age=1):
        return SimpleNamespace(
            message_id=message_id, chat_id=chat_id, media_group_id=media_group_id,
            date=self.runner.started_at + timedelta(seconds=age),
        )

    async def test_single_post_ten_second_delays(self):
        with patch("bot.asyncio.sleep", new_callable=AsyncMock) as sleep:
            await self.runner.react_to_post(-100, 10)
        self.assertEqual([call.args[0] for call in sleep.await_args_list], [10, 10])
        self.first.set_message_reaction.assert_awaited_once()
        self.second.set_message_reaction.assert_awaited_once()
        self.assertEqual(self.first.set_message_reaction.await_args.kwargs["chat_id"], -100)

    async def test_multiple_post_ten_second_delays(self):
        # Multiple active posts keep the same ten-second interval per post.
        with patch.object(self.runner, "tasks", {"post_a", "post_b"}):
            with patch("bot.asyncio.sleep", new_callable=AsyncMock) as sleep:
                await self.runner.react_to_post(-100, 10)
        self.assertEqual([call.args[0] for call in sleep.await_args_list], [10, 10])

    async def test_duplicate_and_album_updates(self):
        self.assertTrue(self.runner.accept_post(self.post()))
        self.assertFalse(self.runner.accept_post(self.post()))
        self.assertTrue(self.runner.accept_post(self.post(20, media_group_id="album-1")))
        self.assertFalse(self.runner.accept_post(self.post(21, media_group_id="album-1")))
        self.assertEqual(len(self.runner.tasks), 2)

    async def test_old_and_other_channel_posts_ignored(self):
        self.assertFalse(self.runner.accept_post(None))
        self.assertFalse(self.runner.accept_post(self.post(chat_id=-200)))
        self.assertFalse(self.runner.accept_post(self.post(age=-10)))
        self.assertEqual(len(self.runner.tasks), 0)

    async def test_rate_limit_waits_and_retries(self):
        self.first.set_message_reaction.side_effect = [RetryAfter(2), True]
        with patch("bot.asyncio.sleep", new_callable=AsyncMock) as sleep:
            result = await self.runner.react_with_bot(self.first, -100, 10, "❤️")
        self.assertTrue(result)
        self.assertEqual(self.first.set_message_reaction.await_count, 2)
        sleep.assert_awaited_once_with(3.0)

    async def test_retries_are_bounded(self):
        self.first.set_message_reaction.side_effect = RetryAfter(2)
        with patch("bot.asyncio.sleep", new_callable=AsyncMock) as sleep:
            result = await self.runner.react_with_bot(self.first, -100, 10, "❤️")
        self.assertFalse(result)
        self.assertEqual(self.first.set_message_reaction.await_count, 3)
        self.assertEqual(sleep.await_count, 2)

    async def test_telegram_error_is_skipped(self):
        self.first.set_message_reaction.side_effect = TelegramError("mock forbidden")
        self.assertFalse(await self.runner.react_with_bot(self.first, -100, 10, "❤️"))
        self.first.set_message_reaction.assert_awaited_once()

    async def test_close_cancels_pending_reactions(self):
        self.runner.accept_post(self.post())
        await self.runner.close()
        self.assertEqual(len(self.runner.tasks), 0)
        self.first.set_message_reaction.assert_not_awaited()


class PollAndChannelTests(unittest.IsolatedAsyncioTestCase):
    async def test_poll_offset_and_filter(self):
        post = object()
        listener = SimpleNamespace(get_updates=AsyncMock(side_effect=[
            [SimpleNamespace(update_id=7, channel_post=post)], asyncio.CancelledError(),
        ]))
        runner = SimpleNamespace(accept_post=Mock())
        with self.assertRaises(asyncio.CancelledError):
            await bot.poll(listener, runner)
        calls = listener.get_updates.await_args_list
        self.assertIsNone(calls[0].kwargs["offset"])
        self.assertEqual(calls[1].kwargs["offset"], 8)
        self.assertEqual(calls[0].kwargs["allowed_updates"], ["channel_post"])
        runner.accept_post.assert_called_once_with(post)

    async def test_poll_conflict_fails_clearly(self):
        listener = SimpleNamespace(get_updates=AsyncMock(side_effect=Conflict("mock conflict")))
        with self.assertRaisesRegex(bot.ConfigError, "running elsewhere"):
            await bot.poll(listener, Mock())

    async def test_channel_resolution_skips_nonmember(self):
        listener = fake_bot(1)
        listener.get_chat = AsyncMock(return_value=SimpleNamespace(
            id=-100, type="channel", available_reactions=[ReactionTypeEmoji("🔥")],
        ))
        other = fake_bot(2)
        other.get_chat_member.return_value = SimpleNamespace(status="left")
        members, weights = await bot.resolve_channels(listener, [listener, other], ["@my_test_channel"])
        self.assertEqual(members[-100], [listener])
        self.assertEqual(weights[-100], {"🔥": 25})

    async def test_missing_listener_membership_fails(self):
        listener = fake_bot(1)
        listener.get_chat = AsyncMock(return_value=SimpleNamespace(id=-100, type="channel", available_reactions=None))
        listener.get_chat_member.return_value = SimpleNamespace(status="left")
        with self.assertRaisesRegex(bot.ConfigError, "first valid bot"):
            await bot.resolve_channels(listener, [listener], [-100])

    async def test_group_target_rejected(self):
        listener = fake_bot(1)
        listener.get_chat = AsyncMock(return_value=SimpleNamespace(id=-100, type="group"))
        with self.assertRaisesRegex(bot.ConfigError, "not a Telegram channel"):
            await bot.resolve_channels(listener, [listener], [-100])


class LifecycleTests(unittest.IsolatedAsyncioTestCase):
    def context_for(self, listener):
        context = AsyncMock()
        context.__aenter__.return_value = listener
        context.__aexit__.return_value = False
        return context

    async def test_run_initializes_and_closes_bots_on_timeout(self):
        listener = fake_bot(1)
        listener.get_webhook_info = AsyncMock(return_value=SimpleNamespace(url=""))
        listener.get_chat = AsyncMock(return_value=SimpleNamespace(id=-100, type="channel", available_reactions=None))
        async def wait_for_updates(**kwargs):
            await asyncio.Event().wait()
        listener.get_updates = AsyncMock(side_effect=wait_for_updates)
        context = self.context_for(listener)
        with patch("bot.Bot", return_value=context):
            await bot.run(bot.load_config(BASE_ENV), 0.0001)
        context.__aenter__.assert_awaited_once()
        context.__aexit__.assert_awaited_once()
        listener.get_updates.assert_awaited_once()
        listener.set_message_reaction.assert_not_awaited()

    async def test_existing_webhook_is_not_removed(self):
        listener = fake_bot(1)
        listener.get_webhook_info = AsyncMock(return_value=SimpleNamespace(url="https://example.invalid/webhook"))
        listener.delete_webhook = AsyncMock()
        context = self.context_for(listener)
        with patch("bot.Bot", return_value=context):
            with self.assertRaisesRegex(bot.ConfigError, "NOT removed"):
                await bot.run(bot.load_config(BASE_ENV), 1)
        listener.delete_webhook.assert_not_awaited()
        context.__aexit__.assert_awaited_once()

    async def test_no_working_tokens_fails_without_polling(self):
        context = AsyncMock()
        context.__aenter__.side_effect = TelegramError("mock invalid token")
        with patch("bot.Bot", return_value=context):
            with self.assertRaisesRegex(bot.ConfigError, "No working bot tokens"):
                await bot.run(bot.load_config(BASE_ENV), 1)


if __name__ == "__main__":
    unittest.main()
