# backend/routers/deliverables.py
from fastapi import APIRouter, Depends, HTTPException, Response
from typing import Optional
from backend.dependencies import get_current_user
from backend.db import get_session
from backend.models import Deliverable
from sqlmodel import select
from fastapi.responses import FileResponse, JSONResponse
from backend.services.pdf_service import make_pdf_from_deliverable

router = APIRouter(prefix="/me", tags=["me"])

@router.get("/deliverables")
def list_deliverables(kind: Optional[str] = None, project_id: Optional[int] = None, user=Depends(get_current_user)) -> list[dict]:
    with get_session() as s:
        from backend.models import Project
        q = select(Deliverable).where(Deliverable.user_id == user.id)
        if kind:
            q = q.where(Deliverable.kind == kind)
        if project_id:
            # vérifie propriété projet
            p = s.get(Project, project_id)
            if not p or p.user_id != user.id:
                raise HTTPException(404, "Projet introuvable")
            q = q.where(Deliverable.project_id == project_id)
        if kind:
            q = q.where(Deliverable.kind == kind)
        items = s.exec(q.order_by(Deliverable.created_at.desc())).all()

    out = []
    for d in items:
        out.append({
            "id": d.id,
            "kind": d.kind,
            "title": d.title,
            "created_at": d.created_at.isoformat(),
            "has_file": bool(d.file_path),
            "json": d.json_content,
        })
    return out

@router.get("/deliverables/{deliverable_id}")
def get_deliverable(deliverable_id: int, user=Depends(get_current_user)) -> dict:
    with get_session() as s:
        d = s.get(Deliverable, deliverable_id)
        if not d or d.user_id != user.id:
            raise HTTPException(404, "Livrable introuvable")
    return {
        "id": d.id,
        "kind": d.kind,
        "title": d.title,
        "created_at": d.created_at.isoformat(),
        "has_file": bool(d.file_path),
        "json": d.json_content,
    }

@router.get("/deliverables/{deliverable_id}/download")
def download_deliverable_file(
    deliverable_id: int,
    format: Optional[str] = "auto",  # auto|html|json|md|pdf
    user=Depends(get_current_user)
):
    with get_session() as s:
        d = s.get(Deliverable, deliverable_id)
        if not d or d.user_id != user.id:
            raise HTTPException(404, "Livrable introuvable")

    # 1) Cas fichier existant (landing HTML)
    if d.file_path and (format in ("auto", "file", "html")):
        filename = d.title or f"{d.kind}-{d.id}.html"
        return FileResponse(d.file_path, filename=filename, media_type="text/html")

    # 2) PDF à la volée
    if format == "pdf" or format == "auto":
        try:
            pdf_bytes = make_pdf_from_deliverable(d)
            filename = f"{d.kind}-{d.id}.pdf"
            return Response(
                pdf_bytes,
                media_type="application/pdf",
                headers={"Content-Disposition": f'attachment; filename="{filename}"'}
            )
        except Exception as e:
            # En cas d'erreur de génération PDF, on bascule sur JSON
            print("[PDF ERROR]", e)

    # 3) Fallback JSON
    filename = f"{d.kind}-{d.id}.json"
    return JSONResponse(
        d.json_content or {},
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )