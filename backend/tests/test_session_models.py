from pydantic import ValidationError

from app.models.session import SessionUpdate


def test_session_update_allows_omitted_venue_id():
    update = SessionUpdate()

    assert update.venue_id is None


def test_session_update_rejects_null_venue_id():
    try:
        SessionUpdate.model_validate({"venue_id": None})
    except ValidationError as exc:
        assert "venue_id cannot be null" in str(exc)
    else:
        raise AssertionError("Expected ValidationError for null venue_id")
