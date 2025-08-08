# backend/routers/ideas.py
from http.client import HTTPException

from fastapi import APIRouter, Depends
from sqlmodel import select
from backend.db import get_session
from backend.models import BusinessIdea
from backend.schemas import BusinessResponse
from backend.dependencies import get_current_user

router = APIRouter(prefix="/api/me/ideas", tags=["ideas"])

@router.get("", response_model=list[BusinessResponse])
def list_my_ideas(user = Depends(get_current_user)):
    with get_session() as session:
        records = session.exec(
            select(BusinessIdea)
            .where(BusinessIdea.user_id == user.id)
            .order_by(BusinessIdea.created_at.desc())
        ).all()

    return [
        BusinessResponse(
            id            = r.id,
            idee          = r.idee,
            persona       = r.persona,
            nom           = r.nom,
            slogan        = r.slogan,
            raw           = r.raw,
            secteur       = r.secteur,
            objectif      = r.objectif,
            competences   = r.competences,
            created_at    = r.created_at,
            potential_rating=r.potential_rating,
        )
        for r in records
    ]

@router.delete("/{idea_id}", status_code=204)
def delete_my_idea(idea_id: int, user = Depends(get_current_user)):
    with get_session() as session:
        idea = session.get(BusinessIdea, idea_id)
        if not idea or idea.user_id != user.id:
            raise HTTPException(status_code=404, detail="Idée introuvable")
        session.delete(idea)
        session.commit()