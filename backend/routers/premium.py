# backend/routers/premium.py
from fastapi import APIRouter, Depends
from backend.schemas import (
    ProfilRequest,
    OfferResponse,
    BusinessModelResponse,
    BrandResponse,
    LandingResponse,
    MarketingResponse,
    PlanResponse
)
from backend.services.premium_service import (
    generate_offer,
    generate_business_model,
    generate_brand,
    generate_landing,
    generate_marketing,
    generate_plan
)
from backend.dependencies import require_premium

router = APIRouter(prefix="/premium", tags=["premium"])

@router.post("/offer", response_model=OfferResponse, dependencies=[Depends(require_premium)])
async def offer_endpoint(profil: ProfilRequest):
    return await generate_offer(profil)

@router.post("/model", response_model=BusinessModelResponse, dependencies=[Depends(require_premium)])
async def model_endpoint(profil: ProfilRequest):
    return await generate_business_model(profil)

@router.post("/brand", response_model=BrandResponse, dependencies=[Depends(require_premium)])
async def brand_endpoint(profil: ProfilRequest):
    return await generate_brand(profil)

@router.post("/landing", response_model=LandingResponse, dependencies=[Depends(require_premium)])
async def landing_endpoint(profil: ProfilRequest):
    return await generate_landing(profil)

@router.post("/marketing", response_model=MarketingResponse, dependencies=[Depends(require_premium)])
async def marketing_endpoint(profil: ProfilRequest):
    return await generate_marketing(profil)

@router.post("/plan", response_model=PlanResponse, dependencies=[Depends(require_premium)])
async def plan_endpoint(profil: ProfilRequest):
    return await generate_plan(profil)