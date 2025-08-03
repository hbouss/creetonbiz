from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlmodel import select
from backend.db import get_session
from backend.models import User
from backend.schemas import UserCreate, Token, TokenData
from backend.services.auth_service import (
    hash_password, verify_password, create_access_token, decode_token
)

router = APIRouter(tags=["auth"])

@router.post("/register", status_code=201)
def register(user: UserCreate):
    with get_session() as session:
        exists = session.exec(select(User).where(User.email == user.email)).first()
        if exists:
            raise HTTPException(400, "Email déjà utilisé")
        db_user = User(
            email=user.email,
            hashed_password=hash_password(user.password),
            plan="free"
        )
        session.add(db_user)
        session.commit()
        session.refresh(db_user)
    return {"id": db_user.id, "email": db_user.email, "plan": db_user.plan}

@router.post("/token", response_model=Token)
def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends()):
    with get_session() as session:
        user = session.exec(select(User).where(User.email == form_data.username)).first()
        if not user or not verify_password(form_data.password, user.hashed_password):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Email ou mot de passe incorrect",
                headers={"WWW-Authenticate": "Bearer"},
            )
    token = create_access_token(sub=str(user.id))
    return {"access_token": token, "token_type": "bearer"}