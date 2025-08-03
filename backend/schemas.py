# backend/schemas.py
from pydantic import BaseModel, EmailStr
from typing import Optional, List

class ProfilRequest(BaseModel):
    secteur: str
    objectif: str
    competences: List[str]

class BusinessResponse(BaseModel):
    idee: str
    persona: str
    nom: str
    slogan: str
    raw: Optional[str]

# Premium response models
class OfferResponse(BaseModel):
    offer: str
    persona: str
    pain_points: List[str]

class BusinessModelResponse(BaseModel):
    model: str

class BrandResponse(BaseModel):
    brand_name: str
    slogan: str
    domain: str
    domain_available: Optional[bool]  # peut être True, False ou None

class LandingResponse(BaseModel):
    html: str

class MarketingResponse(BaseModel):
    ads_strategy: str
    seo_plan: str
    social_plan: str

class PlanResponse(BaseModel):
    plan: List[str]

class UserCreate(BaseModel):
    email: EmailStr
    password: str

class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"

class TokenData(BaseModel):
    sub: str  # on stockera l'ID en string