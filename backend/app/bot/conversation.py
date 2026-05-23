from datetime import datetime, timedelta, timezone
from uuid import UUID

PENDING_TIMEOUT_MINUTES = 10


class ConversationState:
    """
    In-memory state for bot conversations.
    Tracks pending "what's your name?" prompts so the bot can correlate
    a DM reply back to the session the user tried to join.

    State: {telegram_user_id: {"session_id": UUID, "expires_at": datetime}}
    """

    def __init__(self) -> None:
        self._pending: dict[int, dict] = {}

    def set_pending(self, telegram_user_id: int, session_id: UUID) -> None:
        self._pending[telegram_user_id] = {
            "session_id": session_id,
            "expires_at": datetime.now(timezone.utc) + timedelta(minutes=PENDING_TIMEOUT_MINUTES),
        }

    def get_pending(self, telegram_user_id: int) -> UUID | None:
        """Return session_id if a valid (non-expired) pending state exists, else None."""
        state = self._pending.get(telegram_user_id)
        if state is None:
            return None
        if datetime.now(timezone.utc) > state["expires_at"]:
            del self._pending[telegram_user_id]
            return None
        return state["session_id"]

    def clear_pending(self, telegram_user_id: int) -> None:
        self._pending.pop(telegram_user_id, None)

    def cleanup_expired(self) -> None:
        """Remove all expired entries. Called periodically by the job queue."""
        now = datetime.now(timezone.utc)
        expired = [uid for uid, s in self._pending.items() if now > s["expires_at"]]
        for uid in expired:
            del self._pending[uid]


# Module-level singleton — shared across all handler calls in the same process.
conversation_state = ConversationState()
