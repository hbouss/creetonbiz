# backend/routers/premium.py
from fastapi import APIRouter, Depends, HTTPException, Query
from backend.schemas import (
    ProfilRequest, OfferResponse, BusinessModelResponse, BrandResponse,
    LandingResponse, MarketingResponse, PlanResponse
)
from backend.services.premium_service import (
    generate_offer, generate_brand,
    generate_landing, generate_marketing, generate_plan, check_domains_availability as check_domains_namecheap,
    generate_acquisition_structured_for_marketing, generate_business_plan_structured,
)
from backend.dependencies import require_startnow
from backend.services.deliverable_service import (save_deliverable, write_landing_file, render_offer_report_html,
                                                  render_brand_report_html, render_acquisition_report_html,
                                                  render_business_plan_html,
                                                  export_pdf_from_html)
from backend.db import get_session
from backend.models import Project, User
from backend.services.domain_service import suggest_domains, check_domains_availability as check_domains_domainr
import json

router = APIRouter(prefix="/premium", tags=["premium"])

def _get_project_and_unlock_if_needed(user_id: int, project_id: int) -> Project:
    """
    - Vérifie l'accès au projet
    - Décrémente 1 crédit au premier appel premium (si pas encore débloqué)
    - Retourne TOUJOURS l'objet Project (avec idea_snapshot)
    """
    with get_session() as s:
        proj = s.get(Project, project_id)
        if not proj or proj.user_id != user_id:
            raise HTTPException(status_code=404, detail="Projet introuvable ou non autorisé")

        if not proj.premium_unlocked:
            me = s.get(User, user_id)
            if (me.startnow_credits or 0) <= 0:
                raise HTTPException(status_code=402, detail="Crédit StartNow insuffisant pour ce projet")
            # Débloque et consomme 1 crédit
            me.startnow_credits -= 1
            proj.premium_unlocked = True
            s.add_all([me, proj])
            s.commit()
            s.refresh(proj)

        # ⚠️ On renvoie toujours le projet, qu’il soit déjà débloqué ou non
        return proj

@router.post("/offer", response_model=OfferResponse)
async def offer_endpoint(
    profil: ProfilRequest,
    project_id: int = Query(..., gt=0),
    user=Depends(require_startnow),
):
    proj = _get_project_and_unlock_if_needed(user.id, project_id)

    # 1) Génère l'offre (data.offer est une STRING JSON)
    data = await generate_offer(profil, idea_snapshot=proj.idea_snapshot)

    # 2) Parse l'objet "offer"
    try:
        offer_obj = json.loads(data.offer)
    except Exception:
        offer_obj = {}

    # 3) Rendu HTML (avec reprise VERBATIM éventuelle de l’idée)
    idea_text = None
    if isinstance(proj.idea_snapshot, dict):
        idea_text = proj.idea_snapshot.get("idee")

    html = render_offer_report_html(
        offer=offer_obj,
        persona=data.persona,
        pain_points=data.pain_points,
        project_title=f"Offre — {proj.title}",
        idea_text=idea_text,
    )

    # 4) Écriture HTML + 5) Export PDF identique au HTML
    fp_html = write_landing_file(user.id, html)
    pdf_path = await export_pdf_from_html(fp_html, format_="A4")

    # 6) Sauvegarde livrable complet (JSON + chemins)
    json_obj = {
        "structured_offer": offer_obj,
        "persona": data.persona,
        "pain_points": data.pain_points,
        "pdf_path": pdf_path,  # 👈 important
    }
    save_deliverable(
        user.id,
        "offer",
        json_obj,
        title=f"Offre — {proj.title}",
        file_path=fp_html,  # chemin HTML affichable
        project_id=project_id,
    )
    return data

@router.post("/model", response_model=BusinessModelResponse)
async def model_endpoint(
    profil: ProfilRequest,
    project_id: int = Query(..., gt=0),
    user=Depends(require_startnow),
):
    proj = _get_project_and_unlock_if_needed(user.id, project_id)

    # 1) Génère un BP structuré (data lourde)
    bp = await generate_business_plan_structured(profil, idea_snapshot=proj.idea_snapshot)

    # 2) Rendu HTML (≈20 pages) + PDF Playwright
    idea_text = proj.idea_snapshot.get("idee") if isinstance(proj.idea_snapshot, dict) else None
    html = render_business_plan_html(bp, project_title=f"Business Plan — {proj.title}", idea_text=idea_text)

    fp_html = write_landing_file(user.id, html)
    pdf_path = await export_pdf_from_html(fp_html, format_="A4")

    # 3) Sauvegarde livrable (JSON complet + chemins)
    save_deliverable(
        user.id, "model",
        {"business_plan": bp, "pdf_path": pdf_path},
        title="Business Plan",
        file_path=fp_html,
        project_id=project_id,
    )

    # 4) Réponse compatible (pas besoin de changer schemas)
    return BusinessModelResponse(model="Business plan généré. Télécharge le PDF depuis le livrable.")

@router.post("/brand", response_model=BrandResponse)
async def brand_endpoint(
    profil: ProfilRequest,
    project_id: int = Query(..., gt=0),
    user=Depends(require_startnow),
):
    proj = _get_project_and_unlock_if_needed(user.id, project_id)
    data = await generate_brand(profil, idea_snapshot=proj.idea_snapshot)

    # Récupérer le bloc structuré (même logique que generate_brand) pour le stocker
    from backend.services.premium_service import _ask_brand_structured, _profil_dump, _verbatim_block, _parse_json_strict
    structured = await _ask_brand_structured(profil, proj.idea_snapshot)
    # complétion côté serveur au cas où
    from backend.services.premium_service import _ensure_brand_completeness
    structured = _ensure_brand_completeness(structured)

    # -- Étape 3 : suggestions & vérification multi-TLD
    # Suggère quelques domaines pertinents
    suggestions = suggest_domains(data.brand_name, tlds=[".com", ".io", ".co", ".fr"])
    # Assure que le domaine principal proposé apparaît aussi dans la liste
    if data.domain and data.domain.lower() not in {d.lower() for d in suggestions}:
        suggestions = [data.domain] + suggestions

    # Vérifie les domaines : Domainr en priorité, Namecheap en fallback
    domain_checks = await check_domains_domainr(suggestions)
    if all(v is None for v in (domain_checks or {}).values()):
        domain_checks = await check_domains_namecheap(suggestions)


    idea_text = proj.idea_snapshot.get("idee") if isinstance(proj.idea_snapshot, dict) else None
    html = render_brand_report_html(
        brand_name=data.brand_name,
        slogan=data.slogan,
        domain=data.domain,
        domain_available=data.domain_available,
        structured=structured,
        project_title=f"Brand Book — {proj.title}",
        idea_text=idea_text,
        domain_checks=domain_checks,
    )
    # HTML + PDF
    fp_html = write_landing_file(user.id, html)
    pdf_path = await export_pdf_from_html(fp_html, format_="A4")

    json_obj = {
        "brand_name": data.brand_name,
        "slogan": data.slogan,
        "domain": data.domain,
        "domain_available": data.domain_available,
        "brand_structured": structured,
        "domain_checks": domain_checks,
        "pdf_path": pdf_path,  # 👈 important
    }
    save_deliverable(
        user.id, "brand", json_obj,
        title="Branding", file_path=fp_html, project_id=project_id
    )
    return data

@router.post("/landing", response_model=LandingResponse)
async def landing_endpoint(
    profil: ProfilRequest,
    project_id: int = Query(..., gt=0),
    user=Depends(require_startnow),
):
    proj = _get_project_and_unlock_if_needed(user.id, project_id)
    data = await generate_landing(profil, idea_snapshot=proj.idea_snapshot)
    html = data.html if hasattr(data, "html") else (data.get("html") if isinstance(data, dict) else "")
    fp = write_landing_file(user.id, html)
    save_deliverable(
        user.id, "landing", {"html_saved": True},
        title="Landing HTML", file_path=fp, project_id=project_id
    )
    return data

@router.post("/marketing", response_model=MarketingResponse)
async def marketing_endpoint(
    profil: ProfilRequest,
    project_id: int = Query(..., gt=0),
    user=Depends(require_startnow),
):
    proj = _get_project_and_unlock_if_needed(user.id, project_id)

    # 1) Retour texte (compatibilité API existante)
    data = await generate_marketing(profil, idea_snapshot=proj.idea_snapshot)

    # 2) Plan structuré pour livret (débutant-friendly + graphiques)
    acq = await generate_acquisition_structured_for_marketing(profil, idea_snapshot=proj.idea_snapshot)

    # 👉 On ajoute les 3 plans texte comme ANNEXES pour qu'ils apparaissent aussi dans le PDF
    acq["annexes"] = {
        "ads_strategy": getattr(data, "ads_strategy", None),
        "seo_plan": getattr(data, "seo_plan", None),
        "social_plan": getattr(data, "social_plan", None),
    }

    idea_text = proj.idea_snapshot.get("idee") if isinstance(proj.idea_snapshot, dict) else None
    html = render_acquisition_report_html(
        acq, project_title=f"Acquisition — {proj.title}", idea_text=idea_text
    )

    # 3) On sauvegarde d'abord l'HTML (bouton existant)
    fp_html = write_landing_file(user.id, html)

    # 4) Export PDF identique au HTML
    pdf_path = await export_pdf_from_html(fp_html, format_="A4")

    # 5) Sauvegarde livrable complet (HTML + JSON + chemin PDF)
    json_obj = (data.model_dump() if hasattr(data, "model_dump") else dict(data))
    json_obj["acquisition_structured"] = acq
    json_obj["pdf_path"] = pdf_path
    save_deliverable(
        user.id, "marketing", json_obj,
        title="Stratégie d'acquisition", file_path=fp_html, project_id=project_id
    )

    return data

@router.post("/plan", response_model=PlanResponse)
async def plan_endpoint(
    profil: ProfilRequest,
    project_id: int = Query(..., gt=0),
    user=Depends(require_startnow),
):
    proj = _get_project_and_unlock_if_needed(user.id, project_id)
    data = await generate_plan(profil, idea_snapshot=proj.idea_snapshot)
    json_obj = data.model_dump() if hasattr(data, "model_dump") else data
    save_deliverable(user.id, "plan", json_obj, title="Plan d'action 4 semaines", project_id=project_id)
    return data