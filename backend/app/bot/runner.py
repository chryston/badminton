import asyncio
import logging
from uuid import UUID

from telegram import InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    filters,
)

import app.services.venue_service as venue_service
from app.bot.handlers import (
    handle_join_callback,
    handle_name_message,
    handle_start,
    periodic_cleanup,
)
from app.bot.message_formatter import (
    build_full_button,
    build_join_button,
    format_admin_summary,
    format_cancellation_message,
    format_session_announcement,
)
from app.config import settings
from app.models.roster import RosterEntry
from app.models.session import Session, SessionUpdate
from app.services import player_service, roster_service, session_service


class BotRunner:
    """
    Owns the python-telegram-bot Application lifecycle and exposes methods
    that API route handlers can call to post or update Telegram messages.

    Designed to run in the same process as FastAPI via asyncio.create_task().
    """

    def __init__(self) -> None:
        self._app: Application | None = None

    def build(self) -> None:
        """Build the Application and register handlers. Must be called once at startup."""
        self._app = Application.builder().token(settings.telegram_bot_token).build()

        self._app.add_handler(CommandHandler("start", handle_start))
        self._app.add_handler(
            CallbackQueryHandler(handle_join_callback, pattern=r"^join:")
        )
        self._app.add_handler(
            MessageHandler(filters.TEXT & filters.ChatType.PRIVATE, handle_name_message)
        )
        # Clean up stale conversation states every 5 minutes.
        self._app.job_queue.run_repeating(periodic_cleanup, interval=300, first=10)

    async def start_polling(self) -> None:
        """
        Start long-polling. Blocks (via asyncio.Event) until the task is cancelled.
        Long-polling keeps the Render free-tier dyno warm 24/7 — no webhooks needed.
        """
        await self._app.initialize()
        await self._app.start()
        await self._app.updater.start_polling(drop_pending_updates=True)
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            pass
        finally:
            await self._app.updater.stop()
            await self._app.stop()
            await self._app.shutdown()

    async def post_session_announcement(self, session: Session) -> None:
        """
        Post a session announcement to the LOWKEY group chat.

        1. Fetches roster, venue, and paynow player details.
        2. Formats and sends the message with a Join button.
        3. Saves the Telegram message_id back to the session record.
        4. Sends a short summary to the admin chat.
        """
        loop = asyncio.get_running_loop()

        venue = await loop.run_in_executor(None, venue_service.get_by_id, session.venue_id)
        roster = await loop.run_in_executor(
            None, roster_service.get_session_roster, session.id
        )
        player_names = await self._build_player_names(roster, loop)
        paynow_name, paynow_phone = await self._resolve_paynow(session, loop)

        text = format_session_announcement(
            session, roster, player_names, venue.name, paynow_name, paynow_phone
        )
        keyboard = build_join_button(str(session.id))

        message = await self._app.bot.send_message(
            chat_id=settings.telegram_lowkey_chat_id,
            text=text,
            reply_markup=keyboard,
        )

        # Persist the message_id so we can edit it later.
        await loop.run_in_executor(
            None,
            session_service.update,
            session.id,
            SessionUpdate(telegram_message_id=message.message_id),
        )

        admin_text = format_admin_summary(session, venue.name)
        await self._app.bot.send_message(
            chat_id=settings.telegram_admin_chat_id,
            text=admin_text,
        )

    async def edit_session_message(self, session_id: UUID) -> None:
        """
        Re-fetch the session + roster and edit the existing Telegram message in-place.

        Idempotent — safe to call multiple times; does nothing if no message has been
        posted yet (telegram_message_id is None).
        """
        loop = asyncio.get_running_loop()

        session = await loop.run_in_executor(
            None, session_service.get_by_id, session_id
        )
        if session.telegram_message_id is None:
            return

        venue = await loop.run_in_executor(None, venue_service.get_by_id, session.venue_id)
        player_names = await self._build_player_names(session.roster, loop)
        paynow_name, paynow_phone = await self._resolve_paynow(session, loop)

        text = format_session_announcement(
            session, session.roster, player_names, venue.name, paynow_name, paynow_phone
        )

        active_count = sum(1 for e in session.roster if not e.is_waitlisted)
        is_full = active_count >= session.max_pax
        keyboard: InlineKeyboardMarkup = (
            build_full_button() if is_full else build_join_button(str(session_id))
        )

        from telegram.error import BadRequest

        try:
            await self._app.bot.edit_message_text(
                chat_id=settings.telegram_lowkey_chat_id,
                message_id=session.telegram_message_id,
                text=text,
                reply_markup=keyboard,
            )
        except BadRequest as e:
            if "message is not modified" not in str(e).lower():
                raise
            # silently ignore — message content unchanged

    async def post_cancellation_message(self, session: Session, reason: str) -> None:
        """Post a cancellation notice to the LOWKEY group chat.

        Only sends if the session had a Telegram message (was published).
        """
        if session.telegram_message_id is None:
            return  # session was never published — nothing to notify

        loop = asyncio.get_running_loop()
        venue = await loop.run_in_executor(None, venue_service.get_by_id, session.venue_id)
        text = format_cancellation_message(session, venue.name, reason)

        try:
            await self._app.bot.send_message(
                chat_id=settings.telegram_lowkey_chat_id,
                text=text,
            )
        except Exception:
            logging.getLogger(__name__).exception(
                "Failed to send cancellation message for session %s", session.id
            )

    async def update_payment_in_message(self, session_id: UUID) -> None:
        """Trigger a full message re-render after a payment status change."""
        await self.edit_session_message(session_id)

    # ------------------------------------------------------------------ helpers

    async def _build_player_names(
        self, roster: list[RosterEntry], loop: asyncio.AbstractEventLoop
    ) -> dict[UUID, str]:
        """Resolve player UUIDs to display names for all registered entries."""
        player_names: dict[UUID, str] = {}
        for entry in roster:
            if entry.player_id and entry.player_id not in player_names:
                try:
                    player = await loop.run_in_executor(
                        None, player_service.get_by_id, entry.player_id
                    )
                    player_names[entry.player_id] = player.name
                except ValueError:
                    pass  # Orphaned roster entry — display_name will fall back to "Unknown"
        return player_names

    async def _resolve_paynow(
        self, session: Session, loop: asyncio.AbstractEventLoop
    ) -> tuple[str, str]:
        """Return (paynow_name, paynow_phone) for the session's designated paynow player."""
        if session.paynow_player_id is not None:
            try:
                player = await loop.run_in_executor(
                    None, player_service.get_by_id, session.paynow_player_id
                )
                return player.name, player.phone or ""
            except ValueError:
                pass
        return "TBD", ""


# Module-level singleton — imported by handlers (lazily) and by API routers.
bot_runner = BotRunner()
