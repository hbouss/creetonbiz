# backend/dependencies.py
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from backend.config import settings
# Assuming JWT token for user auth
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/token")

def get_current_user(token: str = Depends(oauth2_scheme)):
    # Decode and verify JWT, return user object
    from backend.services.user_service import get_user_from_token
    user = get_user_from_token(token)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid authentication credentials")
    return user

def require_premium(user = Depends(get_current_user)):
    if getattr(user, 'plan', 'free') != 'premium':
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="Accès réservé aux abonnés Premium"
        )
    return user