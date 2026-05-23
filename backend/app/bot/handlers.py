import asyncio
from uuid import UUID

from telegram import Update
from telegram.ext import ContextTypes

from app.bot.conversation import conversation_state
from app.services import player_service, roster_service


async def handle_join_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handler for the "Join ✋" inline button press.

    Flow:
    1. Parse session_id from callback_data ("join:{session_id}").
    2. Look up the Telegram user in the players table.
       - Known player: add to roster immediately.
       - Unknown player: send a DM asking for their name and store pending state.
    3. Call query.answer() exactly once (Telegram requires this within 10 s).
    4. On success: trigger edit_session_message to refresh the group post.

    DB calls are wrapped in run_in_executor because supabase-py is synchronous.
    For this single-instance free-tier app the overhead is negligible, but
    keeping these off the event loop avoids potential latency spikes.
    """
    query = update.callback_query
    telegram_user_id = query.from_user.id
    session_id = UUID(query.data.split(":", 1)[1])

    loop = asyncio.get_running_loop()
    player = await loop.run_in_executor(
        None, player_service.get_by_telegram_id, telegram_user_id
    )

    if player is not None:
        try:
            _entry, is_waitlisted = await loop.run_in_executor(
                None, roster_service.add_player, session_id, telegram_user_id, player.name
            )
        except ValueError as exc:
            await query.answer(str(exc), show_alert=True)
            return

        if is_waitlisted:
            await query.answer(
                f"Session is full — you're on the waitlist, {player.name}! 🎯",
                show_alert=True,
            )
        else:
            await query.answer(f"You're in, {player.name}! See you on court 🏸", show_alert=True)

        # Lazy import avoids circular import at module load time.
        from app.bot.runner import bot_runner

        await bot_runner.edit_session_message(session_id)
    else:
        conversation_state.set_pending(telegram_user_id, session_id)
        try:
            await context.bot.send_message(
                chat_id=telegram_user_id,
                text="Hey! What's your name? Reply here and I'll add you to the session. 🏸",
            )
            await query.answer("I've sent you a DM — reply with your name!")
        except Exception:
            # Bot can't DM the user (they haven't started a chat with the bot yet).
            conversation_state.clear_pending(telegram_user_id)
            await query.answer(
                "Please start a DM with me first, then press Join again!",
                show_alert=True,
            )


async def handle_name_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handler for text messages received in private chat.

    Flow:
    1. Check conversation_state for a pending join request from this user.
    2. If found: treat the message text as their display name, add them to the
       roster (creating a player record if none exists), then refresh the group post.
    3. If not found: send a helpful fallback reply.
    """
    telegram_user_id = update.effective_user.id
    session_id = conversation_state.get_pending(telegram_user_id)

    if session_id is None:
        await update.message.reply_text(
            "I don't understand. Use the Join button in the group to sign up for a session!"
        )
        return

    player_name = update.message.text.strip()
    if not player_name:
        await update.message.reply_text("Please send a non-empty name.")
        return

    loop = asyncio.get_running_loop()
    try:
        _entry, is_waitlisted = await loop.run_in_executor(
            None, roster_service.add_player, session_id, telegram_user_id, player_name
        )
    except ValueError as exc:
        await update.message.reply_text(f"Could not join: {exc}")
        conversation_state.clear_pending(telegram_user_id)
        return

    conversation_state.clear_pending(telegram_user_id)

    if is_waitlisted:
        await update.message.reply_text(
            f"Session is full, {player_name} — you're on the waitlist! "
            "We'll let you know if a spot opens up 🎯"
        )
    else:
        await update.message.reply_text(f"You're in, {player_name}! See you on court 🏸")

    from app.bot.runner import bot_runner

    await bot_runner.edit_session_message(session_id)


async def handle_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler for the /start command in private chat."""
    await update.message.reply_text(
        "Hi! I'm the Badminton Session bot 🏸\n"
        "Use the Join button in the LOWKEY group to sign up for sessions."
    )


async def periodic_cleanup(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Job queue callback: remove expired conversation states every 5 minutes."""
    conversation_state.cleanup_expired()
