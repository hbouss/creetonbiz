# backend/models.py
from datetime import datetime
from typing import Optional, List, Dict, Any

from sqlmodel import Field, SQLModel
from sqlalchemy import Column, Text, String
from sqlalchemy.dialects.postgresql import JSONB

class BusinessIdea(SQLModel, table=True):
    __tablename__ = "business_ideas"

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: Optional[int] = Field(index=True, foreign_key="users.id")  # ← lien user
    secteur: str
    objectif: str
    competences: List[str] = Field(sa_column=Column(JSONB))
    idee: str
    persona: str
    nom: str
    slogan: str
    raw: str
    created_at: datetime = Field(default_factory=datetime.utcnow)

class User(SQLModel, table=True):
    __tablename__ = "users"

    id: Optional[int] = Field(default=None, primary_key=True)
    email: str = Field(
        sa_column=Column(String, unique=True, index=True, nullable=False)
    )
    hashed_password: str = Field(nullable=False)
    plan: str = Field(default="free", nullable=False)  # "free" | "infinity" | "startnow"
    idea_used: int = Field(default=0)  # compteur d'idées utilisées
    startnow_credits: int = Field(default=0)  # ✅ NEW : nb de crédits StartNow disponibles
    last_checkout_session_id: Optional[str] = None  # 👈 garde fou
    stripe_customer_id: Optional[str] = None
    stripe_subscription_id: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)

# ✅ NEW : Projet = 1 crédit StartNow → 1 nouveau projet (tous les livrables y sont rattachés)
# ──────────────────────────────────────────────────────────────────────────────
class Project(SQLModel, table=True):
    __tablename__ = "projects"

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    title: str
    secteur: str
    objectif: str
    competences: List[str] = Field(sa_column=Column(JSONB, nullable=False), default=[])
    premium_unlocked: bool = Field(default=False)
    created_at: datetime = Field(default_factory=datetime.utcnow)

    # ← NOUVEAU : lien vers l’idée d’origine (null si manuel)
    idea_id: Optional[int] = Field(default=None, foreign_key="business_ideas.id", index=True)

class Deliverable(SQLModel, table=True):
    __tablename__ = "deliverables"

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(index=True, foreign_key="users.id")
    project_id: Optional[int] = Field(  # ✅ NEW : rattachement au projet
        default=None,
        foreign_key="projects.id",
        index=True
    )
    kind: str  # 'offer','model','brand','landing','marketing','plan'
    title: Optional[str] = None
    # Utiliser sa_column pour JSONB
    json_content: Optional[Dict[str, Any]] = Field(sa_column=Column(JSONB))
    file_path: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)