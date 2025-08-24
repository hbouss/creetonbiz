# backend/routers/account.py
from fastapi import APIRouter, Depends, HTTPException, status, Response
from pydantic import BaseModel, Field
from sqlmodel import delete
import stripe

from backend.config import settings
from backend.db import get_session
from backend.dependencies import get_current_user
from backend.models import User, Deliverable, BusinessIdea
from backend.services.auth_service import verify_password, hash_password  # 👈 tes helpers existants

router = APIRouter(tags=["account"])

# ---------- Schemas ----------
class MeOut(BaseModel):
    id: int
    email: str
    plan: str
    # Ces champs existent si tu as suivi les étapes précédentes. Sinon, garde les par défaut.
    startnow_credits: int = 0
    is_admin: bool = False

class ChangePasswordIn(BaseModel):
    current_password: str = Field(min_length=6)
    new_password: str = Field(min_length=8)

class DeleteMeIn(BaseModel):
    current_password: str = Field(min_length=6)
    cancel_stripe: bool = False  # annuler l’abonnement Stripe avant suppression


# ---------- Endpoints ----------
@router.get("/me", response_model=MeOut)
def me(user = Depends(get_current_user)):
    return MeOut(
        id=user.id,
        email=user.email,
        plan=user.plan,
        startnow_credits=getattr(user, "startnow_credits", 0) or 0,
        is_admin=getattr(user, "is_admin", False),  # ⬅️ ADD
    )

@router.put("/me/password", status_code=status.HTTP_204_NO_CONTENT)
def change_password(payload: ChangePasswordIn, user = Depends(get_current_user)):
    """
    Change le mot de passe (vérifie l'ancien, enregistre le nouveau).
    Renvoie 204 No Content si OK.
    """
    with get_session() as s:
        db_user = s.get(User, user.id)
        if not db_user:
            raise HTTPException(404, "Utilisateur introuvable")

        if not verify_password(payload.current_password, db_user.hashed_password):
            raise HTTPException(400, "Mot de passe actuel invalide")

        if len(payload.new_password) < 8:
            raise HTTPException(400, "Le nouveau mot de passe doit contenir au moins 8 caractères")

        db_user.hashed_password = hash_password(payload.new_password)  # 👈 ton helper
        s.add(db_user)
        s.commit()

    return Response(status_code=status.HTTP_204_NO_CONTENT)

@router.delete("/me", status_code=status.HTTP_204_NO_CONTENT)
def delete_me(payload: DeleteMeIn, user = Depends(get_current_user)):
    """
    Supprime définitivement le compte :
    - (option) annule l’abonnement Stripe si demandé
    - supprime les livrables et projets associés
    - supprime l’utilisateur
    Renvoie 204 si OK.
    """
    with get_session() as s:
        db_user = s.get(User, user.id)
        if not db_user:
            raise HTTPException(404, "Utilisateur introuvable")

        if not verify_password(payload.current_password, db_user.hashed_password):
            raise HTTPException(400, "Mot de passe invalide")

        # Annulation Stripe (optionnelle)
        if payload.cancel_stripe and getattr(db_user, "stripe_subscription_id", None) and settings.STRIPE_SECRET_KEY:
            try:
                stripe.api_key = settings.STRIPE_SECRET_KEY
                # annule immédiatement (ou utilise cancel_at_period_end=True si tu préfères en fin de période)
                stripe.Subscription.delete(db_user.stripe_subscription_id)
            except Exception as e:
                # On n'empêche pas la suppression du compte si l’annulation Stripe échoue
                print("[Stripe] Erreur d’annulation:", e)

        # Supprimer les dépendances
        s.exec(delete(Deliverable).where(Deliverable.user_id == db_user.id))
        s.exec(delete(BusinessIdea).where(BusinessIdea.user_id == db_user.id))

        # Supprimer l’utilisateur
        s.delete(db_user)
        s.commit()

    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/me/delete", status_code=status.HTTP_204_NO_CONTENT)
def delete_me_post(payload: DeleteMeIn, user = Depends(get_current_user)):
    with get_session() as s:
        db_user = s.get(User, user.id)
        if not db_user:
            raise HTTPException(404, "Utilisateur introuvable")
        if not verify_password(payload.current_password, db_user.hashed_password):
            raise HTTPException(400, "Mot de passe invalide")
        if payload.cancel_stripe and getattr(db_user, "stripe_subscription_id", None) and settings.STRIPE_SECRET_KEY:
            try:
                stripe.api_key = settings.STRIPE_SECRET_KEY
                stripe.Subscription.delete(db_user.stripe_subscription_id)
            except Exception as e:
                print("[Stripe] Erreur d’annulation:", e)
        s.exec(delete(Deliverable).where(Deliverable.user_id == db_user.id))
        s.exec(delete(BusinessIdea).where(BusinessIdea.user_id == db_user.id))
        s.delete(db_user)
        s.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)