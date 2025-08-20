# backend/routers/deliverables.py
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Response
from typing import Optional
from backend.dependencies import get_current_user, require_startnow
from backend.db import get_session
from backend.models import Deliverable
from sqlmodel import select
from fastapi.responses import FileResponse, JSONResponse
from backend.services.pdf_service import make_pdf_from_deliverable
from backend.services.deliverable_service import export_pdf_from_html
from backend.services.calendar_service import ics_from_events
import os

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

        # 🔹 ICS pour le plan d'action (même endpoint que les autres)
        if format == "ics":
            j = d.json_content or {}
            ics_path = (j or {}).get("ics_path")
            # 1) Si un fichier ICS existe, on le renvoie tel quel
            if ics_path and os.path.exists(ics_path):
                return FileResponse(
                    ics_path,
                    filename=f"{(d.title or d.kind).replace(' ', '_')}.ics",
                    media_type="text/calendar; charset=utf-8"
                )
            # 2) Sinon, on (re)génère à la volée depuis la schedule
            if d.kind != "plan":
                raise HTTPException(400, "Export ICS disponible uniquement pour le plan d'action.")
            events = (j or {}).get("schedule") or []
            if not events:
                raise HTTPException(404, "Aucun évènement calendrier dans ce plan.")
            ics_str = ics_from_events(d.title or d.kind, events)
            filename = f"{(d.title or d.kind).replace(' ', '_')}.ics"
            return Response(
                content=ics_str,
                media_type="text/calendar; charset=utf-8",
                headers={"Content-Disposition": f'attachment; filename="{filename}"'}
            )

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

@router.get("/{deliverable_id}/pdf")
async def download_pdf(deliverable_id: int, user=Depends(require_startnow)):
    with get_session() as s:
        d = s.get(Deliverable, deliverable_id)
        if not d or d.user_id != user.id:
            raise HTTPException(404, "Livrable introuvable")

        j = d.json_content or {}

        # 1) Même flux pour MARKETING **et PLAN** : PDF Playwright depuis l’HTML
        if d.kind in ("marketing", "plan"):
            pdf_path = (j or {}).get("pdf_path")
            if pdf_path and os.path.exists(pdf_path):
                return FileResponse(pdf_path, media_type="application/pdf",
                                    filename=Path(pdf_path).name)

            if d.file_path and os.path.exists(d.file_path):
                new_pdf = await export_pdf_from_html(d.file_path)
                j["pdf_path"] = new_pdf
                d.json_content = j
                s.add(d); s.commit()
                return FileResponse(new_pdf, media_type="application/pdf",
                                    filename=Path(new_pdf).name)

        # 2) Fallback générique ReportLab (si jamais pas d’HTML)
        pdf_bytes = make_pdf_from_deliverable(d)
        filename = f'{(d.title or d.kind).replace("/", "-")}.pdf'
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'}
        )