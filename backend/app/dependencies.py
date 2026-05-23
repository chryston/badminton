from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from app.db.client import get_anon_client

security = HTTPBearer()


async def require_admin(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Verify Supabase JWT. Raises 401 if invalid."""
    client = get_anon_client()
    try:
        user = client.auth.get_user(credentials.credentials)
        if not user.user:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
        return user.user
    except Exception:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
