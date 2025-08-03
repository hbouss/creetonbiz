# backend/models.py
from datetime import datetime
from typing import Optional, List

from sqlmodel import Field, SQLModel
from sqlalchemy import Column
from sqlalchemy.dialects.postgresql import JSONB

class BusinessIdea(SQLModel, table=True):
    __tablename__ = "business_ideas"

    id: Optional[int] = Field(default=None, primary_key=True)
    secteur: str
    objectif: str
    # JSON column pour les listes
    competences: List[str] = Field(
        sa_column=Column(JSONB, nullable=False),
        default=[]
    )
    idee: str
    persona: str
    nom: str
    slogan: str
    raw: str
    created_at: datetime = Field(default_factory=datetime.utcnow)

class User(SQLModel, table=True):
    __tablename__ = "users"

    id: Optional[int] = Field(default=None, primary_key=True)
    email: str = Field(index=True, nullable=False, unique=True)
    hashed_password: str = Field(nullable=False)
    plan: str = Field(default="free", nullable=False)  # 'free' ou 'premium'
    created_at: datetime = Field(default_factory=datetime.utcnow)