# backend/main.py
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

# importe et initialise la BDD
from backend.db import init_db, get_session
from backend.schemas import ProfilRequest, BusinessResponse
from backend.models import BusinessIdea
from backend.services.openai_service import generate_business_idea
from backend.routers.premium import router as premium_router
from backend.routers import auth

import json
from sqlmodel import select

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Création des tables si elles n'existent pas
init_db()

@app.get("/")
def read_root():
    return {"message": "Bienvenue sur CréeTonBiz API"}

@app.post("/generate", response_model=BusinessResponse)
async def generate(profil: ProfilRequest):
    raw = generate_business_idea(profil.dict())
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        raise HTTPException(500, detail="Réponse IA non au format JSON")

    # Persistance
    from backend.db import get_session
    with get_session() as session:
        record = BusinessIdea(
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

    return BusinessResponse(
        idee=record.idee,
        persona=record.persona,
        nom=record.nom,
        slogan=record.slogan,
        raw=record.raw
    )

@app.get("/projects", response_model=list[BusinessResponse])
def list_projects():
    with get_session() as session:
        records = session.exec(
            select(BusinessIdea).order_by(BusinessIdea.created_at.desc())
        ).all()
    return [
        BusinessResponse(
            idee=r.idee,
            persona=r.persona,
            nom=r.nom,
            slogan=r.slogan,
            raw=r.raw
        )
        for r in records
    ]

app.include_router(premium_router)
app.include_router(auth.router, prefix="")