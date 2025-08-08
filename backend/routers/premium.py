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

def _check_project(user_id: int, project_id: int):
    with get_session() as s:
         proj = s.get(Project, project_id)

         if not proj or proj.user_id != user_id:

            raise HTTPException(404, "Projet introuvable ou non autorisé")

         # au premier appel on débloque le projet
         if not proj.premium_unlocked:
             # récupère l'utilisateur
            me = s.get(User, user_id)
         # vérifie ses crédits

            if (me.startnow_credits or 0) <= 0:
                raise HTTPException(402, "Crédit StartNow insuffisant pour ce projet")
             # décrémente et débloque
            me.startnow_credits -= 1
            proj.premium_unlocked = True
            s.add_all([me, proj])
            s.commit()
            return proj

@router.post("/offer", response_model=OfferResponse)
async def offer_endpoint(
    profil: ProfilRequest,
    project_id: int = Query(..., gt=0),
    user=Depends(require_startnow),
):
    _check_project(user.id, project_id)
    data = await generate_offer(profil)
    json_obj = data.model_dump() if hasattr(data, "model_dump") else data
    save_deliverable(user.id, "offer", json_obj, title=f"Offre — {profil.secteur}", project_id=project_id)
    return data

@router.post("/model", response_model=BusinessModelResponse)
async def model_endpoint(
    profil: ProfilRequest,
    project_id: int = Query(..., gt=0),
    user=Depends(require_startnow),
):
    _check_project(user.id, project_id)
    data = await generate_business_model(profil)
    json_obj = data.model_dump() if hasattr(data, "model_dump") else data
    save_deliverable(user.id, "model", json_obj, title="Business Model", project_id=project_id)
    return data

@router.post("/brand", response_model=BrandResponse)
async def brand_endpoint(
    profil: ProfilRequest,
    project_id: int = Query(..., gt=0),
    user=Depends(require_startnow),
):
    _check_project(user.id, project_id)
    data = await generate_brand(profil)
    json_obj = data.model_dump() if hasattr(data, "model_dump") else data
    save_deliverable(user.id, "brand", json_obj, title="Branding", project_id=project_id)
    return data

@router.post("/landing", response_model=LandingResponse)
async def landing_endpoint(
    profil: ProfilRequest,
    project_id: int = Query(..., gt=0),
    user=Depends(require_startnow),
):
    _check_project(user.id, project_id)
    data = await generate_landing(profil)
    html = data.html if hasattr(data, "html") else (data.get("html") if isinstance(data, dict) else "")
    fp = write_landing_file(user.id, html)
    save_deliverable(
        user.id,
        "landing",
        {"html_saved": True},
        title="Landing HTML",
        file_path=fp,
        project_id=project_id,
    )
    return data

@router.post("/marketing", response_model=MarketingResponse)
async def marketing_endpoint(
    profil: ProfilRequest,
    project_id: int = Query(..., gt=0),
    user=Depends(require_startnow),
):
    _check_project(user.id, project_id)
    data = await generate_marketing(profil)
    json_obj = data.model_dump() if hasattr(data, "model_dump") else data
    save_deliverable(user.id, "marketing", json_obj, title="Stratégie d'acquisition", project_id=project_id)
    return data

@router.post("/plan", response_model=PlanResponse)
async def plan_endpoint(
    profil: ProfilRequest,
    project_id: int = Query(..., gt=0),
    user=Depends(require_startnow),
):
    _check_project(user.id, project_id)
    data = await generate_plan(profil)
    json_obj = data.model_dump() if hasattr(data, "model_dump") else data
    save_deliverable(user.id, "plan", json_obj, title="Plan d'action 4 semaines", project_id=project_id)
    return data