# backend/services/user_service.py
from typing import Optional
import jwt
from sqlmodel import select
from fastapi import HTTPException, status
from backend.config import settings
from backend.db import get_session
from backend.models import User

# Constants for JWT decoding
JWT_SECRET = settings.JWT_SECRET_KEY
ALGORITHM = settings.JWT_ALGORITHM


def get_user_from_token(token: str) -> User:
    """
    Decode the JWT token, retrieve the user ID (sub), and fetch the User from the database.
    Raises HTTPException 401 if token is invalid or user not found.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[ALGORITHM])
        user_id: Optional[int] = payload.get("sub")
        if user_id is None:
            raise credentials_exception
    except jwt.PyJWTError:
        raise credentials_exception

    # Retrieve user from DB
    with get_session() as session:
        user = session.exec(select(User).where(User.id == user_id)).first()
    if not user:
        raise credentials_exception
    return user