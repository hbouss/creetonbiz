# backend/routers/admin.py
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import select
from backend.db import get_session
from backend.models import User
from backend.dependencies import require_admin
from pydantic import BaseModel
import os, stripe

router = APIRouter(prefix="/admin", tags=["admin"])

@router.get("/users")
def list_users(_: User = Depends(require_admin)):
    with get_session() as s:
        rows = s.exec(select(User).order_by(User.created_at.desc())).all()
        out = []
        is_test = (os.getenv("STRIPE_SECRET_KEY","").startswith("sk_test_"))
        for u in rows:
            cid = getattr(u, "stripe_customer_id", None)
            link = cid and f"https://dashboard.stripe.com/{'test/' if is_test else ''}customers/{cid}"
            out.append({
                "id": u.id, "email": u.email, "plan": u.plan,
                "startnow_credits": u.startnow_credits,
                "idea_used": u.idea_used,
                "is_admin": u.is_admin,
                "stripe_customer_id": cid,
                "stripe_link": link
            })
        return out

class AdminUserPatch(BaseModel):
    plan: str | None = None
    startnow_credits: int | None = None
    idea_used: int | None = None
    is_admin: bool | None = None
    cancel_stripe: bool | None = None

@router.patch("/users/{user_id}")
def update_user(user_id: int, patch: AdminUserPatch, _: User = Depends(require_admin)):
    with get_session() as s:
        u = s.get(User, user_id)
        if not u:
            raise HTTPException(404, "User introuvable")

        if patch.cancel_stripe and getattr(u, "stripe_subscription_id", None):
            try:
                stripe.api_key = os.getenv("STRIPE_SECRET_KEY","")
                stripe.Subscription.delete(u.stripe_subscription_id)
            except Exception as e:
                print("[admin] Stripe cancel failed:", e)

        for k, v in patch.dict(exclude_unset=True).items():
            if k != "cancel_stripe":
                setattr(u, k, v)

        s.add(u); s.commit()
    return {"ok": True}