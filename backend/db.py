# backend/db.py
from sqlmodel import SQLModel, create_engine
from backend.config import settings

# Crée l'engine SQLModel / SQLAlchemy
engine = create_engine(settings.DATABASE_URL, echo=True)

def init_db() -> None:
    """
    Crée toutes les tables définies par SQLModel.metadata.
    À appeler une fois au boot de l'application.
    """
    SQLModel.metadata.create_all(engine)

def get_session():
    from sqlmodel import Session
    return Session(engine)