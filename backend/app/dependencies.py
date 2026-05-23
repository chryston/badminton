import logging
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from app.db.client import get_anon_client, get_service_client

logger = logging.getLogger(__name__)
security = HTTPBearer()


async def require_admin(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Verify Supabase JWT and confirm player has is_admin=True."""
    client = get_anon_client()
    try:
        user_response = client.auth.get_user(credentials.credentials)
    except Exception:
        logger.warning("JWT validation failed", exc_info=True)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    if not user_response.user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    # Check admin flag in players table
    service = get_service_client()
    result = service.table("players") \
        .select("is_admin") \
        .eq("auth_user_id", str(user_response.user.id)) \
        .maybe_single() \
        .execute()

    if not result.data or not result.data["is_admin"]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")

    return user_response.user
