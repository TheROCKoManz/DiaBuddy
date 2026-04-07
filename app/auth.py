from datetime import datetime, timedelta, timezone
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from app.config import get_settings

ALGORITHM = "HS256"
TOKEN_EXPIRE_HOURS = 8

_security = HTTPBearer()


def create_token(email: str) -> str:
    settings = get_settings()
    exp = datetime.now(timezone.utc) + timedelta(hours=TOKEN_EXPIRE_HOURS)
    return jwt.encode({"sub": email, "exp": exp}, settings.jwt_secret, algorithm=ALGORITHM)


def verify_token(credentials: HTTPAuthorizationCredentials = Depends(_security)) -> str:
    settings = get_settings()
    try:
        payload = jwt.decode(credentials.credentials, settings.jwt_secret, algorithms=[ALGORITHM])
        email: str = payload.get("sub", "").lower()
        if not email or email not in settings.allowed_email_list:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Email not authorized")
        return email
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expired, please sign in again")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")