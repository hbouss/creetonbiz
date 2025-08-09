# backend/routers/premium.py
from fastapi import APIRouter, Depends, HTTPException, Query
from backend.schemas import (
    ProfilRequest, OfferResponse, BusinessModelResponse, BrandResponse,
    LandingResponse, MarketingResponse, PlanResponse
)
from backend.services.premium_service import (
    generate_offer, generate_business_model, generate_brand,
    generate_landing, generate_marketing, generate_plan
)
from backend.dependencies import require_startnow
from backend.services.deliverable_service import save_deliverable, write_landing_file
from backend.db import get_session
from backend.models import Project, User

router = APIRouter(prefix="/premium", tags=["premium"])

def _get_project_and_unlock_if_needed(user_id: int, project_id: int) -> Project:
    """
    - Vérifie l'accès au projet
    - Décrémente 1 crédit au premier appel premium (si pas encore débloqué)
    - Retourne TOUJOURS l'objet Project (avec idea_snapshot)
    """
    with get_session() as s:
        proj = s.get(Project, project_id)
        if not proj or proj.user_id != user_id:
            raise HTTPException(status_code=404, detail="Projet introuvable ou non autorisé")

        if not proj.premium_unlocked:
            me = s.get(User, user_id)
            if (me.startnow_credits or 0) <= 0:
                raise HTTPException(status_code=402, detail="Crédit StartNow insuffisant pour ce projet")
            # Débloque et consomme 1 crédit
            me.startnow_credits -= 1
            proj.premium_unlocked = True
            s.add_all([me, proj])
            s.commit()
            s.refresh(proj)

        # ⚠️ On renvoie toujours le projet, qu’il soit déjà débloqué ou non
        return proj

@router.post("/offer", response_model=OfferResponse)
async def offer_endpoint(
    profil: ProfilRequest,
    project_id: int = Query(..., gt=0),
    user=Depends(require_startnow),
):
    proj = _get_project_and_unlock_if_needed(user.id, project_id)
    # 👇 On passe le snapshot pour imposer la reprise VERBATIM
    data = await generate_offer(profil, idea_snapshot=proj.idea_snapshot)
    json_obj = data.model_dump() if hasattr(data, "model_dump") else data
    save_deliverable(
        user.id, "offer", json_obj,
        title=f"Offre — {proj.title}",
        project_id=project_id
    )
    return data

@router.post("/model", response_model=BusinessModelResponse)
async def model_endpoint(
    profil: ProfilRequest,
    project_id: int = Query(..., gt=0),
    user=Depends(require_startnow),
):
    proj = _get_project_and_unlock_if_needed(user.id, project_id)
    data = await generate_business_model(profil, idea_snapshot=proj.idea_snapshot)
    json_obj = data.model_dump() if hasattr(data, "model_dump") else data
    save_deliverable(user.id, "model", json_obj, title="Business Model", project_id=project_id)
    return data

@router.post("/brand", response_model=BrandResponse)
async def brand_endpoint(
    profil: ProfilRequest,
    project_id: int = Query(..., gt=0),
    user=Depends(require_startnow),
):
    proj = _get_project_and_unlock_if_needed(user.id, project_id)
    data = await generate_brand(profil, idea_snapshot=proj.idea_snapshot)
    json_obj = data.model_dump() if hasattr(data, "model_dump") else data
    save_deliverable(user.id, "brand", json_obj, title="Branding", project_id=project_id)
    return data

@router.post("/landing", response_model=LandingResponse)
async def landing_endpoint(
    profil: ProfilRequest,
    project_id: int = Query(..., gt=0),
    user=Depends(require_startnow),
):
    proj = _get_project_and_unlock_if_needed(user.id, project_id)
    data = await generate_landing(profil, idea_snapshot=proj.idea_snapshot)
    html = data.html if hasattr(data, "html") else (data.get("html") if isinstance(data, dict) else "")
    fp = write_landing_file(user.id, html)
    save_deliverable(
        user.id, "landing", {"html_saved": True},
        title="Landing HTML", file_path=fp, project_id=project_id
    )
    return data

@router.post("/marketing", response_model=MarketingResponse)
async def marketing_endpoint(
    profil: ProfilRequest,
    project_id: int = Query(..., gt=0),
    user=Depends(require_startnow),
):
    proj = _get_project_and_unlock_if_needed(user.id, project_id)
    data = await generate_marketing(profil, idea_snapshot=proj.idea_snapshot)
    json_obj = data.model_dump() if hasattr(data, "model_dump") else data
    save_deliverable(user.id, "marketing", json_obj, title="Stratégie d'acquisition", project_id=project_id)
    return data

@router.post("/plan", response_model=PlanResponse)
async def plan_endpoint(
    profil: ProfilRequest,
    project_id: int = Query(..., gt=0),
    user=Depends(require_startnow),
):
    proj = _get_project_and_unlock_if_needed(user.id, project_id)
    data = await generate_plan(profil, idea_snapshot=proj.idea_snapshot)
    json_obj = data.model_dump() if hasattr(data, "model_dump") else data
    save_deliverable(user.id, "plan", json_obj, title="Plan d'action 4 semaines", project_id=project_id)
    return data