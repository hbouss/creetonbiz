# backend/main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# importe et initialise la BDD
from backend.db import init_db
from backend.routers.public import router as public_router
from backend.routers.premium import router as premium_router
from backend.routers import auth
from backend.routers.billing import router as billing_router
from backend.routers.stripe_webhook import router as stripe_webhook_router
from backend.routers.deliverables import router as deliverables_router
from backend.routers.account import router as account_router
from backend.routers.projects import router as projects_router
from backend.routers.ideas import router as ideas_router

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

app.include_router(public_router)
app.include_router(premium_router, prefix="/api")
app.include_router(auth.router, prefix="")

app.include_router(billing_router, prefix="/api")
app.include_router(stripe_webhook_router, prefix="/api")  # => /api/stripe/webhook
app.include_router(deliverables_router, prefix="/api")
app.include_router(account_router, prefix="/api")
app.include_router(projects_router, prefix="/api")
app.include_router(ideas_router)