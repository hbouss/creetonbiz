# backend/routers/public.py
from fastapi import APIRouter, HTTPException, Depends, status
from sqlmodel import select
import json

from backend.schemas import ProfilRequest, BusinessResponse
from backend.models import BusinessIdea
from backend.db import get_session
from backend.services.openai_service import generate_business_idea
from backend.dependencies import get_current_user, get_current_user_optional, require_infinity_or_startnow

router = APIRouter(prefix="/api", tags=["public"])  # /api/*

@router.post("/generate", response_model=BusinessResponse)
async def generate(profil: ProfilRequest, user = Depends(get_current_user_optional),):
    raw = generate_business_idea(profil.model_dump())
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        raise HTTPException(500, detail="Réponse IA non au format JSON")

    with get_session() as session:
        record = BusinessIdea(
            user_id=user.id if user else None,
            secteur=profil.secteur,
            objectif=profil.objectif,
            competences=profil.competences,
            idee=data["idee"],
            persona=data["persona"],
            nom=data["nom"],
            slogan=data["slogan"],
            raw=raw
        )
        session.add(record)
        session.commit()
        session.refresh(record)

    return BusinessResponse.from_orm(record)

@router.get("/ideas", response_model=list[BusinessResponse])
def list_ideas():
    with get_session() as session:
        records = session.exec(
            select(BusinessIdea).order_by(BusinessIdea.created_at.desc())
        ).all()
    return [
        BusinessResponse(
            id=r.id,
            idee=r.idee,
            persona=r.persona,
            nom=r.nom,
            slogan=r.slogan,
            raw=r.raw
        )
        for r in records
    ]

@router.get(
    "/me/ideas",
    response_model=list[BusinessResponse],
    dependencies=[Depends(require_infinity_or_startnow)],
)
def list_my_ideas(user = Depends(get_current_user)):
    with get_session() as session:
        items = session.exec(
            select(BusinessIdea)
            .where(BusinessIdea.user_id == user.id)
            .order_by(BusinessIdea.created_at.desc())
        ).all()
    return [
        BusinessResponse(
            id=r.id,
            idee=r.idee,
            persona=r.persona,
            nom=r.nom,
            slogan=r.slogan,
            raw=r.raw,
            secteur=r.secteur,
            objectif=r.objectif,
            competences=r.competences,
            created_at=r.created_at,
        )
        for r in items
    ]

@router.delete(
    "/me/ideas/{idea_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_infinity_or_startnow)],
)
def delete_idea(idea_id: int, user=Depends(get_current_user)):
    """
    Supprime une idée générée par l’utilisateur.
    """
    from backend.models import BusinessIdea
    from backend.db import get_session

    with get_session() as session:
        idea = session.get(BusinessIdea, idea_id)
        if not idea or idea.user_id != user.id:
            raise HTTPException(status_code=404, detail="Idée introuvable ou non autorisée")
        session.delete(idea)
        session.commit()
    return

