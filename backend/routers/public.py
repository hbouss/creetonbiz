# backend/routers/public.py
import public
from fastapi import APIRouter, HTTPException, Depends, status, Form
from pydantic import EmailStr
from fastapi.responses import JSONResponse
from sqlmodel import select
import json
import logging
from backend.schemas import ProfilRequest, BusinessResponse
from backend.models import BusinessIdea
from backend.db import get_session
from backend.services.openai_service import generate_business_idea
from backend.dependencies import (
    get_current_user,
    get_current_user_optional,
    require_infinity_or_startnow,
)

router = APIRouter(prefix="/api", tags=["public"])
logger = logging.getLogger(__name__)


@router.post("/generate", response_model=BusinessResponse)
async def generate(
    profil: ProfilRequest,
    user=Depends(get_current_user_optional),
):
    max_attempts = 3
    raw = None
    data = None

    for attempt in range(1, max_attempts + 1):
        raw = generate_business_idea(profil.model_dump())
        try:
            data = json.loads(raw)
            break
        except json.JSONDecodeError:
            logger.warning(f"[generate] tentative {attempt} échouée, JSON invalide : {raw!r}")
            if attempt == max_attempts:
                # on remonte l'erreur après la dernière tentative
                raise HTTPException(
                    status_code=500,
                    detail=f"Réponse IA non au format JSON (après {max_attempts} essais). Contenu reçu : {raw}"
                )

        # à ce stade `data` est un dict valide
    with get_session() as session:
        idea = BusinessIdea(
            user_id=user.id if user else None,
            secteur=profil.secteur,
            objectif=profil.objectif,
            competences=profil.competences,
            idee=data["idee"],
            persona=data["persona"],
            nom=data["nom"],
            slogan=data["slogan"],
            raw=raw,
            potential_rating=data.get("potential_rating"),
        )
        session.add(idea)
        session.commit()
        session.refresh(idea)

    return BusinessResponse.from_orm(idea)


@router.get("/ideas", response_model=list[BusinessResponse])
def list_ideas():
    with get_session() as session:
        records = session.exec(
            select(BusinessIdea).order_by(BusinessIdea.created_at.desc())
        ).all()
    # on renvoie tout le model Pydantic directement
    return [BusinessResponse.from_orm(r) for r in records]


@router.get(
    "/me/ideas",
    response_model=list[BusinessResponse],
    dependencies=[Depends(require_infinity_or_startnow)],
)
def list_my_ideas(user=Depends(get_current_user)):
    with get_session() as session:
        items = session.exec(
            select(BusinessIdea)
            .where(BusinessIdea.user_id == user.id)
            .order_by(BusinessIdea.created_at.desc())
        ).all()
    return [BusinessResponse.from_orm(r) for r in items]


@router.delete(
    "/me/ideas/{idea_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_infinity_or_startnow)],
)
def delete_idea(idea_id: int, user=Depends(get_current_user)):
    """
    Supprime une idée générée par l’utilisateur.
    """
    with get_session() as session:
        idea = session.get(BusinessIdea, idea_id)
        if not idea or idea.user_id != user.id:
            raise HTTPException(status_code=404, detail="Idée introuvable ou non autorisée")
        session.delete(idea)
        session.commit()
    return

@router.post("/landing/lead")
async def landing_lead(
    project_id: int = Form(...),
    name: str = Form(...),
    email: EmailStr = Form(...),
    message: str = Form(""),
):
    # Stockage minimaliste en CSV
    from datetime import datetime
    from pathlib import Path
    from backend.services.deliverable_service import STORAGE_DIR

    leads_dir = Path(STORAGE_DIR) / "leads"
    leads_dir.mkdir(parents=True, exist_ok=True)
    fp = leads_dir / f"project_{project_id}.csv"

    # Nettoyage simple pour le CSV
    name_s = (name or "").replace('"', "'")
    msg_s  = (message or "").replace('"', "'")

    if not fp.exists():
        fp.write_text("created_at,project_id,name,email,message\n", encoding="utf-8")

    line = f'"{datetime.utcnow().isoformat()}","{project_id}","{name_s}","{email}","{msg_s}"\n'
    with fp.open("a", encoding="utf-8") as f:
        f.write(line)

    return JSONResponse({"ok": True})