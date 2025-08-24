# backend/dependencies.py
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from backend.services.user_service import get_user_from_token

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/token")

def get_current_user_optional(token: str = Depends(oauth2_scheme)):
    try:
        return get_user_from_token(token)
    except:
        return None

def get_current_user(token: str = Depends(oauth2_scheme)):
    user = get_user_from_token(token)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid authentication credentials")
    return user

def require_infinity_or_startnow(user = Depends(get_current_user)):
    if getattr(user, "plan", "free") not in ("infinity", "startnow"):
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="Passez à Infinity pour idées illimitées."
        )
    return user

def require_startnow(user = Depends(get_current_user)):
    if getattr(user, "plan", "free") != "startnow":
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="Accès réservé au pack StartNow."
        )
    return user


def require_admin(user = Depends(get_current_user)):
    if not getattr(user, "is_admin", False):
        raise HTTPException(403, "Admin requis")
    return user