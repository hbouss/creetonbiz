# backend/routers/projects.py
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlmodel import select
from backend.db import get_session
from backend.dependencies import get_current_user
from backend.models import User
from backend.models import Project, Deliverable
from sqlalchemy import delete

router = APIRouter(prefix="/projects", tags=["projects"])

class CreateProjectBody(BaseModel):
    title: str
    secteur: str
    objectif: str
    competences: list[str]
    idea_id: int | None = None  # ← NOUVEAU

@router.get("", status_code=200)
def list_projects(user=Depends(get_current_user)):
    with get_session() as s:
        items = s.exec(
            select(Project).where(Project.user_id == user.id).order_by(Project.created_at.desc())
        ).all()
    return [
        {
            "id": p.id,
            "title": p.title,
            "secteur": p.secteur,
            "objectif": p.objectif,
            "competences": p.competences,
            "created_at": p.created_at.isoformat(),
            "idea_id": p.idea_id,  # ← on renvoie le flag
        } for p in items
    ]

# backend/routers/projects.py  ───────────
@router.post("", status_code=201)
def create_project(body: CreateProjectBody, user=Depends(get_current_user)):
    # ⛔️ NE consommons plus de crédit ici !
    proj = Project(
        user_id=user.id,
        title=body.title.strip() or "Mon projet",
        secteur=body.secteur,
        objectif=body.objectif,
        competences=body.competences,
        premium_unlocked=False,          # ← explicite
        idea_id=body.idea_id,  # ← si conversion d’idée
    )
    with get_session() as s:
        s.add(proj)
        s.commit()
        s.refresh(proj)
    return {"id": proj.id}

@router.delete(
    "/{project_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_project(project_id: int, user=Depends(get_current_user)):
    """
    Supprime un projet (et ses livrables) pour l’utilisateur courant.
    """
    from backend.db import get_session
    with get_session() as session:
        proj = session.get(Project, project_id)
        if not proj or proj.user_id != user.id:
            raise HTTPException(status_code=404, detail="Projet introuvable ou non autorisé")
        # supprime d’abord les deliverables liés
        session.exec(
            delete(Deliverable).where(Deliverable.project_id == project_id)
        )
        session.delete(proj)
        session.commit()
    return