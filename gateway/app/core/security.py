"""JWT authentication and security utilities."""

from datetime import datetime
from typing import Optional

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

from app.core.config import get_settings

settings = get_settings()
security = HTTPBearer()


class TokenPayload(BaseModel):
    """JWT token payload."""

    sub: str  # user_id
    exp: int  # expiration timestamp
    iat: int  # issued at timestamp


class User(BaseModel):
    """Authenticated user."""

    user_id: str


def decode_token(token: str) -> TokenPayload:
    """Decode and validate JWT token."""
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
        )
        return TokenPayload(**payload)
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
        )
    except jwt.InvalidTokenError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {str(e)}",
        )


def create_token(user_id: str, expires_in: int = 3600) -> str:
    """Create a JWT token for testing/development."""
    now = int(datetime.utcnow().timestamp())
    payload = {
        "sub": user_id,
        "iat": now,
        "exp": now + expires_in,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> User:
    """Dependency to get the current authenticated user."""
    payload = decode_token(credentials.credentials)

    # Check expiration
    if payload.exp < int(datetime.utcnow().timestamp()):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
        )

    return User(user_id=payload.sub)


async def get_optional_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(
        HTTPBearer(auto_error=False)
    ),
) -> Optional[User]:
    """Dependency to optionally get the current user."""
    if credentials is None:
        return None
    try:
        payload = decode_token(credentials.credentials)
        if payload.exp < int(datetime.utcnow().timestamp()):
            return None
        return User(user_id=payload.sub)
    except HTTPException:
        return None
