# backend/routers/stripe_webhook.py
from fastapi import APIRouter, Request, HTTPException
import stripe
from backend.config import settings
from backend.db import get_session
from backend.models import User
from sqlmodel import select

router = APIRouter(prefix="/stripe", tags=["stripe"])

stripe.api_key = settings.STRIPE_SECRET_KEY

def _find_user(session_db, user_id: str | None, client_ref: str | None, email: str | None):
    """Essaie de retrouver l'utilisateur via (id) puis fallback (client_reference_id) puis (email)."""
    user = None
    if user_id:
        try:
            user = session_db.exec(select(User).where(User.id == int(user_id))).first()
        except Exception:
            user = None
    if not user and client_ref:
        try:
            user = session_db.exec(select(User).where(User.id == int(client_ref))).first()
        except Exception:
            pass
    if not user and email:
        user = session_db.exec(select(User).where(User.email == email)).first()
    return user

@router.post("/webhook")
async def stripe_webhook(request: Request):
    # 1) Vérification de signature (NE PAS convertir payload en str)
    payload = await request.body()
    sig_header = request.headers.get("Stripe-Signature", "")
    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, settings.STRIPE_WEBHOOK_SECRET
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Webhook invalide: {str(e)}")

    etype = event["type"]
    obj = event["data"]["object"]
    print("[Stripe] event:", etype)

    # 2) Cas principal : la Checkout est payée
    if etype in ("checkout.session.completed", "checkout.session.async_payment_succeeded"):
        session = obj
        session_id = session.get("id")  # 👈 utile pour idempotence
        metadata = session.get("metadata") or {}
        pack = (metadata.get("pack") or "").lower()              # "infinity" ou "startnow"
        user_id = metadata.get("user_id")
        client_ref = session.get("client_reference_id")
        email = session.get("customer_email") or (session.get("customer_details") or {}).get("email")

        # (disponibles si mode=subscription)
        customer_id = session.get("customer")
        subscription_id = session.get("subscription")

        print("Session id:", session.get("id"))
        print("Session metadata:", metadata)
        print("Client ref id:", client_ref)
        print("Customer email:", email)

        # Legacy : certaines anciennes sessions peuvent remonter "premium"
        if pack == "premium":
            pack = "startnow"

        if pack not in ("infinity", "startnow"):
            print(f"[WEBHOOK] Pack inconnu '{pack}', on ignore.")
            return {"received": True}

        with get_session() as s:
            user = _find_user(s, user_id, client_ref, email)
            if not user:
                print("[WEBHOOK] Aucun user trouvé pour cette session.")
                return {"received": True}

            # Mise à jour du plan
            user.plan = pack
            # Idempotence : ne créditer qu'une fois ce session.id
            if pack == "startnow" and session_id and user.last_checkout_session_id != session_id:
                user.startnow_credits = (user.startnow_credits or 0) + 1
                user.last_checkout_session_id = session_id

            if hasattr(user, "stripe_customer_id") and customer_id:
                user.stripe_customer_id = customer_id
            if hasattr(user, "stripe_subscription_id") and subscription_id:
                user.stripe_subscription_id = subscription_id
            if hasattr(user, "idea_used"):
                user.idea_used = 0

            s.add(user)
            s.commit()
            print(f"[WEBHOOK] User {user.email} -> {pack} ✅")

    # 3) (Optionnel) gérer la résiliation si tu stockes stripe_customer_id
    elif etype == "customer.subscription.deleted":
        subscription = obj
        customer_id = subscription.get("customer")
        if customer_id and hasattr(User, "stripe_customer_id"):
            with get_session() as s:
                user = s.exec(
                    select(User).where(getattr(User, "stripe_customer_id") == customer_id)
                ).first()
                if user:
                    user.plan = "free"
                    s.add(user)
                    s.commit()
                    print(f"[WEBHOOK] Abonnement résilié → {user.email} repasse en free")

    return {"received": True}