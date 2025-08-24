# backend/routers/billing.py
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from fastapi.responses import RedirectResponse

from backend.db import get_session
from backend.models import User
from sqlmodel import select
import stripe
from backend.config import settings
from backend.dependencies import get_current_user

router = APIRouter(tags=["billing"])

stripe.api_key = settings.STRIPE_SECRET_KEY

class CheckoutPayload(BaseModel):
    pack: str = Field(
        ...,
        description="‘infinity’, ‘startnow’ ou ‘startnow-one-time’"
    )


class PortalOut(BaseModel):
    url: str

@router.post("/create-checkout-session")
def create_checkout_session(
    payload: CheckoutPayload,
    user: User = Depends(get_current_user),
):
    # IDs de prix
    PRICE_ID_INFINITY           = settings.STRIPE_PRICE_ID_INFINITY          # abo 29,90€/mois
    PRICE_ID_STARTNOW_ONE_TIME  = settings.STRIPE_PRICE_ID_STARTNOW_ONE_TIME # 350€ one-time
    PRICE_ID_STARTNOW_SUB       = settings.STRIPE_PRICE_ID_INFINITY          # 29,90€/mois (réutilisé)

    if not settings.FRONTEND_BASE_URL:
        raise HTTPException(500, "FRONTEND_BASE_URL manquant")

    requested = payload.pack.lower()
    if requested not in ("infinity", "startnow"):
        raise HTTPException(400, "Pack invalide")

    # Si on demande un startnow *et* que l’utilisateur a déjà un abonnement
    # (startnow ou infinity), on ne facture que le one-time.
    if requested == "startnow" and user.plan != "free":
        # pack « virtuel » pour construire le panier
        actual_pack = "startnow-one-time"
    else:
        actual_pack = requested

    # Préparation du panier Stripe
    if actual_pack == "infinity":
        mode       = "subscription"
        line_items = [{"price": PRICE_ID_INFINITY, "quantity": 1}]
    elif actual_pack == "startnow":
        mode       = "subscription"
        line_items = [
            {"price": PRICE_ID_STARTNOW_SUB,     "quantity": 1},  # abo 29,90€/mois
            {"price": PRICE_ID_STARTNOW_ONE_TIME,"quantity": 1},  # one-time 350€
        ]
    else:  # "startnow-one-time"
        mode       = "payment"  # paiement one-shot
        line_items = [{"price": PRICE_ID_STARTNOW_ONE_TIME, "quantity": 1}]

    # URLs de retour
    success_url = (
        f"{settings.FRONTEND_BASE_URL}/premium?success=1"
        f"&session_id={{CHECKOUT_SESSION_ID}}&pack={requested}"
    )
    cancel_url = f"{settings.FRONTEND_BASE_URL}/premium?canceled=1"

    session = stripe.checkout.Session.create(
        mode=mode,
        line_items=line_items,
        customer_email=user.email,
        client_reference_id=str(user.id),
        metadata={"user_id": str(user.id), "pack": requested},
        success_url=success_url,
        cancel_url=cancel_url,
        allow_promotion_codes=True,
    )

    return {"sessionId": session.id}

@router.get("/verify-checkout-session")
def verify_checkout_session(
    session_id: str,
    user = Depends(get_current_user),
):
    s = stripe.checkout.Session.retrieve(session_id)
    paid = s.get("payment_status") == "paid" or s.get("status") == "complete"
    metadata = s.get("metadata") or {}
    pack = (metadata.get("pack") or "").lower()

    if not paid:
        raise HTTPException(400, "Session non payée")

    if pack not in ("infinity", "startnow", "startnow-one-time"):
        raise HTTPException(400, "Pack inconnu")

    customer_id = s.get("customer")
    subscription_id = s.get("subscription")

    with get_session() as db:
        me = db.exec(select(User).where(User.id == user.id)).first()
        if not me:
            raise HTTPException(404, "Utilisateur introuvable")

        # 1) Mise à jour du plan si nécessaire
        if pack == "infinity" and me.plan != "infinity":
            me.plan = "infinity"
        elif pack == "startnow" and me.plan != "startnow":
            me.plan = "startnow"
        # pack == startnow-one-time n’affecte pas me.plan

        # 2) Créditer un jeton StartNow à l’issue d’un setup one-time
        #    (une seule fois par sessionId)
        if pack in ("startnow", "startnow-one-time"):
            if me.last_checkout_session_id != session_id:
                me.startnow_credits = (me.startnow_credits or 0) + 1
                me.last_checkout_session_id = session_id

        # 3) Stocker les IDs Stripe
        if hasattr(me, "stripe_customer_id") and customer_id:
            me.stripe_customer_id = customer_id
        if hasattr(me, "stripe_subscription_id") and subscription_id:
            me.stripe_subscription_id = subscription_id

        db.add(me)
        db.commit()
        credits = me.startnow_credits

    return {"ok": True, "pack": pack, "startnow_credits": credits}

@router.post("/billing-portal", response_model=PortalOut)
def create_billing_portal_session(user: User = Depends(get_current_user)):
    if not settings.STRIPE_SECRET_KEY:
        raise HTTPException(500, "STRIPE_SECRET_KEY manquant")
    if not settings.FRONTEND_BASE_URL:
        raise HTTPException(500, "FRONTEND_BASE_URL manquant")

    stripe.api_key = settings.STRIPE_SECRET_KEY

    # Récupère/assure le customer_id Stripe
    with get_session() as s:
        me = s.get(User, user.id)
        cid = getattr(me, "stripe_customer_id", None)

        if not cid:
            # essaie de retrouver par email
            existing = stripe.Customer.list(email=me.email, limit=1).data
            if existing:
                cid = existing[0].id
            else:
                created = stripe.Customer.create(email=me.email)
                cid = created.id
            me.stripe_customer_id = cid
            s.add(me)
            s.commit()

    session = stripe.billing_portal.Session.create(
        customer=cid,
        return_url=f"{settings.FRONTEND_BASE_URL}/settings"
    )
    return {"url": session.url}

@router.get("/billing-portal/redirect")
def redirect_billing_portal_session(user: User = Depends(get_current_user)):
    if not settings.STRIPE_SECRET_KEY:
        raise HTTPException(500, "STRIPE_SECRET_KEY manquant")
    if not settings.FRONTEND_BASE_URL:
        raise HTTPException(500, "FRONTEND_BASE_URL manquant")

    stripe.api_key = settings.STRIPE_SECRET_KEY

    # Récupère/assure le customer_id Stripe
    with get_session() as s:
        me = s.get(User, user.id)
        cid = getattr(me, "stripe_customer_id", None)
        if not cid:
            existing = stripe.Customer.list(email=me.email, limit=1).data
            if existing:
                cid = existing[0].id
            else:
                created = stripe.Customer.create(email=me.email)
                cid = created.id
            me.stripe_customer_id = cid
            s.add(me)
            s.commit()

    session = stripe.billing_portal.Session.create(
        customer=cid,
        return_url=f"{settings.FRONTEND_BASE_URL}/settings"
    )
    # 303 → navigation propre vers Stripe
    return RedirectResponse(session.url, status_code=303)