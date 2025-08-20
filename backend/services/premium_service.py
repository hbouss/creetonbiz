# backend/services/premium_service.py
import _uuid
import os
import re
import hashlib
import math
import random
import json, datetime, uuid
from textwrap import dedent
from backend.db import get_session
from backend.models import Deliverable
import html

import httpx
from typing import Optional, Dict, Any, List, Tuple
from sqlmodel import select
from openai import OpenAI
from fastapi import HTTPException, status
from xml.etree import ElementTree as ET
from backend.schemas import (
    ProfilRequest,
    OfferResponse,
    BusinessModelResponse,
    BrandResponse,
    LandingResponse,
    MarketingResponse,
    PlanResponse,
)
from backend.services.market_calibrator import calibrate_market

# Initialise le client OpenAI
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# ─────────────────────────────────────────────────────────────────────────────
# Helpers JSON & VERBATIM
# ─────────────────────────────────────────────────────────────────────────────

def _parse_json_strict(content: str) -> Dict[str, Any]:
    """
    Tente de parser un JSON retourné par le modèle.
    - Supprime d'éventuelles fences ```json ... ```
    - Fallback: extrait la première {...} si nécessaire
    """
    txt = content.strip()
    # retire fences markdown éventuelles
    txt = re.sub(r"^```(?:json)?\s*", "", txt)
    txt = re.sub(r"\s*```$", "", txt).strip()
    try:
        return json.loads(txt)
    except json.JSONDecodeError:
        start = txt.find("{")
        end = txt.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Impossible d'extraire JSON: {content}"
            )
        snippet = txt[start:end+1]
        try:
            return json.loads(snippet)
        except json.JSONDecodeError:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"JSON invalide extrait: {snippet}"
            )

def _verbatim_block(idea_snapshot: Optional[Dict[str, Any]]) -> str:
    """
    Construit un bloc VERBATIM à injecter dans le prompt.
    Tous ces champs doivent être repris strictement à l'identique si utilisés.
    """
    if not idea_snapshot:
        return ""
    def g(k: str) -> str:
        v = idea_snapshot.get(k) or ""
        if isinstance(v, str):
            return v.replace("\n", " ").strip()
        return str(v)
    # on garde 'idee' tel quel en JSON pour éviter toute distorsion
    idee_json = json.dumps(idea_snapshot.get("idee") or "")
    return (
        "\n[VERBATIM_IDEE]\n"
        f'nom: "{g("nom")}"\n'
        f'slogan: "{g("slogan")}"\n'
        f'persona: "{g("persona")}"\n'
        f"idee: {idee_json}\n"
        "RÈGLE: Ces champs doivent être repris EXACTEMENT à l’identique (copier-coller) dès qu’ils apparaissent dans le livrable. "
        "Interdiction de reformuler, corriger ou résumer.\n"
    )

def _profil_dump(profil: ProfilRequest) -> Dict[str, Any]:
    return profil.model_dump() if hasattr(profil, "model_dump") else dict(profil)

def _competences_str(profil: ProfilRequest) -> str:
    d = _profil_dump(profil)
    comps = d.get("competences") or []
    if isinstance(comps, list):
        return ", ".join(str(x) for x in comps)
    return str(comps)

def _non_empty_str(x: Any) -> bool:
    return isinstance(x, str) and x.strip() != ""

def _looks_hex(s: str) -> bool:
    return bool(re.fullmatch(r"#(?:[0-9a-fA-F]{6}|[0-9a-fA-F]{3})", s or ""))

def _fallback_palette() -> List[Dict[str, str]]:
    return [
        {"name": "Primary Indigo", "hex": "#4F46E5", "usage": "Titres, éléments clés"},
        {"name": "Slate", "hex": "#1F2937", "usage": "Fond sombre"},
        {"name": "Sky", "hex": "#0EA5E9", "usage": "Accents"},
        {"name": "Zinc", "hex": "#A1A1AA", "usage": "Texte secondaire"},
    ]

# --- ajoute ce helper en haut, avec les autres helpers ---
def _to_str(x: Any) -> str:
    if x is None:
        return ""
    if isinstance(x, str):
        return x
    if isinstance(x, (int, float, bool)):
        return str(x)
    if isinstance(x, dict):
        # joli flatten "clé: valeur" si possible, sinon JSON
        try:
            return " | ".join(f"{k}: {v}" for k, v in x.items())
        except Exception:
            pass
    if isinstance(x, list):
        try:
            return ", ".join(_to_str(v) for v in x)
        except Exception:
            pass
    # fallback
    import json
    try:
        return json.dumps(x, ensure_ascii=False)
    except Exception:
        return str(x)

# ─────────────────────────────────────────────────────────────────────────────
# OFFRE
# ─────────────────────────────────────────────────────────────────────────────

async def generate_offer(profil: ProfilRequest, idea_snapshot: Optional[Dict[str, Any]] = None) -> OfferResponse:
    """
    Retour JSON STRICT avec exactement:
      - offer (string JSON)  ← livret structuré mais renvoyé en string (option 1)
      - persona (string)     ← identique au VERBATIM si fourni
      - pain_points (list[str])
    """
    # Helpers existants de ton fichier
    verbatim = _verbatim_block(idea_snapshot)
    p = _profil_dump(profil)

    system_msg = dedent("""\
        Tu es un cabinet de conseil go-to-market. Réponds en FRANÇAIS et UNIQUEMENT en JSON valide (aucun texte autour).
        Clés AUTORISÉES à la racine: "offer", "persona", "pain_points".
        "offer" DOIT contenir exactement ces sous-clés :
          - market_overview: {volume, current_state, trends[], products_services[], main_players[]}
          - demand_analysis: {segments[], customer_count_trend, locations[], behaviors[], choice_criteria[], budget}
          - competitor_analysis: {direct[], indirect[], differentiation_points[], success_factors[], failures_lessons[]}
          - environment_regulation: {innovations[], tech_evolution_pace, regulatory_framework[], associations[], entry_barriers[]}
          - synthesis: string
        EXIGENCES DE QUALITÉ (style livret) :
          - Phrases courtes, précises, orientées décision.
          - Évite le jargon. Pas de chiffres inventés : utilise des ordres de grandeur QUALITATIFS (faible / modéré / élevé).
          - Chaque liste: 3–6 puces maximum, chacune percutante.
          - "synthesis": 6–10 phrases, lisible comme une conclusion exécutive.
        NE PAS ajouter d'autres clés.
    """)

    user_msg = dedent(f"""\
        CONTEXTE
        - Secteur : {p.get('secteur')}
        - Objectif : {p.get('objectif')}
        - Compétences : {_competences_str(profil)}

        {verbatim}

        CONTRAINTES SUPPLÉMENTAIRES
        - Si un VERBATIM est présent, réutilise le texte de l'IDÉE MOT POUR MOT (pas de reformulation) pour cadrer l'analyse.
        - Si le VERBATIM contient un persona, la clé "persona" doit être STRICTEMENT identique.
        - "pain_points": 5 à 7 éléments, chacun très court.

        FORMAT ATTENDU (JSON strict uniquement) :
        {{
          "offer": {{
            "market_overview": {{
              "volume": "ordre de grandeur qualitatif (faible/modéré/élevé) + justification en 1–2 phrases",
              "current_state": "progression | régression | stagnation (qualitatif + raisons)",
              "trends": ["tendance 1", "tendance 2", "tendance 3"],
              "products_services": ["catégorie 1", "catégorie 2", "catégorie 3"],
              "main_players": ["acteur A", "acteur B", "acteur C"]
            }},
            "demand_analysis": {{
              "segments": ["segment 1", "segment 2", "segment 3"],
              "customer_count_trend": "en hausse | en baisse | stable (qualitatif)",
              "locations": ["zone 1", "zone 2"],
              "behaviors": ["moment clé", "habitude", "motivation", "niveau de satisfaction"],
              "choice_criteria": ["prix", "qualité", "distribution", "service"],
              "budget": "faible | moyen | élevé (qualitatif)"
            }},
            "competitor_analysis": {{
              "direct": [{{"name":"Concurr 1","positioning":"...","strengths":"...","weaknesses":"..."}}, {{"name":"Concurr 2","positioning":"...","strengths":"...","weaknesses":"..."}}],
              "indirect": ["substitut 1", "substitut 2"],
              "differentiation_points": ["levier 1", "levier 2", "levier 3"],
              "success_factors": ["facteur 1", "facteur 2", "facteur 3"],
              "failures_lessons": ["leçon 1", "leçon 2", "leçon 3"]
            }},
            "environment_regulation": {{
              "innovations": ["innovation 1", "innovation 2"],
              "tech_evolution_pace": "lent | modéré | rapide",
              "regulatory_framework": ["règle/texte 1", "règle/texte 2"],
              "associations": ["organisme 1", "organisme 2"],
              "entry_barriers": ["barrière 1", "barrière 2"]
            }},
            "synthesis": "Conclusion en 6–10 phrases, réunissant marché, demande, concurrence, environnement, et angle distinctif."
          }},
          "persona": "1–2 lignes (rôle + contexte d’usage)",
          "pain_points": ["point 1", "point 2", "point 3", "point 4", "point 5"]
        }}
    """)

    resp = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": system_msg},
            {"role": "user",   "content": user_msg},
        ],
        temperature=0.5,
        top_p=0.9,
        presence_penalty=0.1,
        frequency_penalty=0.1,
        max_tokens=1400,
        response_format={"type": "json_object"},
    )

    data = _parse_json_strict(resp.choices[0].message.content)

    # Normalisation pain_points
    pp = data.get("pain_points")
    if isinstance(pp, str):
        lines = [ln.strip("-• ").strip() for ln in pp.splitlines() if ln.strip()]
        data["pain_points"] = lines
    elif isinstance(pp, list):
        data["pain_points"] = [str(x).strip() for x in pp if str(x).strip()]
    else:
        data["pain_points"] = []

    # Persona: forcer le VERBATIM si présent
    if idea_snapshot and idea_snapshot.get("persona"):
        data["persona"] = idea_snapshot["persona"]
    else:
        data["persona"] = _to_str(data.get("persona"))

    # Robustesse: garantir toutes les sous-sections
    offer_obj = data.get("offer") or {}
    offer_obj.setdefault("market_overview", {})
    offer_obj.setdefault("demand_analysis", {})
    offer_obj.setdefault("competitor_analysis", {})
    offer_obj.setdefault("environment_regulation", {})
    offer_obj.setdefault("synthesis", "")

    # 👉 Option 1 : renvoyer 'offer' en STRING (attendu par OfferResponse)
    data["offer"] = json.dumps(offer_obj, ensure_ascii=False)

    missing = [k for k in ("offer", "persona", "pain_points") if k not in data]
    if missing:
        raise HTTPException(status_code=500, detail=f"Clés manquantes: {missing}")

    return OfferResponse(**data)

# ─────────────────────────────────────────────────────────────────────────────
# BUSINESS MODEL
# ─────────────────────────────────────────────────────────────────────────────

async def generate_business_model(profil: ProfilRequest, idea_snapshot: Optional[Dict[str, Any]] = None) -> BusinessModelResponse:
    """
    Retour JSON STRICT avec exactement:
      - model (string) : structure claire, alignée avec l'idée VERBATIM
    """
    p = _profil_dump(profil)
    prompt = (
        "Réponds EXCLUSIVEMENT par un JSON brut avec EXACTEMENT la clé 'model'.\n"
        "CONTRAINTES:\n"
        "- Le model doit refléter l'idee du VERBATIM sans la reformuler (base textuelle et dénominations constantes).\n"
        "- Une seule clé 'model'. Aucune autre clé.\n"
        + _verbatim_block(idea_snapshot) +
        f"\n[PROFIL] secteur={p.get('secteur')} • objectif={p.get('objectif')}"
    )

    resp = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.5,
        max_tokens=350,
    )
    data = _parse_json_strict(resp.choices[0].message.content)
    if "model" not in data:
        raise HTTPException(status_code=500, detail="Clé 'model' manquante dans la réponse JSON")
    return BusinessModelResponse(model=str(data["model"]))

# ─────────────────────────────────────────────────────────────────────────────
# BRAND (utilise directement le VERBATIM si disponible)
# ─────────────────────────────────────────────────────────────────────────────

def _ensure_brand_completeness(b: dict) -> dict:
    # Force toutes les sections et champs attendus
    b = dict(b or {})
    b.setdefault("mission", "Clarifier la raison d’être pour créer de la valeur réelle.")
    b.setdefault("vision", "Devenir une référence durable et reconnue sur notre marché.")
    vals = b.get("values") or []
    if not isinstance(vals, list) or len(vals) < 3:
        b["values"] = ["Simplicité", "Fiabilité", "Impact client"]

    pal = b.get("color_palette") or []
    # normaliser hex, injecter fallback si vide/incorrect
    valid_pal = []
    for c in pal if isinstance(pal, list) else []:
        hx = c.get("hex")
        if _looks_hex(str(hx)):
            valid_pal.append({"name": c.get("name") or "Couleur", "hex": hx, "usage": c.get("usage") or "Usage principal"})
    if not valid_pal:
        valid_pal = _fallback_palette()
    b["color_palette"] = valid_pal

    typo = b.get("typography") or {}
    if not isinstance(typo, dict):
        typo = {}
    typo.setdefault("primary", {"font": "Inter", "usage": "Titres et UI"})
    typo.setdefault("secondary", {"font": "Inter", "usage": "Corps de texte"})
    b["typography"] = typo

    logo = b.get("logo_guidelines") or {}
    if not isinstance(logo, dict):
        logo = {}
    logo.setdefault("concept", "Signe simple + logotype, facilement déclinable.")
    logo.setdefault("variations", ["Couleur", "Monochrome", "Pictogramme seul"])
    logo.setdefault("clear_space", "Laisser un espace équivalent à la hauteur du pictogramme tout autour.")
    logo.setdefault("min_size", "24 px de hauteur minimum en usage digital.")
    logo.setdefault("dos", ["Respecter la zone de protection", "Préserver les contrastes"])
    logo.setdefault("donts", ["Ne pas étirer", "Ne pas changer les couleurs"])
    # logo_set (propositions avec croquis SVG)
    logo_set = logo.get("logo_set")
    if not isinstance(logo_set, list) or not logo_set:
        # on laissera le renderer générer des croquis d'initiales si absent,
        # mais on met au moins des slots vides pour 3 concepts
        logo["logo_set"] = [
            {"name": "Concept A", "rationale": "Symbole abstrait + mot-symbole.", "sketch_svg": None},
            {"name": "Concept B", "rationale": "Initiales dans un disque.", "sketch_svg": None},
            {"name": "Concept C", "rationale": "Icône minimaliste + tagline.", "sketch_svg": None},
        ]
    b["logo_guidelines"] = logo

    story = b.get("storytelling") or {}
    if not isinstance(story, dict):
        story = {}
    story.setdefault("origins", "Née d’un constat terrain et d’un besoin utilisateur clair.")
    story.setdefault("values_engagement", "Engagement concret: qualité mesurable et relation client soignée.")
    if not isinstance(story.get("proof_points"), list) or not story["proof_points"]:
        story["proof_points"] = ["Retours utilisateurs positifs", "Premier POC concluant", "Cas d’usage reproductibles"]
    b["storytelling"] = story

    cons = b.get("consistency") or {}
    if not isinstance(cons, dict):
        cons = {}
    cons.setdefault("social", "Palette cohérente, templates réutilisables, ton clair.")
    cons.setdefault("emails", "Header avec logo, typographies de la charte, boutons consistants.")
    cons.setdefault("documents", "Gabarits pour brochures, pitch decks et fiches produit.")
    b["consistency"] = cons

    return b

async def _ask_brand_structured(profil: ProfilRequest, idea_snapshot: Optional[Dict[str, Any]]) -> dict:
    p = _profil_dump(profil)
    prompt = (
        "Tu es directeur de création & stratégie de marque. Réponds en FRANÇAIS et UNIQUEMENT par un JSON valide (aucun texte hors JSON).\n"
        "Clé racine UNIQUE: 'brand_structured'.\n"
        "'brand_structured' DOIT contenir:\n"
        "  mission (string), vision (string), values (liste 3–6),\n"
        "  color_palette (liste 3–5 objets {name, hex, usage}, hex au format #RRGGBB),\n"
        "  typography ({primary:{font,usage}, secondary:{font,usage}}),\n"
        "  logo_guidelines: {concept, variations[], clear_space, min_size, dos[], donts[], logo_set[]},\n"
        "  storytelling: {origins, values_engagement, proof_points[]},\n"
        "  consistency: {social, emails, documents}.\n"
        "Contraintes: pas de valeurs vides ni 'à définir'.\n"
        + _verbatim_block(idea_snapshot) +
        f"\nContexte: secteur={p.get('secteur')} • objectif={p.get('objectif')} • compétences={_competences_str(profil)}"
    )
    resp = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.55,
        top_p=0.9,
        max_tokens=1400,
        response_format={"type": "json_object"},
    )
    data = _parse_json_strict(resp.choices[0].message.content)
    return data.get("brand_structured") or {}

async def check_domains_availability(domains: List[str]) -> Dict[str, Optional[bool]]:
    """
    Vérifie la disponibilité de plusieurs domaines via Namecheap.
    Retourne { "foo.com": True|False|None, ... }  (None si non vérifié).
    """
    api_user = os.getenv("NAMECHEAP_USER")
    api_key = os.getenv("NAMECHEAP_KEY")
    client_ip = os.getenv("CLIENT_IP")
    if not (api_user and api_key and client_ip) or not domains:
        # pas de credentials => on renvoie 'None' partout
        return {d: None for d in domains}

    # Namecheap accepte une liste CSV
    domain_list = ",".join(domains)
    url = (
        "https://api.namecheap.com/xml.response"
        f"?ApiUser={api_user}&ApiKey={api_key}&UserName={api_user}"
        f"&ClientIp={client_ip}&Command=namecheap.domains.check&DomainList={domain_list}"
    )
    out: Dict[str, Optional[bool]] = {d: None for d in domains}
    async with httpx.AsyncClient(timeout=20) as http:
        r = await http.get(url)
    try:
        tree = ET.fromstring(r.text)
        for node in tree.findall(".//DomainCheckResult"):
            dom = node.get("Domain")
            av  = node.get("Available")
            if dom is not None and av is not None:
                out[dom] = (av.lower() == "true")
    except Exception:
        # en cas d'erreur XML, on garde None
        pass
    return out

async def generate_brand(profil: ProfilRequest, idea_snapshot: Optional[Dict[str, Any]] = None) -> BrandResponse:
    # 1) Nom/slogan (VERBATIM prioritaire, sinon génération)
    brand_name = (idea_snapshot or {}).get("nom")
    slogan = (idea_snapshot or {}).get("slogan")
    if not brand_name or not slogan:
        p = _profil_dump(profil)
        prompt_min = (
            "Réponds EXCLUSIVEMENT par un JSON brut avec EXACTEMENT les clés 'brand_name' et 'slogan'. "
            "Aucune autre clé. Aucun Markdown.\n"
            + _verbatim_block(idea_snapshot) +
            f"\n[PROFIL] secteur={p.get('secteur')} • objectif={p.get('objectif')}"
        )
        resp = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt_min}],
            temperature=0.5,
            max_tokens=120,
            response_format={"type": "json_object"},
        )
        data_min = _parse_json_strict(resp.choices[0].message.content)
        if not _non_empty_str(data_min.get("brand_name")) or not _non_empty_str(data_min.get("slogan")):
            raise HTTPException(status_code=500, detail="Échec génération nom/slogan")
        brand_name, slogan = data_min["brand_name"], data_min["slogan"]

    if idea_snapshot:
        brand_name = idea_snapshot.get("nom") or brand_name
        slogan = idea_snapshot.get("slogan") or slogan

    # 2) Bloc structuré (avec 2 tentatives + complétion côté serveur)
    structured = await _ask_brand_structured(profil, idea_snapshot)
    if not structured:
        structured = await _ask_brand_structured(profil, idea_snapshot)
    structured = _ensure_brand_completeness(structured)

    # 3) Optionnel: disponibilité du domaine
    domain = (brand_name or "").replace(" ", "") + ".com"
    api_user = os.getenv("NAMECHEAP_USER")
    api_key = os.getenv("NAMECHEAP_KEY")
    client_ip = os.getenv("CLIENT_IP")
    available = None
    if api_user and api_key and client_ip:
        url = (
            "https://api.namecheap.com/xml.response"
            f"?ApiUser={api_user}&ApiKey={api_key}&UserName={api_user}"
            f"&ClientIp={client_ip}&Command=namecheap.domains.check&DomainList={domain}"
        )
        async with httpx.AsyncClient() as http:
            r = await http.get(url)
        try:
            tree = ET.fromstring(r.text)
            available = tree.find(".//DomainCheckResult").get("Available") == "true"
        except Exception:
            available = None

    # 4) On stockera 'structured' dans le livrable JSON depuis l'endpoint (voir premium.py)
    return BrandResponse(
        brand_name=brand_name,
        slogan=slogan,
        domain=domain,
        domain_available=available,
    )
# ─────────────────────────────────────────────────────────────────────────────
# LANDING
# ─────────────────────────────────────────────────────────────────────────────

from typing import Optional
import base64, mimetypes, os
from pydantic import BaseModel, Field


# Ton modèle existant :
class LandingResponse(BaseModel):
    html: str

def _as_data_uri_from_path(path: str | None) -> str | None:
    if not path or not os.path.exists(path):
        return None
    mime, _ = mimetypes.guess_type(path)
    mime = mime or "application/octet-stream"
    with open(path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("utf-8")
    return f"data:{mime};base64,{b64}"

def _esc(x):
    try:
        return html.escape(str(x if x is not None else ""))
    except Exception:
        return str(x)

def _latest_deliverable(project_id: int, kind: str):
    with get_session() as s:
        return (
            s.query(Deliverable)
             .filter(Deliverable.project_id == project_id, Deliverable.kind == kind)
             .order_by(Deliverable.id.desc())
             .first()
        )

def _unique(items, limit=None):
    out = []
    for x in items or []:
        xs = (x or "").strip()
        if xs and xs.lower() not in {z.lower() for z in out}:
            out.append(xs)
            if limit and len(out) >= limit:
                break
    return out

def _round_price(x: float, step: int = 1):
    try:
        v = float(x)
    except Exception:
        return 0
    # arrondi « propre »
    return int(round(v / step) * step)

def _synth_content_for_landing(project_id: int, fallback_price: float | int = 29):
    """
    Construit tous les textes/sections de la landing à partir des livrables existants.
    Retourne un dict:
      { 'headline', 'subhead', 'benefits', 'features', 'use_cases',
        'pricing': [ {name, price, bullets}, ... ],
        'faq': [ (q, a), ... ],
        'testimonials': [ "…", "…" ] }
    """
    idea = _latest_deliverable(project_id, "offer")
    brand = _latest_deliverable(project_id, "brand")
    model = _latest_deliverable(project_id, "model")  # business plan structuré

    idea_j = (idea.json_content or {}) if idea else {}
    brand_j = (brand.json_content or {}) if brand else {}
    model_j = (model.json_content or {}) if model else {}

    # — Idée / persona / pains / features
    persona = idea_j.get("persona") or (idea_j.get("structured_offer", {}) or {}).get("persona") or ""
    pains   = idea_j.get("pain_points") or []
    s_offer = idea_j.get("structured_offer") or {}

    # Features candidates depuis plusieurs champs
    features = []
    features += s_offer.get("competitor_analysis", {}).get("differentiation_points", []) or []
    features += s_offer.get("market_overview", {}).get("products_services", []) or []
    features += s_offer.get("demand_analysis", {}).get("choice_criteria", []) or []
    # fallback : transformer les pain points en bénéfices
    if not features and pains:
        features = [f"Résout : {p}" for p in pains]

    features = _unique(features, limit=9)

    # Bénéfices (courts)
    benefits = []
    if pains:
        benefits = _unique([f"Élimine « {p} »" for p in pains], limit=5)
    if not benefits and features:
        benefits = _unique([f"Valeur : {f}" for f in features], limit=5)

    # Use cases simples (si segments/locations)
    segs = s_offer.get("demand_analysis", {}).get("segments", []) or []
    locs = s_offer.get("demand_analysis", {}).get("locations", []) or []
    use_cases = _unique([f"{s} à {l}" for s in segs for l in (locs or ["France"])], limit=4) or _unique(segs, limit=4)

    # — Prix de référence depuis le business plan
    bp = model_j.get("business_plan") or {}
    assumptions = bp.get("assumptions") or {}
    base_price = assumptions.get("price") or fallback_price
    base_price = _round_price(base_price, step=1)

    # 3 paliers
    price_starter = max(5, _round_price(base_price * 0.6))
    price_pro     = max(price_starter + 1, _round_price(base_price))
    price_ent     = max(price_pro + 1, _round_price(base_price * 2.2))

    # Bullets de tarifs à partir des features (on répartit automatiquement)
    f_starter = features[:3] if len(features) >= 3 else features[:]
    f_pro     = features[:6] if len(features) >= 6 else features[:]
    f_ent     = features[:9] if len(features) >= 9 else features[:]

    pricing = [
        {"name": "Starter",   "price": f"{price_starter} € / mois", "bullets": f_starter or ["Pour démarrer"]},
        {"name": "Pro",       "price": f"{price_pro} € / mois",     "bullets": f_pro or ["Fonctionnalités clés"]},
        {"name": "Entreprise","price": "Sur devis",                 "bullets": f_ent or ["SSO, SLA, onboarding…"]},
    ]

    # FAQ (générées à partir du contexte)
    faq = [
        ("Puis-je essayer gratuitement ?", "Oui, jusqu’à 14 jours sans carte bancaire."),
        ("Mes données sont-elles RGPD ?", "Oui, hébergement UE et DPA sur demande."),
        ("Quel accompagnement ?", "Onboarding, support email et aide à l’import de données."),
    ]
    if persona:
        faq.insert(0, (f"En quoi cela aide {persona} ?", "Nous adressons directement ses principaux irritants et offrons des gains rapides."))

    # Témoignages courts (placeholder « marketing » propre)
    testimonials = [
        "“Mise en place rapide et ROI clair.” — Utilisateur pilote",
        "“L’équipe est réactive, super expérience.” — Client beta",
    ]

    # Headline / subhead
    brand_name = brand_j.get("brand_name") or idea_j.get("nom") or "Votre Marque"
    slogan     = brand_j.get("slogan")     or idea_j.get("slogan") or "Votre slogan"
    headline   = f"{brand_name} — {slogan}"
    subhead    = idea_j.get("offer") or s_offer.get("synthesis") or idea_j.get("structured_offer", {}).get("synthesis") \
                 or "Solution prête à l’emploi pour votre besoin."

    return {
        "brand_name": brand_name,
        "slogan": slogan,
        "headline": headline,
        "subhead": subhead,
        "persona": persona,
        "benefits": benefits,
        "features": features,
        "use_cases": use_cases,
        "pricing": pricing,
        "faq": faq,
        "testimonials": testimonials,
    }

# Ton modèle existant
class LandingResponse(BaseModel):
    html: str

# Nouveau: schéma de copy généré par GPT (textes uniquement)
class PricingTier(BaseModel):
    name: str
    price_per_month_eur: Optional[int] = None  # None pour "Sur devis"
    bullets: list[str] = Field(default_factory=list)
    cta: str = "Choisir"

class LandingCopy(BaseModel):
    hero_title: str
    hero_subtitle: str
    hero_bullets: list[str] = Field(default_factory=list)
    segments_badges: list[str] = Field(default_factory=list)

    features: list[dict] = Field(default_factory=list)        # [{title, desc}]
    differentiators: list[str] = Field(default_factory=list)  # ["..."]

    pricing: dict = Field(default_factory=dict)               # {starter, pro, enterprise} -> PricingTier-like
    trust_points: list[str] = Field(default_factory=list)     # ["RGPD...", "Hébergement UE...", ...]

    testimonials: list[dict] = Field(default_factory=list)    # [{quote, name, role}]
    faq: list[dict] = Field(default_factory=list)             # [{q, a}]

def _safe_json_loads(s: str) -> dict:
    try:
        return json.loads(s)
    except Exception:
        # tente d’extraire un JSON minimal
        start = s.find("{")
        end = s.rfind("}")
        if start >= 0 and end > start:
            return json.loads(s[start:end+1])
        raise

    # -------- Helpers pricing (NIVEAU MODULE) --------

# --- Helpers marché ----------------------------------------------------------
def _saas_segment(sector: str, idea: Optional[dict] = None) -> str:
    s = (sector or "").lower()
    if idea:
        # concatène quelques champs si dispo pour enrichir la détection
        s += " " + " ".join(str(x) for x in (
            idea.get("idee") or "",
            " ".join(idea.get("products_services") or []),
            " ".join(idea.get("differentiation_points") or []),
        )).lower()
    m = {
        "crm": "crm", "vente": "crm", "sales": "crm",
        "project": "pm", "gestion de projet": "pm", "kanban": "pm",
        "helpdesk": "helpdesk", "support": "helpdesk", "service client": "helpdesk", "ticket": "helpdesk",
        "analytics": "analytics", "bi": "analytics", "reporting": "analytics",
        "hr": "hr", "rh": "hr", "paie": "hr", "congés": "hr", "planning": "hr",
        "recrut": "ats", "ats": "ats",
        "sécur": "security", "cyber": "security", "iam": "security",
        "dev": "devtools", "developer": "devtools", "ci/cd": "devtools", "monitor": "devtools",
        "ecom": "ecom_tools", "e-commerce": "ecom_tools", "shopify": "ecom_tools",
        "finance": "finops", "compta": "finops", "facturation": "finops", "invoic": "finops",
        "data": "data_platform", "etl": "data_platform", "warehouse": "data_platform",
        "santé": "health", "medical": "health", "clinique": "health",
    }
    for k, v in m.items():
        if k in s:
            return v
    return "generic"

_SAAS_BENCH = {
    # fourchettes indicatives mensuelles / utilisateur ou compte selon segment
    "crm":            {"starter": (9, 29),   "pro": (29, 79),   "ent_mul": 2.5},
    "pm":             {"starter": (6, 19),   "pro": (20, 49),   "ent_mul": 2.2},
    "helpdesk":       {"starter": (12, 29),  "pro": (29, 79),   "ent_mul": 2.4},
    "analytics":      {"starter": (15, 39),  "pro": (39, 99),   "ent_mul": 2.5},
    "hr":             {"starter": (39, 99),  "pro": (99, 199),  "ent_mul": 2.0},
    "ats":            {"starter": (49, 129), "pro": (129, 249), "ent_mul": 2.0},
    "security":       {"starter": (99, 199), "pro": (199, 399), "ent_mul": 2.0},  # souvent par compte/site
    "devtools":       {"starter": (5, 19),   "pro": (19, 49),   "ent_mul": 2.2},
    "ecom_tools":     {"starter": (9, 29),   "pro": (29, 79),   "ent_mul": 2.0},
    "finops":         {"starter": (19, 59),  "pro": (59, 149),  "ent_mul": 2.2},
    "data_platform":  {"starter": (49, 149), "pro": (149, 299), "ent_mul": 2.0},
    "health":         {"starter": (49, 149), "pro": (149, 299), "ent_mul": 2.2},
    "generic":        {"starter": (9, 39),   "pro": (39, 99),   "ent_mul": 2.2},
}

def _price_charm_9(x: float) -> int:
    v = int(round(float(x)))
    if v <= 9: return v
    # pousse vers 9 quand c’est pertinent
    return (v // 10) * 10 + 9 if v % 10 not in (9,) else v

def _stable_jitter(key: str, base: float, pct: float = 0.08) -> float:
    seed = int(hashlib.md5(key.encode("utf-8")).hexdigest()[:8], 16)
    rnd = random.Random(seed)
    return base * (1.0 + rnd.uniform(-pct, pct))

def _extract_competitive_corridor(idea: Optional[dict]) -> tuple[Optional[float], Optional[float]]:
    """
    Cherche des prix dans l’offer/competitor_analysis s’ils existent.
    Retourne (p25, p75) pour serrer le corridor marché.
    Schémas tolérés: competitors:[{price|price_min|price_max|starter|pro|...}]
    """
    if not idea:
        return (None, None)
    candidates = []
    paths = [
        idea.get("competitors"),
        (idea.get("structured_offer") or {}).get("competitor_analysis", {}).get("competitors"),
        (idea.get("competitor_analysis") or {}).get("competitors"),
        (idea.get("structured_offer") or {}).get("competitor_analysis", {}).get("prices"),
    ]
    for arr in paths:
        if isinstance(arr, list):
            for c in arr:
                if not isinstance(c, dict): continue
                for k in ("price","price_min","price_max","starter_price","pro_price","prix","tarif"):
                    v = c.get(k)
                    try:
                        if v is None: continue
                        # gère "49 €", "49/mois"
                        if isinstance(v, str):
                            vv = "".join(ch for ch in v if (ch.isdigit() or ch == "."))
                            if not vv: continue
                            v = float(vv)
                        candidates.append(float(v))
                    except Exception:
                        pass
    if len(candidates) >= 3:
        candidates.sort()
        p25 = candidates[int(0.25 * (len(candidates)-1))]
        p75 = candidates[int(0.75 * (len(candidates)-1))]
        return (p25, p75)
    return (None, None)

# --- NOUVELLE VERSION : pricing basé marché + BP ----------------------------
def _compute_pricing_from_bp(
    bp: Optional[dict],
    sector: str,
    base_price: Optional[float],
    objective: Optional[str],
    project_id: Optional[int],
    idea_snapshot: Optional[dict] = None,   # ← optionnel, si dispo on lit les prix concurrents
) -> dict:
    seg = _saas_segment(sector, idea_snapshot)
    bench = _SAAS_BENCH.get(seg, _SAAS_BENCH["generic"])

    # corridor bench (starter/pro)
    s_lo, s_hi = bench["starter"]
    p_lo, p_hi = bench["pro"]

    # corridor concurrentiel (si dispo) pour resserrer encore
    c25, c75 = _extract_competitive_corridor(idea_snapshot)
    if c25 and c75:
        # on ne laisse pas le corridor sortir des bornes bench
        p_lo = max(p_lo, int(c25))
        p_hi = min(p_hi, int(c75))

    # contraintes BP
    cal = (bp or {}).get("calibration_used") or {}
    arpu   = float(cal.get("arpu_month") or base_price or p_lo)
    gm_pct = float(cal.get("gm_pct") or 80.0) / 100.0
    cac    = float(cal.get("cac_blended") or 80.0)

    obj = (objective or "").lower()
    aggressive = any(k in obj for k in ("venture","hyper","agress","scale","levée","seed","série","x2"))
    payback_months = 6 if aggressive else 9

    # plancher par payback
    floor_payback = cac / max(0.01, gm_pct * payback_months)

    # Pro = max(ARPU, floor_payback) puis clamp au corridor pro
    pro_raw = max(arpu, floor_payback)
    pro_raw = _stable_jitter(f"prj:{project_id}:pro:{seg}", pro_raw, 0.08)
    pro = max(p_lo, min(_price_charm_9(pro_raw), p_hi))

    # Starter ≈ 55–70% du Pro, clamp au corridor starter
    starter_raw = pro * (0.6 if aggressive else 0.55)
    starter_raw = _stable_jitter(f"prj:{project_id}:starter:{seg}", starter_raw, 0.07)
    starter = max(s_lo, min(_price_charm_9(starter_raw), s_hi))

    pricing = {
        "starter": {
            "name": "Starter",
            "price_per_month_eur": int(starter),
            "bullets": [
                "Jusqu’à 3 utilisateurs",
                "Fonctionnalités essentielles",
                "Support standard",
            ],
            "cta": "Commencer",
        },
        "pro": {
            "name": "Pro",
            "price_per_month_eur": int(pro),
            "bullets": [
                "Utilisateurs illimités",
                "Intégrations & exports",
                "Support prioritaire",
            ],
            "cta": "Essayer Pro",
        },
        "enterprise": {
            "name": "Entreprise",
            "price_per_month_eur": None,   # Sur devis
            "bullets": [
                "SSO & SLA",
                "Environnements dédiés",
                "Accompagnement expert",
            ],
            "cta": "Obtenir un devis",
        },
    }
    return pricing

def _as_data_uri_from_path(path: str | None) -> str | None:
    if not path or not os.path.exists(path):
        return None
    mime, _ = mimetypes.guess_type(path)
    mime = mime or "application/octet-stream"
    with open(path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("utf-8")
    return f"data:{mime};base64,{b64}"

def _landing_sector_category_long(secteur: str | None) -> str:
    s = (secteur or "").lower()
    if any(k in s for k in ["e-com","ecommerce","boutique","retail","shop"]): return "ecommerce_b2c"
    if any(k in s for k in ["saas","logiciel","b2b","crm","erp","data"]):     return "saas_b2b"
    if any(k in s for k in ["industrie","iot","manufact","usine"]):           return "industry_b2b"
    if any(k in s for k in ["mobile","app","application"]):                   return "mobile_app"
    if any(k in s for k in ["service","artisan","local"]):                    return "services_locaux"
    return "generic_b2b"

def _pricing_benchmarks(cat: str) -> dict:
    # bornes FR réalistes par catégorie (fourchettes indicatives)
    return {
        "saas_b2b":       {"base_min": 29, "base_max": 199, "starter_mul": 0.6, "pro_mul": 1.0, "ent_mul": 2.2},
        "ecommerce_b2c":  {"base_min": 19, "base_max": 99,  "starter_mul": 0.6, "pro_mul": 1.0, "ent_mul": 2.0},
        "industry_b2b":   {"base_min": 99, "base_max": 399, "starter_mul": 0.6, "pro_mul": 1.0, "ent_mul": 2.5},
        "mobile_app":     {"base_min": 5,  "base_max": 19,  "starter_mul": 0.6, "pro_mul": 1.0, "ent_mul": 2.2},
        "services_locaux":{"base_min": 39, "base_max": 149, "starter_mul": 0.6, "pro_mul": 1.0, "ent_mul": 2.0},
        "generic_b2b":    {"base_min": 39, "base_max": 199, "starter_mul": 0.6, "pro_mul": 1.0, "ent_mul": 2.2},
    }.get(cat or "generic_b2b")

def _pricing_charm(x: float) -> int:
    # arrondi psychologique → termine en 9 ou 5
    v = int(round(float(x)))
    if v <= 9: return v
    return (v - 1) if (v % 10 in (0,1,2,3,4,6,7,8)) else v  # pousse vers 9

def _project_potential(objectif: str | None) -> float:
    # uplift tarifaire si objectif “agressif”
    s = (objectif or "").lower()
    if any(k in s for k in ["venture", "hyper", "scale", "levée", "x2", "série"]):
        return 1.15  # +15%
    return 1.0

def _compute_pricing_smart(sector: str | None, base_price_hint: float | None, objectif: str | None) -> dict:
    cat = _landing_sector_category_long(sector)
    bench = _pricing_benchmarks(cat)
    base  = float(base_price_hint or bench["base_min"])
    # clamp dans la fourchette du marché
    base  = max(bench["base_min"], min(base, bench["base_max"]))
    # uplift si potentiel élevé
    base *= _project_potential(objectif)

    starter = _pricing_charm(base * bench["starter_mul"])
    pro     = _pricing_charm(base * bench["pro_mul"])
    # Enterprise reste “Sur devis” (mais on calcule une ancre interne si besoin)
    _enterprise_anchor = _pricing_charm(base * bench["ent_mul"])

    return {
        "starter": {
            "name": "Starter",
            "price_per_month_eur": starter,
            "bullets": [
                "Mise en place rapide",
                "Fonctionnalités essentielles",
                "Support standard",
            ],
            "cta": "Commencer",
        },
        "pro": {
            "name": "Pro",
            "price_per_month_eur": pro,
            "bullets": [
                "Fonctionnalités avancées",
                "Intégrations & exports",
                "Support prioritaire",
                "Mises à jour continues",
            ],
            "cta": "Essayer Pro",
        },
        "enterprise": {
            "name": "Entreprise",
            "price_per_month_eur": None,  # sur devis
            "bullets": [
                "SLA & SSO",
                "Environnements dédiés",
                "Accompagnement expert",
                "Gouvernance & sécurité",
            ],
            "cta": "Obtenir un devis",
        },
    }

def _merge_pricing(pref_from_gpt: dict | None, smart: dict) -> dict:
    """
    Conserve la structure GPT si elle existe mais remplace/normalise les prix
    hors bornes par les prix 'smart' sectoriels.
    """
    pref = dict(pref_from_gpt or {})
    out = {}
    for tier in ("starter","pro","enterprise"):
        a = dict(smart.get(tier, {}))
        b = dict((pref.get(tier) or {}))
        # on garde bullets/cta de GPT si fournis, mais on impose le prix calculé
        if tier != "enterprise":
            a["price_per_month_eur"] = a["price_per_month_eur"]
        else:
            a["price_per_month_eur"] = None  # enterprise = sur devis
        if b.get("bullets"): a["bullets"] = b["bullets"]
        if b.get("cta"):     a["cta"]     = b["cta"]
        if b.get("name"):    a["name"]    = b["name"]
        out[tier] = a
    return out

def _compute_pricing_from_base(base_price: Optional[float]) -> dict:
    base = float(base_price or 49)
    starter = int(round(base * 0.60))
    pro = int(round(base * 1.00))
    return {
        "starter": {
            "name": "Starter",
            "price_per_month_eur": starter,
            "bullets": [
                "Démarrage rapide",
                "Support standard",
                "Fonctionnalités essentielles",
            ],
            "cta": "Commencer",
        },
        "pro": {
            "name": "Pro",
            "price_per_month_eur": pro,
            "bullets": [
                "Fonctionnalités avancées",
                "Rapports & exports",
                "Support prioritaire",
                "Intégrations standards",
                "Mises à jour mensuelles",
                "Onboarding guidé",
            ],
            "cta": "Essayer Pro",
        },
        "enterprise": {
            "name": "Entreprise",
            "price_per_month_eur": None,
            "bullets": [
                "SLA & SSO",
                "Intégrations sur mesure",
                "Environnements dédiés",
                "Accompagnement expert",
                "Facturation annuelle",
                "Gouvernance & sécurité",
            ],
            "cta": "Obtenir un devis",
        },
    }

def _fallback_copy(
    brand_name: str, slogan: str, persona: str, idea: str,
    base_price: Optional[float], products: list[str], diffs: list[str], segments: list[str]
) -> LandingCopy:
    return LandingCopy(
        hero_title=f"{brand_name} — {slogan}",
        hero_subtitle=idea or "Solution prête à l’emploi, conçue pour votre marché.",
        hero_bullets=[
            "Mise en place rapide",
            "Gains mesurables dès 30 jours",
            "Support réactif en français",
        ],
        segments_badges=segments[:4] or ["France", "PME", "Indépendants"],
        features=[{"title": p, "desc": "Bénéfice concret et mesurable pour l’utilisateur."} for p in (products[:6] or ["Fonction clé 1","Fonction clé 2"])],
        differentiators=diffs[:5] or ["Simplicité d’usage", "Accompagnement de proximité", "Rapport qualité/prix"],
        pricing=_compute_pricing_from_base(base_price),
        trust_points=[
            "Hébergement en Union Européenne",
            "Conforme RGPD (DPA sur demande)",
            "Chiffrement des données en transit et au repos",
            "Facturation en euros (TVA), CGV disponibles",
        ],
        testimonials=[
            {"quote":"Très simple à déployer, ROI clair.","name":"Client A","role":"Dir. Opérations"},
            {"quote":"Un support vraiment réactif.","name":"Client B","role":"CEO"},
        ],
        faq=[
            {"q":"Proposez-vous un essai ?","a":"Oui, 14 jours sans carte bancaire."},
            {"q":"Où sont hébergées les données ?","a":"En UE, conformément au RGPD."},
            {"q":"Comment se passe l’onboarding ?","a":"Guidé, avec bonnes pratiques sectorielles."},
            {"q":"Puis-je résilier facilement ?","a":"Oui, à tout moment depuis l’espace client."},
            {"q":"Avez-vous des intégrations ?","a":"Oui, les principales APIs/middleware du marché."},
        ],
    )

def _prompt_landing_copy(context: dict) -> str:
    # contexte → prompt JSON-only
    return (
        "Réponds EXCLUSIVEMENT par un JSON brut avec EXACTEMENT la clé 'copy'. "
        "AUCUN autre texte. PAS de ```.\n\n"
        "Ton rôle: rédiger le contenu d'une landing (FR) à PARTIR DU CONTEXTE, sans modifier le style HTML.\n"
        "Exigences:\n"
        "- 3 fonctionnalités clés MAX (cartes), chacune: title, desc courte (bénéfice), bullets (2–4), et un KPI plausible (ex: ~12% ou ~8h/mois).\n"
        "- 3 raisons 'Pourquoi nous' MAX (cartes), adaptées au projet/secteur; 1 phrase CLAIRE par élément.\n"
        "- Montants en euros; ton professionnel; FR sans jargon inutile; RGPD/UE si pertinent.\n"
        "- Ne mets PAS de markdown.\n\n"
        "{\n"
        '  "copy": {\n'
        '    "hero_title": "...",\n'
        '    "hero_subtitle": "...",\n'
        '    "hero_bullets": ["...","...","..."],\n'
        '    "segments_badges": ["...","..."],\n'
        '    "features": [\n'
        '      {"title":"...","desc":"...","bullets":["...","..."],"kpi":"~...% / ...h gagnées"},\n'
        '      {"title":"...","desc":"...","bullets":["...","..."],"kpi":"~...% / ...h gagnées"},\n'
        '      {"title":"...","desc":"...","bullets":["...","..."],"kpi":"~...% / ...h gagnées"}\n'
        '    ],\n'
        '    "differentiators": ["...","...","..."],\n'
        '    "pricing": {\n'
        '       "starter": {"name":"Starter","price_per_month_eur":123,"bullets":["..."],"cta":"..."},\n'
        '       "pro": {"name":"Pro","price_per_month_eur":199,"bullets":["..."],"cta":"..."},\n'
        '       "enterprise": {"name":"Entreprise","price_per_month_eur":null,"bullets":["..."],"cta":"..."}\n'
        "    },\n"
        '    "trust_points": ["...","..."],\n'
        '    "testimonials": [{"quote":"...","name":"...","role":"..."}],\n'
        '    "faq": [{"q":"...","a":"..."}]\n'
        "  }\n"
        "}\n\n"
        f"[CONTEXTE]\n{json.dumps(context, ensure_ascii=False)}"
    )

def _brand_theme(brand: Optional[dict]) -> dict:
    # Clés possibles: primary_color, accent_color, bg_color
    primary = (brand or {}).get("primary_color") or (brand or {}).get("primary") or "#8b93ff"
    accent  = (brand or {}).get("accent_color")  or (brand or {}).get("accent")  or "#14b8a6"
    bg      = (brand or {}).get("bg_color")      or "#0f172a"
    return {
        "primary": primary,
        "accent":  accent,
        "bg":      bg,
        "text":    "#e5e7eb",
        "panel":   "#111827",
        "border":  "#1f2937",
        "muted":   "#9ca3af",
    }

def _sector_presets_for_feature_details(sector: str) -> dict:
    s = (sector or "").lower()
    if any(k in s for k in ["saas","logiciel","b2b","crm","erp","plateforme","app"]):
        return {
            "bullets": [
                "Connexion en < 30 min (SSO / OAuth)",
                "Intégrations natives (Zapier, Slack, Google Sheets)",
                "Exports CSV & API REST",
                "Alertes et automatisations"
            ],
            "kpi": "~20–40% de temps gagné / équipe"
        }
    if any(k in s for k in ["ecom","e-commerce","ecommerce","boutique","retail","dnvb"]):
        return {
            "bullets": [
                "Catalogues & variantes illimités",
                "Suivi panier & reprise d’abandon",
                "Coupons & campagnes ciblées",
                "Rapports ventes / marge / cohortes"
            ],
            "kpi": "~5–12% d’augmentation du taux de conversion"
        }
    # services / générique
    return {
        "bullets": [
            "Planification & suivi d’exécution",
            "Templates & checklist qualité",
            "Tableaux de bord temps & coûts",
            "Exports PDF/CSV, partage client"
        ],
        "kpi": "~15–30% de productivité en plus"
    }

def _enrich_features(copy: dict, idea_snapshot: dict, sector: str) -> list[dict]:
    """Retourne EXACTEMENT 3 cartes: title, desc, bullets (2–4), kpi."""
    base = copy.get("features") or []
    presets = _sector_presets_for_feature_details(sector)

    # Titres de secours si rien n’est fourni
    fallback_titles = (
        idea_snapshot.get("products_services")
        or idea_snapshot.get("differentiation_points")
        or [f"Résout : {p}" for p in (idea_snapshot.get("pain_points") or [])]
        or ["Fonction clé 1", "Fonction clé 2", "Fonction clé 3"]
    )

    # Normalise
    norm = []
    for f in base:
        if not isinstance(f, dict): continue
        title   = (f.get("title") or "").strip() or (fallback_titles[0] if fallback_titles else "Fonction")
        desc    = (f.get("desc") or "Bénéfice clair et résultat attendu.").strip()
        bullets = [b for b in (f.get("bullets") or presets["bullets"][:3]) if b][:4]
        if len(bullets) < 2:
            bullets += presets["bullets"][: (2 - len(bullets))]
        kpi     = (f.get("kpi") or presets["kpi"]).strip()
        norm.append({"title": title, "desc": desc, "bullets": bullets, "kpi": kpi})

    # Complète si < 3
    i = 0
    while len(norm) < 3 and i < len(fallback_titles):
        t = fallback_titles[i]
        norm.append({
            "title": str(t),
            "desc": "Impact direct et mesurable pour votre cas d’usage.",
            "bullets": presets["bullets"][:3],
            "kpi": presets["kpi"]
        })
        i += 1
    while len(norm) < 3:
        norm.append({
            "title": f"Fonction clé {len(norm)+1}",
            "desc": "Gain de temps et fiabilité au quotidien.",
            "bullets": presets["bullets"][:3],
            "kpi": presets["kpi"]
        })

    return norm[:3]

def _top3_differentiators(copy: dict, idea_snapshot: dict, sector: str, project_id: Optional[int]) -> list[str]:
    diffs = [d for d in (copy.get("differentiators") or []) if isinstance(d, str) and d.strip()]
    if not diffs:
        diffs = [d for d in (idea_snapshot.get("differentiation_points") or []) if d]
    if not diffs:
        s = (sector or "").lower()
        if any(k in s for k in ["saas","logiciel","b2b"]):
            diffs = [
                "Mise en place rapide — Onboarding guidé & intégrations natives",
                "RGPD & hébergement UE — DPA, chiffrement, bonnes pratiques",
                "Support réactif — Réponse 24–48h, spécialistes du secteur",
            ]
        elif any(k in s for k in ["ecom","e-commerce","boutique"]):
            diffs = [
                "Pensé pour le e-commerce — Outils conversion & retargeting",
                "Intégrations logistiques — Suivi, retours, rapports marge",
                "ROI mesurable — Tableaux de bord ventes & cohortes",
            ]
        else:
            diffs = [
                "Simple à déployer — Accompagnement pas-à-pas",
                "Sécurisé & conforme — Hébergement UE",
                "Humain & proche — Support qui comprend votre métier",
            ]

    # Fige à 3 (sélection stable par projet)
    if len(diffs) > 3:
        seed = int(hashlib.md5(f"diffs:{project_id}".encode("utf-8")).hexdigest()[:8], 16)
        rnd = random.Random(seed)
        rnd.shuffle(diffs)
    return diffs[:3]

async def _generate_landing_copy(
    profil: "ProfilRequest",
    idea_snapshot: Optional[dict],
    brand: Optional[dict],
) -> LandingCopy:
    # Récup des éléments projet
    p = _profil_dump(profil)
    sector = p.get("secteur") or "—"
    idea = (idea_snapshot or {}).get("idee") or ""
    persona = (idea_snapshot or {}).get("persona") or p.get("persona") or ""
    products = (idea_snapshot or {}).get("products_services") or []
    diffs = (idea_snapshot or {}).get("differentiation_points") or []
    segments = (idea_snapshot or {}).get("segments") or []
    locations = (idea_snapshot or {}).get("locations") or []
    base_price = (idea_snapshot or {}).get("base_price_eur") \
        or (p.get("assumptions") or {}).get("price") \
        or (getattr(profil, "price", None))

    brand_name = (brand or {}).get("brand_name") or (idea_snapshot or {}).get("nom") or "Votre Marque"
    slogan     = (brand or {}).get("slogan")     or (idea_snapshot or {}).get("slogan") or "Votre slogan ici"

    context = {
        "sector": sector,
        "brand_name": brand_name,
        "slogan": slogan,
        "idea": idea,
        "persona": persona,
        "pain_points": (idea_snapshot or {}).get("pain_points") or [],
        "products_services": products,
        "segments": segments,
        "locations": locations,
        "differentiation_points": diffs,
        "base_price_eur": base_price,
        "market": (idea_snapshot or {}).get("market") or "",
    }
    prompt = _prompt_landing_copy(context)

    project_id = (idea_snapshot or {}).get("project_id")
    bp = None
    try:
        if project_id:
            d = _latest_deliverable(int(project_id), "model")
            if d and d.json_content:
                j = dict(d.json_content or {})
                bp = j.get("business_plan") or j  # selon comment tu as stocké le livrable
    except Exception:
        bp = None

    try:
        resp = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role":"user","content":prompt}],
            temperature=0.5,
            max_tokens=1200,
        )
        data = _safe_json_loads(resp.choices[0].message.content)
        copy = data.get("copy", {}) or {}
        copy["features"] = _enrich_features(copy, idea_snapshot, sector)
        # 3 “Pourquoi nous” adaptés
        copy["differentiators"] = _top3_differentiators(copy, idea_snapshot or {}, sector, int(project_id or 0))
        # Tarification “smart” à partir du BP (calibration), sinon fallback base
        smart_pricing = _compute_pricing_from_bp(
            bp=bp,
            sector=sector,
            base_price=base_price,
            objective=p.get("objectif"),
            project_id=int(project_id or 0),
        )
        copy["pricing"] = _merge_pricing(copy.get("pricing"), smart_pricing)

        # (facultatif) renforcer quelques champs si vides
        if not copy.get("hero_bullets"):
            copy["hero_bullets"] = [
                "ROI mesurable sous 30 jours",
                "Onboarding guidé et support réactif",
                "Conforme RGPD, hébergement UE",
            ]
        if not copy.get("differentiators"):
            copy["differentiators"] = [
                "Simplicité d’usage",
                "Rapport qualité/prix aligné marché",
                "Intégrations natives au secteur",
            ]

        return LandingCopy(**copy)

    except Exception:
        # Fallback sûr si le JSON est invalide
        return _fallback_copy(
            brand_name=brand_name, slogan=slogan, persona=persona, idea=idea,
            base_price=base_price, products=products, diffs=diffs, segments=segments
        )

def _esc(x: Any) -> str:
    try:
        import html
        return html.escape(str(x if x is not None else ""))
    except Exception:
        return str(x)

def _render_landing_html(
    copy: LandingCopy,
    brand_name: str, slogan: str, sector: str,
    project_id: int,
    logo_data_uri: Optional[str] = None,
    theme: Optional[dict] = None,
) -> str:
    t = theme or {
        "primary":"#8b93ff","accent":"#14b8a6","bg":"#0f172a",
        "text":"#e5e7eb","panel":"#111827","border":"#1f2937","muted":"#9ca3af"
    }

    hero_svg = """<svg viewBox="0 0 600 360" width="100%" height="100%" preserveAspectRatio="xMidYMid slice" role="img" aria-label="Product">
      <defs><linearGradient id="g" x1="0" x2="1" y1="0" y2="1">
        <stop offset="0%" stop-color="{}"/><stop offset="100%" stop-color="{}"/>
      </linearGradient></defs>
      <rect x="0" y="0" width="600" height="360" fill="#0b1220"/>
      <rect x="24" y="24" width="552" height="312" rx="14" fill="url(#g)" opacity="0.18"/>
      <g opacity="0.9">
        <rect x="60" y="72" width="480" height="40" rx="8" fill="#111827" stroke="#1f2937"/>
        <rect x="60" y="126" width="360" height="24" rx="6" fill="#0b1220" />
        <rect x="60" y="160" width="420" height="24" rx="6" fill="#0b1220" />
        <rect x="60" y="194" width="300" height="24" rx="6" fill="#0b1220" />
        <rect x="60" y="238" width="160" height="44" rx="10" fill="#111827" stroke="#1f2937"/>
      </g>
    </svg>""".format(_esc(t["primary"]), _esc(t["accent"]))

    def bullets(items: list[str]) -> str:
        items = [i for i in (items or []) if i]
        return "<ul class='list'>" + "".join(f"<li>{_esc(i)}</li>" for i in items) + "</ul>" if items else ""

    def features_grid(features: list[dict]) -> str:
        items = (features or [])[:3]
        cells = []
        for f in items:
            title  = _esc(f.get("title",""))
            desc   = _esc(f.get("desc",""))
            bts    = [b for b in (f.get("bullets") or []) if b][:4]
            kpi    = _esc(f.get("kpi",""))
            li     = "".join(f"<li>{_esc(b)}</li>" for b in bts)
            cells.append(
                "<div class='panel'>"
                f"<div class='card-title'>{title}</div>"
                f"<div class='muted'>{desc}</div>"
                f"<ul class='list'>{li}</ul>"
                + (f"<div class='kpi'>{kpi}</div>" if kpi else "")
                + "</div>"
            )
        return "<div class='grid grid-3'>" + "".join(cells) + "</div>"

    def why_us_cards(diffs: list[str]) -> str:
        items = (diffs or [])[:3]
        cells = []
        for s in items:
            raw = s or ""
            if "—" in raw:
                ttitle, tdesc = raw.split("—", 1)
            elif ":" in raw:
                ttitle, tdesc = raw.split(":", 1)
            else:
                ttitle, tdesc = raw, ""
            cells.append(
                "<div class='panel'>"
                f"<div class='card-title'>{_esc(ttitle.strip())}</div>"
                f"<div class='muted'>{_esc(tdesc.strip())}</div>"
                "</div>"
            )
        return "<div class='grid grid-3'>" + "".join(cells) + "</div>"

    badges = "".join(f"<span class='badge'>{_esc(b)}</span> " for b in (copy.segments_badges or [])[:4])

    styles = f"""
    <style>
      :root {{
        --primary:{_esc(t["primary"])};
        --accent:{_esc(t["accent"])};
        --bg:{_esc(t["bg"])};
        --text:{_esc(t["text"])};
        --panel:{_esc(t["panel"])};
        --border:{_esc(t["border"])};
        --muted:{_esc(t["muted"])};
        color-scheme: dark;
      }}
      body {{ margin:0; background:var(--bg); color:var(--text); font-family: Inter, system-ui, -apple-system, Segoe UI, Roboto, Arial; }}
      .wrap {{ max-width:1100px; margin:0 auto; padding:24px; }}
      header {{ display:flex; align-items:center; justify-content:space-between; gap:16px; padding:14px 0; }}
      .brand {{ display:flex; align-items:center; gap:12px; }}
      .brand img {{ height:42px; width:auto; border-radius:8px; background:#0b1220; border:1px solid var(--border); }}
      .brand .t {{ display:flex; flex-direction:column; line-height:1.1 }}
      .brand .n {{ font-weight:800; font-size:20px }}
      .brand .s {{ color:var(--muted); font-size:12px }}
      .cta {{ display:flex; gap:10px }}
      .cta a, .cta button, .cta-btn {{ background:var(--primary); color:white; border:none; padding:10px 14px; border-radius:10px; font-weight:600; cursor:pointer; text-decoration:none }}
      .cta a:hover, .cta button:hover, .cta-btn:hover {{ filter:brightness(1.05) }}
      .hero {{ display:grid; grid-template-columns:1.1fr .9fr; gap:18px; align-items:center; padding:16px 0 26px; }}
      .hero h1 {{ font-size:36px; margin:6px 0 10px; }}
      .hero p {{ color:var(--muted) }}
      .panel {{ background:var(--panel); border:1px solid var(--border); border-radius:16px; padding:18px; }}
      .grid {{ display:grid; gap:14px }}
      .grid-2 {{ grid-template-columns:repeat(2,minmax(0,1fr)) }}
      .grid-3 {{ grid-template-columns:repeat(3,minmax(0,1fr)) }}
      .list li {{ margin:6px 0 }}
      section h2 {{ font-size:22px; margin:18px 0 10px; color:var(--primary) }}
      .badge {{ display:inline-block; background:#0b1220; border:1px solid var(--border); padding:6px 10px; border-radius:999px; font-size:12px; color:var(--muted); margin-right:6px }}
      .price {{ font-size:28px; font-weight:800 }}
      .card-title {{ font-weight:700; font-size:16px; margin-bottom:6px }}
      .kpi {{ margin-top:8px; font-weight:800; color:var(--accent) }}
      .muted {{ color:var(--muted) }}
      form input, form textarea {{ width:100%; background:#0b1220; color:var(--text); border:1px solid var(--border); border-radius:10px; padding:10px 12px; }}
      form button {{ background:var(--accent); color:#052e2b; border:none; padding:10px 14px; border-radius:10px; font-weight:700; cursor:pointer }}
      footer {{ margin:24px 0 10px; color:var(--muted); font-size:12px; text-align:center }}
      @media (max-width: 900px) {{ .hero {{ grid-template-columns:1fr; }} .grid-3 {{ grid-template-columns:1fr; }} }}
    </style>
    """

    def pricing_block(pr: dict) -> str:
        def tier_html(t: dict) -> str:
            name = _esc(t.get("name",""))
            price = t.get("price_per_month_eur")
            price_html = f"<div class='price'>{int(price)} € / mois</div>" if price is not None else "<div class='price'>Sur devis</div>"
            bl = bullets(t.get("bullets") or [])
            cta = _esc(t.get("cta") or "Choisir")
            return f"<div class='panel'><div><strong>{name}</strong></div>{price_html}{bl}<div style='margin-top:8px'><a class='cta-btn' href='#contact'>{cta}</a></div></div>"
        return "<div class='grid grid-3'>" + tier_html(pr.get("starter", {})) + tier_html(pr.get("pro", {})) + tier_html(pr.get("enterprise", {})) + "</div>"

    html = f"""<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>{_esc(brand_name)} — Landing</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;800&display=swap" rel="stylesheet">
{styles}
</head>
<body>
<div class="wrap">
  <header>
    <div class="brand">
      {("<img alt='logo' src='" + _esc(logo_data_uri) + "'/>") if logo_data_uri else ""}
      <div class="t">
        <div class="n">{_esc(brand_name)}</div>
        <div class="s">{_esc(slogan)}</div>
      </div>
    </div>
    <div class="cta">
      <a href="#contact">Commencer</a>
      <a href="#pricing" style="background:#0b1220;border:1px solid var(--border);color:var(--text)">Tarifs</a>
    </div>
  </header>

  <div class="hero">
    <div class="panel">
      <span class="badge">Secteur : {_esc(sector)}</span> {badges}
      <h1>{_esc(copy.hero_title or (brand_name + " — " + slogan))}</h1>
      <p>{_esc(copy.hero_subtitle)}</p>
      {bullets(copy.hero_bullets)}
      <div class="cta" style="margin-top:10px">
        <a href="#contact">Demander une démo</a>
        <a href="#pricing" style="background:#0b1220; border:1px solid var(--border); color:var(--text)">Voir les tarifs</a>
      </div>
    </div>
    <div class="panel">{hero_svg}</div>
  </div>

  <section id="features" class="panel">
    <h2>Fonctionnalités clés</h2>
    {features_grid(copy.features)}
  </section>

  <section class="panel">
    <h2>Pourquoi nous</h2>
    {why_us_cards(copy.differentiators)}
  </section>

  <section id="pricing" class="panel">
    <h2>Tarification</h2>
    {pricing_block(copy.pricing)}
  </section>

  <section class="panel">
    <h2>Confiance & conformité</h2>
    {bullets(copy.trust_points)}
  </section>

  <section class="panel">
    <h2>Témoignages</h2>
    <div class="grid grid-2">
      {''.join(f"<div class='panel'>“{_esc(t.get('quote',''))}” — {_esc(t.get('name',''))}, {_esc(t.get('role',''))}</div>" for t in (copy.testimonials or [])[:2])}
    </div>
  </section>

  <section id="faq" class="panel">
    <h2>FAQ</h2>
    <div class="grid grid-2">
      {''.join(f"<div class='panel'><strong>{_esc(qa.get('q',''))}</strong><br/>{_esc(qa.get('a',''))}</div>" for qa in (copy.faq or [])[:6])}
    </div>
  </section>

  <section id="contact" class="panel">
    <h2>Contact</h2>
    <form action="/api/landing/lead" method="POST">
      <input type="hidden" name="project_id" value="{project_id}" />
      <div class="grid grid-2">
        <div><label>Nom</label><br/><input name="name" required placeholder="Votre nom"/></div>
        <div><label>Email</label><br/><input name="email" type="email" required placeholder="vous@exemple.com"/></div>
      </div>
      <div style="margin-top:8px">
        <label>Message</label><br/>
        <textarea name="message" rows="4" placeholder="Parlez-nous de votre besoin (optionnel)"></textarea>
      </div>
      <div style="margin-top:10px"><button type="submit">Envoyer</button></div>
      <small class="muted">Nous répondons sous 24–48h.</small>
    </form>
  </section>

  <footer>© {_esc(brand_name)} — Tous droits réservés</footer>
</div>
</body>
</html>"""
    return html

# --- REMPLACE ta generate_landing par celle-ci -------------------------------

async def generate_landing(
    profil: "ProfilRequest",
    idea_snapshot: Optional[dict] = None,
    brand: Optional[dict] = None,
    logo_data_uri: Optional[str] = None,
) -> LandingResponse:
    """
    On garde le STYLE/MARKUP de ta landing. GPT ne génère QUE les textes (copy).
    """
    # 1) Prépa contextes
    p = _profil_dump(profil)
    sector = p.get("secteur") or "—"
    brand_name = (brand or {}).get("brand_name") or (idea_snapshot or {}).get("nom") or "Votre Marque"
    slogan     = (brand or {}).get("slogan")     or (idea_snapshot or {}).get("slogan") or "Votre slogan ici"
    project_id = (idea_snapshot or {}).get("project_id") or 0

    # 2) Sécuriser logo (si chemin) → data URI
    if logo_data_uri and logo_data_uri.startswith("/"):
        logo_data_uri = _as_data_uri_from_path(logo_data_uri)

    # 3) Générer la COPY (JSON) via GPT (ou fallback)
    copy = await _generate_landing_copy(profil, idea_snapshot, brand)

    theme = _brand_theme(brand)

    # 4) Rendre le HTML final en réinjectant la copy dans TON template
    html = _render_landing_html(copy, brand_name, slogan, sector, int(project_id or 0), logo_data_uri, theme)

    return LandingResponse(html=html)
# MARKETING
# ─────────────────────────────────────────────────────────────────────────────

async def generate_marketing(profil: ProfilRequest, idea_snapshot: Optional[Dict[str, Any]] = None) -> MarketingResponse:
    """
    Retour JSON STRICT avec exactement:
      - ads_strategy (string)
      - seo_plan (string)
      - social_plan (string)
    Contraintes: persona VERBATIM = audience cible, noms/verbatims inchangés.
    """
    p = _profil_dump(profil)
    prompt = (
        "Réponds EXCLUSIVEMENT par un JSON brut avec EXACTEMENT les clés 'ads_strategy', 'seo_plan', 'social_plan'.\n"
        "CONTRAINTES:\n"
        "- Utiliser la 'persona' du VERBATIM comme audience cible, sans reformulation du libellé.\n"
        "- Garder noms/slogans du VERBATIM inchangés quand ils apparaissent.\n"
        "- Aucune autre clé.\n"
        + _verbatim_block(idea_snapshot) +
        f"\n[PROFIL] secteur={p.get('secteur')} • objectif={p.get('objectif')}"
    )
    resp = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.5,
        max_tokens=700,
    )
    data = _parse_json_strict(resp.choices[0].message.content)
    for key in ("ads_strategy", "seo_plan", "social_plan"):
        val = data.get(key)
        if not isinstance(val, str):
            data[key] = json.dumps(val, ensure_ascii=False)
    missing = [k for k in ("ads_strategy", "seo_plan", "social_plan") if k not in data]
    if missing:
        raise HTTPException(status_code=500, detail=f"Clés manquantes: {missing}")
    return MarketingResponse(**data)

# ─────────────────────────────────────────────────────────────────────────────

# ─────────────────────────────────────────────────────────────────────────────
# ACQUISITION STRUCTURÉE (pour le livret Marketing)
# ─────────────────────────────────────────────────────────────────────────────

def _default_assumptions() -> Dict[str, float]:
    return {
        "cpc": 1.2,        # € par clic (paid)
        "ctr": 0.02,       # 2%
        "lp_cvr": 0.06,    # 6% landing -> lead
        "sales_cvr": 0.18, # 18% lead -> vente
        "aov": 120.0,      # panier moyen €
        "retention": 0.0
    }

def _build_forecast(monthly_budget: float, assumptions: Dict[str, float], months: int = 3) -> List[Dict[str, float]]:
    a = {**_default_assumptions(), **(assumptions or {})}
    out: List[Dict[str, float]] = []
    for i in range(1, months + 1):
        budget = float(monthly_budget or 0)
        clicks = budget / max(a["cpc"], 0.01)
        imps   = clicks / max(a["ctr"], 0.0001)
        leads  = clicks * a["lp_cvr"]
        sales  = leads  * a["sales_cvr"]
        revenue = sales * a["aov"]
        cac = (budget / sales) if sales > 0 else None
        roas = (revenue / budget) if budget > 0 else None
        out.append({
            "month": f"M{i}",
            "impressions": round(imps),
            "clicks": round(clicks),
            "leads": round(leads),
            "sales": round(sales),
            "revenue": round(revenue, 2),
            "cac": round(cac, 2) if cac else None,
            "roas": round(roas, 2) if roas else None,
            "spend": round(budget, 2),
        })
    return out

# ─────────────────────────────────────────────────────────────────────────────
# Benchmarks secteur + forecast
# ─────────────────────────────────────────────────────────────────────────────

def _map_industry(secteur: str | None) -> str:
    s = (secteur or "").lower()
    if any(k in s for k in ["e-com", "boutique", "retail", "shop"]):
        return "ecommerce_b2c"
    if any(k in s for k in ["saas", "logiciel", "b2b", "crm", "erp", "data"]):
        return "saas_b2b"
    if any(k in s for k in ["industrie", "robot", "iot", "manufact", "usine"]):
        return "industry_b2b"
    if any(k in s for k in ["mobile", "app", "application"]):
        return "mobile_app"
    if any(k in s for k in ["formation", "coaching", "infoproduit"]):
        return "info_b2c"
    if any(k in s for k in ["service", "artisan", "local"]):
        return "services_locaux"
    return "generic_b2b"

def _industry_benchmarks() -> Dict[str, Dict[str, Any]]:
    # Médianes réalistes à ajuster avec tes données terrain (proportions en décimal).
    return {
        "saas_b2b": {
            "assumptions": {"cpc": 3.2, "ctr": 0.02, "lp_cvr": 0.045, "mql_rate": 0.55, "sql_rate": 0.45, "close_rate": 0.22, "aov": 0.0},
            "monthly_budget": 4000,
            "mix": [("LinkedIn Ads", 0.30), ("Google Search", 0.30), ("SEO/Contenu", 0.20), ("Emailing", 0.10), ("Retargeting", 0.10)],
        },
        "ecommerce_b2c": {
            "assumptions": {"cpc": 0.9, "ctr": 0.018, "lp_cvr": 0.025, "mql_rate": 1.0, "sql_rate": 1.0, "close_rate": 0.035, "aov": 65},
            "monthly_budget": 3000,
            "mix": [("Meta Ads", 0.40), ("Google Shopping", 0.30), ("SEO/Contenu", 0.15), ("Influence/UGC", 0.10), ("Emailing", 0.05)],
        },
        "industry_b2b": {
            "assumptions": {"cpc": 2.4, "ctr": 0.016, "lp_cvr": 0.06, "mql_rate": 0.6, "sql_rate": 0.5, "close_rate": 0.25, "aov": 0.0},
            "monthly_budget": 3500,
            "mix": [("Google Search", 0.35), ("LinkedIn Ads", 0.25), ("SEO/Contenu", 0.20), ("Salons/Partenariats", 0.10), ("Emailing", 0.10)],
        },
        "mobile_app": {
            "assumptions": {"cpc": 0.7, "ctr": 0.03, "lp_cvr": 0.07, "mql_rate": 1.0, "sql_rate": 1.0, "close_rate": 0.04, "aov": 12},
            "monthly_budget": 2500,
            "mix": [("ASA/UAC", 0.45), ("Meta/TikTok", 0.35), ("SEO/ASO", 0.10), ("Emailing/CRM", 0.10)],
        },
        "services_locaux": {
            "assumptions": {"cpc": 1.6, "ctr": 0.025, "lp_cvr": 0.09, "mql_rate": 0.7, "sql_rate": 0.6, "close_rate": 0.35, "aov": 180},
            "monthly_budget": 1500,
            "mix": [("Google Search", 0.50), ("SEO Local", 0.25), ("Avis clients", 0.15), ("Emailing", 0.10)],
        },
        "info_b2c": {
            "assumptions": {"cpc": 0.8, "ctr": 0.02, "lp_cvr": 0.18, "mql_rate": 0.6, "sql_rate": 0.35, "close_rate": 0.12, "aov": 79},
            "monthly_budget": 2000,
            "mix": [("Meta Ads", 0.45), ("Webinars/Lead magnet", 0.25), ("SEO/Contenu", 0.20), ("Emailing", 0.10)],
        },
        "generic_b2b": {
            "assumptions": {"cpc": 2.2, "ctr": 0.02, "lp_cvr": 0.05, "mql_rate": 0.55, "sql_rate": 0.45, "close_rate": 0.20, "aov": 0.0},
            "monthly_budget": 3000,
            "mix": [("Google Search", 0.35), ("LinkedIn Ads", 0.25), ("SEO/Contenu", 0.20), ("Emailing", 0.10), ("Retargeting", 0.10)],
        },
    }

def _choose_bench(secteur: str | None, objectif: str | None) -> Tuple[Dict[str, float], float, list[tuple[str, float]]]:
    cat = _map_industry(secteur)
    cfg = _industry_benchmarks()[cat]
    assumptions = cfg["assumptions"]
    budget = cfg["monthly_budget"]
    mix = cfg["mix"]
    if objectif and any(k in (objectif or "").lower() for k in ["agress", "x2", "scale", "hyper"]):
        budget *= 1.4  # boost budget si objectif agressif
    return assumptions, budget, mix

def _build_forecast_6m(ass: Dict[str, float], monthly_budget: float) -> Dict[str, list[Dict[str, float]]]:
    """
    3 trajectoires lisibles pour 6 mois :
      - 'Départ prudent'     : budget 0.8x, conversions 0.85x, CPC 1.1x
      - 'Vitesse de croisière': budget 1.0x, conversions 1.0x, CPC 1.0x
      - 'Accélération'       : budget 1.2x, conversions 1.15x, CPC 0.95x
    + apprentissage : on démarre à 70% du budget et on monte progressivement à 100% M6.
    """
    traj = {
        "Départ prudent":     {"budget": 0.8, "conv": 0.85, "cpc": 1.10},
        "Vitesse de croisière": {"budget": 1.0, "conv": 1.00, "cpc": 1.00},
        "Accélération":       {"budget": 1.2, "conv": 1.15, "cpc": 0.95},
    }
    out: Dict[str, list[Dict[str, float]]] = {}
    for name, m in traj.items():
        rows: List[Dict[str, float]] = []
        cum_leads = 0.0
        cum_sales = 0.0
        for i in range(1, 7):
            ramp = 0.70 + (0.06 * (i - 1))  # 70% -> 100% sur 6 mois
            spend = monthly_budget * m["budget"] * ramp

            cpc = max(ass.get("cpc", 1.0) * m["cpc"] * (1 - 0.05 * (i - 1)), 0.05)
            ctr = ass.get("ctr", 0.015) * m["conv"] * (1 + 0.06 * (i - 1))
            lp  = ass.get("lp_cvr", 0.05) * m["conv"] * (1 + 0.05 * max(0, i - 2))
            mql = ass.get("mql_rate", 0.6) * m["conv"]
            sql = ass.get("sql_rate", 0.45) * m["conv"]
            close = ass.get("close_rate", 0.2) * m["conv"]
            aov = ass.get("aov", 0.0)

            clicks = spend / cpc
            imps = clicks / max(ctr, 0.0001)
            leads = clicks * lp
            mqls  = leads * mql
            sqls  = mqls * sql
            sales = sqls * close
            revenue = sales * aov if aov > 0 else 0.0

            cum_leads += leads
            cum_sales += sales

            rows.append({
                "month": f"M{i}",
                "impressions": round(imps),
                "clicks": round(clicks),
                "leads": round(leads),
                "mqls": round(mqls),
                "sqls": round(sqls),
                "sales": round(sales),
                "revenue": round(revenue, 2),
                "cumulative_leads": round(cum_leads),
                "cumulative_sales": round(cum_sales),
                "spend": round(spend, 2),
            })
        out[name] = rows
    return out

async def generate_acquisition_structured_for_marketing(
    profil: ProfilRequest, idea_snapshot: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    p = _profil_dump(profil)
    secteur = p.get("secteur")
    objectif = p.get("objectif")
    assumptions, monthly_budget, default_mix = _choose_bench(secteur, objectif)

    # Mix canaux — explications simples + étapes concrètes
    channel_mix: List[Dict[str, Any]] = []
    for name, share in default_mix:
        steps: List[str] = []
        goal = "Acquisition"

        if name in ("Google Search", "Google Shopping"):
            goal = "Être trouvé quand on te cherche"
            steps = [
                "Crée ton compte Google Ads (si inexistant) et relie-le à GA4.",
                "Liste 10 à 20 expressions que tes clients tapent (ex: 'logiciel devis bâtiment').",
                "Crée 2 annonces par groupe de mots-clés, avec un titre clair et un appel à l’action simple.",
                "Ajoute une page de destination courte : titre clair, bénéfice, preuve sociale, formulaire simple.",
                "Installe le suivi des conversions (clic sur bouton, envoi de formulaire).",
            ]
        elif name in ("LinkedIn Ads",):
            goal = "Aller vers les décideurs B2B"
            steps = [
                "Décris ton client idéal (fonction, taille d’entreprise, secteur).",
                "Prépare un document utile (guide PDF, étude de cas) à télécharger.",
                "Crée une campagne 'Génération de leads' avec formulaire court (nom, email pro).",
                "Rédige 2 à 3 messages simples expliquant l’intérêt du document.",
                "Connecte le formulaire à ton CRM (ou exporte les leads chaque semaine).",
            ]
        elif name in ("Meta Ads", "TikTok", "Influence/UGC"):
            goal = "Se faire découvrir"
            steps = [
                "Crée 3 vidéos courtes (20–30 s) montrant le produit/problème/solution.",
                "Commence avec une audience large + centres d’intérêt pertinents.",
                "Page d’atterrissage simple : une promesse, une image, un bouton.",
                "Lance un petit budget pour tester quelles vidéos fonctionnent le mieux.",
                "Relance (retargeting) les visiteurs qui n’ont pas encore acheté/contacté.",
            ]
        elif name.startswith("SEO"):
            goal = "Apparaître gratuitement dans Google"
            steps = [
                "Liste 10 questions fréquentes posées par tes clients.",
                "Écris 1 article par semaine qui répond clairement à une question.",
                "Améliore la vitesse de ton site et les titres de pages (clairs, mots-clés simples).",
                "Ajoute des liens entre tes pages (ex: article → page produit).",
                "Cherche 2 sites/mois pour obtenir un lien vers ton site (partenaires, blogs).",
            ]
        elif name in ("Emailing", "Emailing/CRM"):
            goal = "Transformer les visiteurs en clients"
            steps = [
                "Installe un formulaire d’inscription discret sur le site (newsletter ou guide).",
                "Rédige 3 emails d’accueil : présentation, aide utile, offre d’essai/démo.",
                "Envoie 1 email par semaine avec un conseil pratique lié à ton produit.",
                "Nettoie la liste chaque mois (bounces, inactifs).",
                "Ajoute un bouton ou un lien vers la prise de contact/achat dans chaque email.",
            ]
        elif name in ("Retargeting",):
            goal = "Rattraper les indécis"
            steps = [
                "Crée une audience des visiteurs des 30 derniers jours.",
                "Prépare 2 visuels rappelant le bénéfice principal + une offre d’essai/démo.",
                "Limite la répétition (fréquence) pour éviter la lassitude.",
                "Exclus les clients déjà convertis.",
            ]
        elif name in ("Salons/Partenariats",):
            goal = "Créer des opportunités en direct"
            steps = [
                "Choisis 1 à 2 événements pertinents ce trimestre.",
                "Prépare un support simple (affiche, flyer) et une démo courte.",
                "Collecte les coordonnées des personnes intéressées (fiche ou QR code).",
                "Recontacte sous 48 h avec un email personnalisé + proposition de RDV.",
            ]
        else:
            steps = ["Plan d’actions dédié selon ton contexte."]

        channel_mix.append({
            "name": name,
            "budget_share": round(share, 2),
            "goal": goal,
            "beginner_steps": steps,
            "kpis": ["Coût par contact", "Nombre de contacts", "Conversions"],
        })

    # Funnel pédagogique
    funnel = {
        "awareness": ["On te découvre (réseaux, Google, bouche-à-oreille)"],
        "consideration": ["On s’intéresse (pages comparatives, cas clients, webinar)"],
        "conversion": ["On te contacte / On achète (formulaire simple, essai, offre claire)"],
        "retention": ["On revient / On recommande (emails, support, parrainage, avis)"],
    }

    # Projection 6 mois
    forecast = _build_forecast_6m(assumptions, monthly_budget)

    # Agenda débutant (avec temps estimé & “qui”)
    agenda = [
        {"week": 1, "theme": "Mise en place", "time": "6–8 h", "owner": "Fondateur/CM",
         "tasks": ["Créer comptes (GA4, Ads, Meta/TikTok, email)", "Installer balises (Pixel/Tag Manager)", "Lister 10 mots-clés et 10 questions clients"]},
        {"week": 2, "theme": "Pages & messages", "time": "6–8 h", "owner": "Fondateur/CM",
         "tasks": ["Écrire 1 page d’atterrissage claire", "Rédiger 2 annonces Search", "Préparer 2 visuels/vidéos simples"]},
        {"week": 3, "theme": "Lancement tests", "time": "5–7 h", "owner": "Fondateur/CM",
         "tasks": ["Lancer petites campagnes (Search + Social)", "Activer suivi des conversions", "Créer formulaire capture email"]},
        {"week": 4, "theme": "Emails & relance", "time": "4–6 h", "owner": "Fondateur/CM",
         "tasks": ["Séquence d’accueil (3 emails)", "Retargeting visiteurs 30j", "Tableau de bord simple (leads, coût)"]},
        {"week": 5, "theme": "Amélioration", "time": "4–6 h", "owner": "Fondateur/CM",
         "tasks": ["A/B test titres page", "Ajouter mots-clés négatifs", "1 article SEO"]},
        {"week": 6, "theme": "Preuve sociale", "time": "3–5 h", "owner": "Fondateur/CM",
         "tasks": ["Collecter 3 avis", "Publier 1 mini étude de cas", "Relance email ciblée"]},
        {"week": 7, "theme": "Monter le volume", "time": "4–6 h", "owner": "Fondateur/CM",
         "tasks": ["Augmenter budget sur campagnes qui marchent", "Nouvelles audiences similaires", "2e article SEO"]},
        {"week": 8, "theme": "Événement simple", "time": "4–6 h", "owner": "Fondateur/CM",
         "tasks": ["Planifier un live / webinar court", "Invitations email & social", "Page d’inscription"]},
        {"week": 9, "theme": "Suivi commercial", "time": "3–5 h", "owner": "Fondateur/Sales",
         "tasks": ["Script d’appel", "Relance sous 48 h des contacts", "Prioriser les plus chauds"]},
        {"week":10, "theme": "Optimisation créas", "time": "4–6 h", "owner": "Fondateur/CM",
         "tasks": ["Refaire 2 vidéos/visuels gagnants", "Retargeting catalogue (si e-commerce)", "3e article SEO"]},
        {"week":11, "theme": "Qualité base email", "time": "2–3 h", "owner": "Fondateur/CM",
         "tasks": ["Nettoyer liste", "Segmenter par intérêt", "Relances personnalisées"]},
        {"week":12, "theme": "Bilan & suite", "time": "3–4 h", "owner": "Fondateur/CM",
         "tasks": ["Comparer coûts/contacts par canal", "Garder ce qui marche, couper le reste", "Plan mois 4–6"]},
    ]

    objectives = {
        "north_star": (objectif or "Augmenter régulièrement les contacts qualifiés et les ventes"),
        "targets": [
            "Obtenir des contacts chaque semaine dès le mois 2",
            "Améliorer le coût par contact de 15–25% d’ici 3 mois",
            "Transformer au moins 20% des contacts en prospects sérieux (B2B) ou 3–5% en ventes (e-commerce)",
        ],
    }

    return {
        "objectives": objectives,
        "icp": p.get("persona") or (idea_snapshot or {}).get("persona") or "Décris en 1 phrase ton client idéal (rôle/usage).",
        "funnel": funnel,
        "channel_mix": channel_mix,
        "assumptions": assumptions,
        "monthly_budget": round(monthly_budget, 2),
        "agenda": agenda,
        "kpis": ["Coût par contact", "Nombre de contacts", "Taux de conversion", "Ventes/Opportunités"],
        "forecast_scenarios": _build_forecast_6m(assumptions, monthly_budget),
        "notes": "Ces chiffres sont des médianes par secteur. Ajuste dès 2–3 semaines avec tes vraies données (coûts, clics, conversions).",
    }

# ─────────────────────────────────────────────────────────────────────────────
# BUSINESS PLAN STRUCTURÉ (≈20 pages)
# ─────────────────────────────────────────────────────────────────────────────

from math import pow

def _norm(s: str | None) -> str:
    return (s or "").lower()

def _seed_from_context(user_id: int | None, project_id: int | None, titre: str | None) -> int:
    base = f"{user_id}-{project_id}-{titre or ''}"
    return int(hashlib.md5(base.encode("utf-8")).hexdigest()[:8], 16)

def _jitter(val: float, pct: float, rnd: random.Random) -> float:
    """Applique une variation stable ±pct%."""
    return val * (1.0 + rnd.uniform(-pct, pct))

def _sector_profile(secteur: str) -> dict:
    s = _norm(secteur)
    # Profils FR “par défaut” (bornes conservatrices, pas des vérités absolues)
    if any(k in s for k in ["saas", "logiciel", "app", "plateforme"]):
        return {
            "model": "saas",
            "arpu_month_range": (30, 180),
            "churn_m_range": (0.8, 5.0),      # %/mois
            "gm_pct_range": (75, 92),
            "cac_blended_range": (20, 160),
            "seasonality": [0.98, 0.99, 1.00, 1.01, 1.03, 1.05, 1.05, 1.03, 1.01, 1.00, 0.99, 0.98],
            "dso_days": 15, "dpo_days": 30, "inv_days": 0,
        }
    if any(k in s for k in ["ecommerce", "e-commerce", "boutique", "retail", "q-commerce"]):
        return {
            "model": "ecom",
            "aov_range": (25, 120),           # panier moyen
            "conv_site_range": (0.6, 3.0),    # %
            "return_rate_range": (2, 12),     # %
            "gm_pct_range": (35, 65),
            "cac_blended_range": (8, 60),
            "seasonality": [0.90, 0.92, 0.98, 1.00, 1.04, 1.08, 1.12, 1.06, 1.00, 1.02, 1.10, 1.20],
            "dso_days": 2, "dpo_days": 30, "inv_days": 40,
        }
    # Services/Agence/Conseil (par défaut)
    return {
        "model": "services",
        "tj_range": (350, 950),
        "util_rate_range": (45, 75),       # % facturable
        "gm_pct_range": (40, 70),
        "cac_blended_range": (15, 120),
        "seasonality": [0.95, 0.97, 1.00, 1.02, 1.05, 1.06, 1.04, 1.01, 0.98, 0.97, 0.96, 0.95],
        "dso_days": 35, "dpo_days": 30, "inv_days": 0,
    }

def build_calibration_snapshot(
    user_id: int | None,
    project_id: int | None,
    titre: str | None,
    profil: "ProfilRequest",
    idea_snapshot: dict | None,
) -> dict:
    rnd = random.Random(_seed_from_context(user_id, project_id, titre))
    sect = getattr(profil, "secteur", None) or (idea_snapshot or {}).get("sector") or ""
    prof = _sector_profile(sect)

    # Bornes → tirage stable (pour éviter clones)
    def pick(a, b): return _jitter((a + b)/2.0, 0.15, rnd)

    model = prof["model"]
    if model == "saas":
        arpu = pick(*prof["arpu_month_range"])
        churn = pick(*prof["churn_m_range"])
        gm = pick(*prof["gm_pct_range"])
        cac = pick(*prof["cac_blended_range"])
        base = {"arpu_month": arpu, "churn_m_pct": churn, "gm_pct": gm, "cac_blended": cac}
    elif model == "ecom":
        aov = pick(*prof["aov_range"])
        conv = pick(*prof["conv_site_range"])
        ret = pick(*prof["return_rate_range"])
        gm = pick(*prof["gm_pct_range"])
        cac = pick(*prof["cac_blended_range"])
        base = {"aov": aov, "site_conv_pct": conv, "return_rate_pct": ret, "gm_pct": gm, "cac_blended": cac}
    else:
        tj = pick(*prof["tj_range"])
        util = pick(*prof["util_rate_range"])
        gm = pick(*prof["gm_pct_range"])
        cac = pick(*prof["cac_blended_range"])
        base = {"tj_eur": tj, "util_rate_pct": util, "gm_pct": gm, "cac_blended": cac}

    # Croissance & Mkt ratio selon objectif
    obj = _norm(getattr(profil, "objectif", "") or (idea_snapshot or {}).get("objective", ""))
    if any(k in obj for k in ["venture", "hyper", "levée", "seed", "série"]):
        growth_mom = rnd.uniform(0.08, 0.18)
        mkt_ratio = rnd.uniform(0.12, 0.28)
        runway_target_m = 18
    else:
        growth_mom = rnd.uniform(0.03, 0.10)
        mkt_ratio = rnd.uniform(0.06, 0.15)
        runway_target_m = 12

    # Charges fixes plancher par modèle
    if model == "saas": opex_floor = rnd.uniform(7000, 15000)
    elif model == "ecom": opex_floor = rnd.uniform(9000, 18000)
    else: opex_floor = rnd.uniform(6000, 14000)

    return {
        "model": model,
        "seasonality": prof["seasonality"],
        "dso_days": prof["dso_days"],
        "dpo_days": prof["dpo_days"],
        "inv_days": prof["inv_days"],
        "growth_mom": growth_mom,
        "mkt_ratio": mkt_ratio,
        "opex_floor": opex_floor,
        "runway_target_m": runway_target_m,
        **base,
    }

def _bp_map_industry(secteur: str | None) -> str:
    s = (secteur or "").lower()
    if any(k in s for k in ["e-com", "boutique", "retail", "shop"]): return "ecommerce_b2c"
    if any(k in s for k in ["saas", "logiciel", "b2b", "crm", "erp", "data"]): return "saas_b2b"
    if any(k in s for k in ["industrie", "robot", "iot", "manufact", "usine"]): return "industry_b2b"
    if any(k in s for k in ["mobile", "app", "application"]): return "mobile_app"
    if any(k in s for k in ["formation", "coaching", "infoproduit"]): return "info_b2c"
    if any(k in s for k in ["service", "artisan", "local"]): return "services_locaux"
    return "generic_b2b"

def _bp_defaults(secteur: str | None, objectif: str | None) -> dict:
    cat = _bp_map_industry(secteur)
    # valeurs de base par secteur (réalistes mais génériques)
    base = {
        "saas_b2b":     dict(price=190.0, units_m1=22,  mom_growth=0.09, gm=0.82, var_rate=0.18, opex=12000, payroll=16000, mkt_ratio=0.22,
                             investments=[("Dév. produit", 12000, 1, 3), ("Site & outils", 6000, 1, 3)],
                             tax_rate=0.25, loan_rate=0.055, loan_years=4),
        "ecommerce_b2c":dict(price=64.0,  units_m1=380, mom_growth=0.07, gm=0.45, var_rate=0.55, opex=8000,  payroll=9000,  mkt_ratio=0.15,
                             investments=[("Stock initial", 15000, 1, 3), ("Site & shooting", 5000, 1, 3)],
                             tax_rate=0.25, loan_rate=0.06,  loan_years=3),
        "industry_b2b": dict(price=1400.0,units_m1=6,   mom_growth=0.06, gm=0.35, var_rate=0.65, opex=14000, payroll=18000, mkt_ratio=0.08,
                             investments=[("Machines/Outillage", 30000, 1, 5), ("Logiciels/ERP", 10000, 1, 4)],
                             tax_rate=0.25, loan_rate=0.052, loan_years=5),
        "mobile_app":   dict(price=10.0,  units_m1=2200,mom_growth=0.08, gm=0.85, var_rate=0.15, opex=6000,  payroll=14000, mkt_ratio=0.20,
                             investments=[("App & assets", 10000, 1, 3)],
                             tax_rate=0.25, loan_rate=0.055, loan_years=3),
        "info_b2c":     dict(price=79.0,  units_m1=90,  mom_growth=0.08, gm=0.75, var_rate=0.25, opex=5000,  payroll=9000,  mkt_ratio=0.18,
                             investments=[("Plateforme & studio", 7000, 1, 3)],
                             tax_rate=0.25, loan_rate=0.055, loan_years=3),
        "services_locaux": dict(price=180.0, units_m1=35,mom_growth=0.07, gm=0.70, var_rate=0.30, opex=7000, payroll=9000,  mkt_ratio=0.10,
                             investments=[("Véhicule/Matériel", 12000, 1, 4)],
                             tax_rate=0.25, loan_rate=0.055, loan_years=4),
        "generic_b2b":  dict(price=600.0, units_m1=10,  mom_growth=0.07, gm=0.60, var_rate=0.40, opex=10000, payroll=14000, mkt_ratio=0.15,
                             investments=[("Site & outils", 6000, 1, 3)],
                             tax_rate=0.25, loan_rate=0.055, loan_years=4),
    }[cat]

    # objectif agressif → un peu plus d’opex & de croissance
    if objectif and any(k in objectif.lower() for k in ["agress", "scale", "hyper", "x2"]):
        base["mom_growth"] *= 1.15
        base["mkt_ratio"]  *= 1.2
        base["opex"]       *= 1.1
    return base | {"category": cat}

def _annuity_pmt(principal: float, rate_year: float, years: int) -> float:
    r = rate_year / 12.0
    n = years * 12
    if r == 0:
        return principal / max(n, 1)
    return principal * (r / (1 - pow(1 + r, -n)))

def _adapt_investments(params: dict, cal: dict, seed: int) -> list[tuple[str, float, int, int]]:
    """
    Varie légèrement les montants d'investissements par projet (±25%) de façon stable (seed).
    Conserve (label, month, life_years) inchangés.
    """
    rnd = random.Random(seed + 77)
    items: list[tuple[str, float, int, int]] = []
    for (label, amount, month, life_y) in params.get("investments", []) or []:
        amt = round(float(amount) * (1.0 + rnd.uniform(-0.25, 0.25)), 2)
        items.append((label, amt, int(month or 1), int(life_y or 3)))
    return items

def _build_invest_depreciation(investments: list[tuple[str, float, int, int]], horizon_months: int = 36):
    """
    investments: [(label, amount, month_acquisition>=1, lifetime_years), ...]
    Retourne:
      - items détaillés normalisés
      - dep_month[1..36] : dotations mensuelles
      - total_invest : somme des achats
    """
    items = []
    dep_month = [0.0] * (horizon_months + 1)  # 1-indexé
    total = 0.0
    for (label, amount, m, life_y) in investments or []:
        amount = float(amount or 0)
        m = max(1, int(m))
        life_y = max(1, int(life_y))
        total += amount
        monthly = amount / (life_y * 12)
        items.append({"label": label, "amount": round(amount, 2), "month": m, "life_years": life_y, "amort_month": round(monthly, 2)})
        for i in range(m, min(horizon_months, m + life_y * 12 - 1) + 1):
            dep_month[i] += monthly
    return items, dep_month, round(total, 2)

def _build_loan_schedule(principal: float, rate_year: float, years: int, start_month: int = 1, horizon_months: int = 36):
    if principal <= 0:
        return [], [0.0] * (horizon_months + 1), [0.0] * (horizon_months + 1)
    pmt = _annuity_pmt(principal, rate_year, years)
    sched = []
    balance = principal
    interest_m = [0.0] * (horizon_months + 1)
    principal_m = [0.0] * (horizon_months + 1)
    r = rate_year / 12.0
    for i in range(1, years * 12 + 1):
        mo = start_month + i - 1
        if mo > horizon_months:
            break
        interest = balance * r
        amort = pmt - interest
        balance = max(0.0, balance - amort)
        interest_m[mo] = interest
        principal_m[mo] = amort
        sched.append({"month": mo, "payment": round(pmt, 2), "interest": round(interest, 2), "principal": round(amort, 2), "balance": round(balance, 2)})
    return sched, interest_m, principal_m

def _forecast_36m_calibrated(cal: dict, params: dict) -> dict:
    """Retourne séries mensuelles cohérentes & uniques selon calibration."""
    months = 36
    seas = cal["seasonality"]
    model = cal["model"]

    revenue = [0.0]*months
    cogs    = [0.0]*months
    marketing = [0.0]*months
    fixed   = [max(params.get("fixed_base", 0.0), cal["opex_floor"])]*months
    payroll = [params.get("payroll_base", 0.0)]*months

    # Budget marketing comme % du CA (avec latence de 1 mois)
    # On démarre avec un socle fixe pour amorcer l’acquisition
    mkt_min = max(1500.0, 0.3*fixed[0])

    growth = cal["growth_mom"]
    gm_pct = cal["gm_pct"]/100.0
    mkt_ratio = cal["mkt_ratio"]

    # Amorce MRR / commandes / jours facturés
    base_scale = 1.0
    if model == "saas":
        arpu = cal["arpu_month"]
        churn = cal["churn_m_pct"]/100.0
        mrr = 800.0  # MRR initial réaliste (variera avec growth)
        subs = max(5.0, mrr / max(arpu, 1e-6))
        for m in range(months):
            # growth + saisonnalité (faible en SaaS)
            subs = subs * (1.0 + growth*0.9)
            churn_loss = subs * churn
            net_subs = subs - churn_loss
            mrr = net_subs * arpu
            revenue[m] = mrr * (0.98 + 0.02*seas[m%12])
            cogs[m] = revenue[m] * (1.0 - gm_pct)
            marketing[m] = max(mkt_min, revenue[m-1]*mkt_ratio if m>0 else mkt_min)

    elif model == "ecom":
        aov = cal["aov"]
        conv = cal["site_conv_pct"]/100.0
        ret = cal["return_rate_pct"]/100.0
        visits = 8000.0
        for m in range(months):
            visits *= (1.0 + growth) * (0.96 + 0.04*seas[m%12])  # saisonnalité marquée
            orders = visits * conv
            gross_sales = orders * aov
            net_sales = gross_sales * (1.0 - ret)
            revenue[m] = net_sales
            cogs[m] = revenue[m] * (1.0 - gm_pct)
            marketing[m] = max(mkt_min, revenue[m-1]*mkt_ratio if m>0 else mkt_min)

    else:  # services
        tj = cal["tj_eur"]; util = cal["util_rate_pct"]/100.0
        days_cap = 20.0  # jours/mois par FTE facturable
        ftes = 1.0
        for m in range(months):
            ftes *= (1.0 + growth*0.5)
            fact_days = ftes * days_cap * util
            revenue[m] = fact_days * tj * (0.97 + 0.03*seas[m%12])
            cogs[m] = revenue[m] * (1.0 - gm_pct)
            marketing[m] = max(mkt_min, revenue[m-1]*mkt_ratio if m>0 else mkt_min)

    # EBITDA
    ebitda = [round(revenue[i] - cogs[i] - marketing[i] - fixed[i] - payroll[i], 2) for i in range(months)]
    return {
        "revenue": [round(x, 2) for x in revenue],
        "cogs": [round(x, 2) for x in cogs],
        "marketing": [round(x, 2) for x in marketing],
        "fixed": [round(x, 2) for x in fixed],
        "payroll": [round(x, 2) for x in payroll],
        "ebitda": ebitda,
    }

def _breakeven(cal: dict, params: dict, fore: dict) -> dict:
    """
    Retourne :
      - month : 1..36 si EBITDA mensuel >= 0 atteint, sinon None
      - revenue_month : CA du mois charnière (si atteint)
      - revenue : CA ANNUEL à atteindre (théorique, marge contributive)
      - month_hint : texte lisible (Mxx, ou “non atteint sur 36 mois”, ou alerte marge négative)
    """
    # 1) Repère empirique sur les 36 mois (EBITDA >= 0)
    month = None
    revenue_month = None
    for i in range(len(fore["revenue"])):  # 0..35
        e = fore["revenue"][i] - fore["cogs"][i] - fore["marketing"][i] - fore["fixed"][i] - fore["payroll"][i]
        if e >= 0:
            month = i + 1
            revenue_month = round(fore["revenue"][i], 2)
            break

    # 2) CA annuel théorique à atteindre (marge contributive)
    gm_eff = (cal.get("gm_pct", None) or (params.get("gm") * 100.0)) / 100.0  # cal.gm_pct si dispo, sinon params.gm
    mkt_ratio = float(cal.get("mkt_ratio", params.get("mkt_ratio", 0.15)))

    if gm_eff - mkt_ratio <= 0:
        return {
            "month": month,
            "revenue_month": revenue_month,
            "revenue": None,
            "month_hint": "marge contributive négative (revoyez GM% et/ou le ratio marketing)"
        }

    # Charges fixes + payroll sur 12 mois (plus réaliste que opex*12)
    fixed_year = sum(fore["fixed"][:12]) + sum(fore["payroll"][:12])
    revenue_annual_needed = round(fixed_year / (gm_eff - mkt_ratio), 2)

    month_hint = f"M{month}" if month else "non atteint sur 36 mois"
    return {
        "month": month,
        "revenue_month": revenue_month,
        "revenue": revenue_annual_needed,        # <- clé attendue par ton renderer
        "month_hint": month_hint
    }

def _compute_bfr(cal: dict, series: dict) -> float:
    """
    BFR simple: stock + créances - dettes fournisseurs.
    Approche par jours moyens (DSO/DPO/INV) sur un mois moyen de croisière (M7–M12).
    """
    rev = series["revenue"]; cogs = series["cogs"]
    mid = rev[6:12] if len(rev) >= 12 else rev
    mid_cogs = cogs[6:12] if len(cogs) >= 12 else cogs
    avg_rev = sum(mid)/max(len(mid), 1)
    avg_cogs = sum(mid_cogs)/max(len(mid_cogs), 1)

    dso = cal["dso_days"]; dpo = cal["dpo_days"]; invd = cal["inv_days"]
    receivables = avg_rev * (dso/30.0)
    payables = avg_cogs * (dpo/30.0)
    inventory = avg_cogs * (invd/30.0)

    bfr = max(0.0, inventory + receivables - payables)
    return float(round(bfr, 2))

def _recommended_funding(series: dict, bfr: float, runway_target_m: int) -> float:
    """
    Levée recommandée: runway cible * burn moyen 6 prochains mois + BFR + 10% buffer.
    """
    e = series["ebitda"]
    # burn = -min(EBITDA, 0)
    burns = [max(0.0, -x) for x in e[:6]] if len(e) >= 6 else [max(0.0, -x) for x in e]
    avg_burn_6m = sum(burns)/max(len(burns), 1)
    ask = runway_target_m * avg_burn_6m + bfr
    ask *= 1.10  # buffer
    return float(round(ask, 2))

# --- utils agrégations / investissements / P&L / cash -----------------------

def _aggregate_years(series: list[float]) -> list[float]:
    """Somme par année 1..3 depuis une série mensuelle 0..35"""
    y1 = round(sum(series[:12]), 2)
    y2 = round(sum(series[12:24]), 2)
    y3 = round(sum(series[24:36]), 2)
    return [y1, y2, y3]

def _invest_outflow_monthly(investments: list[tuple[str, float, int, int]], horizon_months: int = 36) -> list[float]:
    """Retourne un tableau 1-indexé des décaissements d'investissements (mois d'achat)."""
    out = [0.0] * (horizon_months + 1)
    for (_label, amount, m, _life_y) in investments or []:
        m = max(1, int(m or 1))
        if m <= horizon_months:
            out[m] += float(amount or 0.0)
    return out

def _pnl_3y_from_forecast(fore: dict, dep_m: list[float], loan_int_m: list[float], tax_rate: float) -> dict:
    """Agrège un P&L 3 ans depuis les séries mensuelles calibrées."""
    revenue   = fore["revenue"]
    cogs      = fore["cogs"]
    marketing = fore["marketing"]
    fixed     = fore["fixed"]
    payroll   = fore["payroll"]
    ebitda_m  = [revenue[i] - cogs[i] - marketing[i] - fixed[i] - payroll[i] for i in range(len(revenue))]

    def _sum_year(slice_):
        return round(sum(slice_), 2)

    y1 = slice(0, 12); y2 = slice(12, 24); y3 = slice(24, 36)

    rev_y   = [_sum_year(revenue[y1]), _sum_year(revenue[y2]), _sum_year(revenue[y3])]
    cogs_y  = [_sum_year(cogs[y1]),    _sum_year(cogs[y2]),    _sum_year(cogs[y3])]
    gross_y = [round(rev_y[i] - cogs_y[i], 2) for i in range(3)]
    mkt_y   = [_sum_year(marketing[y1]), _sum_year(marketing[y2]), _sum_year(marketing[y3])]
    fix_y   = [_sum_year(fixed[y1]),     _sum_year(fixed[y2]),     _sum_year(fixed[y3])]
    pay_y   = [_sum_year(payroll[y1]),   _sum_year(payroll[y2]),   _sum_year(payroll[y3])]
    ebd_y   = [_sum_year(ebitda_m[y1]),  _sum_year(ebitda_m[y2]),  _sum_year(ebitda_m[y3])]
    dep_y   = [_sum_year(dep_m[1:13]),   _sum_year(dep_m[13:25]),  _sum_year(dep_m[25:37])]
    int_y   = [_sum_year(loan_int_m[1:13]), _sum_year(loan_int_m[13:25]), _sum_year(loan_int_m[25:37])]

    ebit_y = [round(ebd_y[i] - dep_y[i], 2) for i in range(3)]
    ebt_y  = [round(ebit_y[i] - int_y[i], 2) for i in range(3)]
    tax_y  = [round(max(0.0, ebt_y[i]) * tax_rate, 2) for i in range(3)]
    net_y  = [round(ebt_y[i] - tax_y[i], 2) for i in range(3)]

    return {
        "revenue": rev_y, "cogs": cogs_y, "gross": gross_y,
        "marketing": mkt_y, "fixed": [round(fix_y[i] + pay_y[i], 2) for i in range(3)],
        "ebitda": ebd_y, "depreciation": dep_y, "interest": int_y,
        "ebit": ebit_y, "ebt": ebt_y, "tax": tax_y, "net": net_y
    }

def _cash_12m_from_forecast(fore: dict, loan_int_m: list[float], loan_prin_m: list[float], start_cash: float) -> tuple[float, list[dict]]:
    """
    Trésorerie 12 mois (simple & lisible) :
    - Encaissements = CA mensuel (hypothèse conservative).
    - Décaissements = COGS + Marketing + Fixed + Payroll + Intérêts + Principal.
    - start_cash = capitaux propres + emprunt - investissements (capex).
    """
    cash = []
    bal = float(round(start_cash, 2))
    for m in range(1, 13):
        inflow  = fore["revenue"][m-1]
        outflow = fore["cogs"][m-1] + fore["marketing"][m-1] + fore["fixed"][m-1] + fore["payroll"][m-1] + loan_int_m[m] + loan_prin_m[m]
        bal = round(bal + inflow - outflow, 2)
        cash.append({"month": m, "in": round(inflow, 2), "out": round(outflow, 2), "end": bal})
    return start_cash, cash

def _pnl_3y_from_series(fore: dict, dep_m: list[float], loan_int_m: list[float], tax_rate: float) -> dict:
    """Construit un P&L annuel (Y1..Y3) à partir des séries mensuelles calibrées."""
    # séries mensuelles 0..35 ; dep_m et loan_int_m sont 1-indexés
    gross_m     = [max(0.0, fore["revenue"][i] - fore["cogs"][i]) for i in range(36)]
    dep_m_0     = [float(dep_m[i+1] if i+1 < len(dep_m) else 0.0) for i in range(36)]
    interest_0  = [float(loan_int_m[i+1] if i+1 < len(loan_int_m) else 0.0) for i in range(36)]
    ebit_m      = [round(fore["ebitda"][i] - dep_m_0[i], 2) for i in range(36)]
    ebt_m       = [round(ebit_m[i] - interest_0[i], 2) for i in range(36)]
    tax_m       = [round(max(0.0, ebt_m[i]) * tax_rate, 2) for i in range(36)]
    net_m       = [round(ebt_m[i] - tax_m[i], 2) for i in range(36)]

    return {
        "revenue":      _aggregate_years(fore["revenue"]),
        "cogs":         _aggregate_years(fore["cogs"]),
        "gross":        _aggregate_years(gross_m),
        "marketing":    _aggregate_years(fore["marketing"]),
        "fixed":        _aggregate_years(fore["fixed"]),
        "payroll":      _aggregate_years(fore["payroll"]),
        "ebitda":       _aggregate_years(fore["ebitda"]),
        "depreciation": _aggregate_years(dep_m_0),
        "interest":     _aggregate_years(interest_0),
        "ebit":         _aggregate_years(ebit_m),
        "ebt":          _aggregate_years(ebt_m),
        "tax":          _aggregate_years(tax_m),
        "net":          _aggregate_years(net_m),
    }

def _cash_12m_from_series(
    fore: dict,
    invest_out_m: list[float],     # 1-indexé
    loan_int_m: list[float],       # 1-indexé
    loan_prin_m: list[float],      # 1-indexé
    equity_inflow: float,
    loan_inflow: float
) -> tuple[float, list[dict]]:
    """
    Trésorerie sur 12 mois — approche directe : encaissements = CA ; décaissements = coûts + service de la dette + CAPEX.
    On suppose versement equity + prêt au M1.
    """
    cash = []
    bal = equity_inflow + loan_inflow
    for m in range(1, 13):
        i = m - 1  # index 0..11
        inflow  = fore["revenue"][i]
        outflow = (
            fore["cogs"][i] + fore["marketing"][i] + fore["fixed"][i] + fore["payroll"][i]
            + float(loan_int_m[m] if m < len(loan_int_m) else 0.0)
            + float(loan_prin_m[m] if m < len(loan_prin_m) else 0.0)
            + float(invest_out_m[m] if m < len(invest_out_m) else 0.0)
        )
        bal += inflow - outflow
        cash.append({"month": m, "in": round(inflow, 2), "out": round(outflow, 2), "end": round(bal, 2)})
    return round(equity_inflow + loan_inflow, 2), cash

def _break_even(params: dict):
    """Point mort basé sur marge contributive = GM% - mkt_ratio."""
    mc_ratio = params["gm"] - params["mkt_ratio"]
    fixed_year = (params["opex"] + params["payroll"]) * 12
    if mc_ratio <= 0:
        return {"revenue": None, "comment": "Marge contributive négative (revoyez la structure de coûts)."}
    rev_needed = fixed_year / mc_ratio
    months = 12 * (1 + 0.0)  # approx
    return {"revenue": round(rev_needed, 2), "month_hint": "entre M10 et M18 selon la traction"}

def _safe_json_loads_bp(s: str) -> dict:
    try:
        return json.loads(s)
    except Exception:
        st, en = s.find("{"), s.rfind("}")
        if st >= 0 and en > st:
            return json.loads(s[st:en+1])
        raise

def _prompt_bp_copy(context: Dict[str, Any]) -> str:
    """
    Produit UNIQUEMENT les textes (~15 pages) d’un Business Plan FR/UE,
    en JSON strict 'copy'. L'étape C (ancrage marché) est intégrée via [CALIBRATION].
    """
    return (
        # === Format & langue
        "Réponds EXCLUSIVEMENT par un JSON brut avec EXACTEMENT la clé 'copy'. "
        "Aucune autre clé. Pas de ```.\n"
        "Langue: français (FR). Monnaie: euro (€).\n\n"

        # === Objectif
        "Objectif: Rédiger le contenu COMPLET d’un Business Plan (~15 pages) en français, "
        "style expert-comptable, prêt pour banque/investisseur, adapté au marché FR/UE.\n\n"

        # === Étape C : ancrage par hypothèses calibrées (NE RIEN INVENTER)
        "ANCRAGE OBLIGATOIRE:\n"
        "- Utilise UNIQUEMENT les nombres provenant de CONTEXTE.assumptions, CONTEXTE.metrics "
        "et CALIBRATION.derived (ainsi que leurs fourchettes/ranges éventuelles).\n"
        "- Si une valeur n’est pas fournie, N’INVENTE PAS de chiffre: décris qualitativement "
        "(« ordre de grandeur faible/moyen/élevé », « à confirmer ») et propose l’hypothèse à tester.\n"
        "- Aligne les formulations métier avec CALIBRATION.signals (price_tier, geo, channel_mix, etc.).\n"
        "- Ne cite pas de sources externes chiffrées qui ne figurent PAS dans CALIBRATION.sources.\n\n"

        # === Schéma STRICT attendu
        "Schéma STRICT requis:\n"
        "{\n"
        "  \"copy\": {\n"
        "    \"executive_summary\": \"string non vide (proposition de valeur, traction visée, ordres de grandeur, point mort)\",\n"
        "    \"team\": \"string non vide (rôles, crédibilité)\",\n"
        "    \"project\": \"string non vide (problème, solution, différenciation, modèle FR/UE)\",\n"
        "    \"market\": {\n"
        "      \"size_drivers\": \"string non vide (marché FR puis ouverture UE; ancrer aux drivers du secteur)\",\n"
        "      \"segments\": [\"≥3 items (personas/secteurs spécifiques au projet)\"],\n"
        "      \"competition\": [\"≥3 acteurs/alternatives FR/UE (catégories si noms absents)\"],\n"
        "      \"regulation\": [\"≥3 points (RGPD/CNIL si pertinent, normes/qualité, obligations sectorielles)\"]\n"
        "    },\n"
        "    \"go_to_market\": {\n"
        "      \"segmentation\": [\"≥3 items (ICP + secondaires; refléter price_tier/geo/canaux)\"],\n"
        "      \"positioning\": \"string non vide (promesse, preuve, différenciation)\",\n"
        "      \"mix\": [\"Produit\", \"Prix\", \"Distribution\", \"Communication\"],\n"
        "      \"sales_process\": [\"≥4 étapes + KPI (CAC, conversion, churn/LTV si récurrent) – sans inventions\"]\n"
        "    },\n"
        "    \"operations\": {\n"
        "      \"organization\": \"string non vide (org cible, processus clés)\",\n"
        "      \"people\": [\"≥4 rôles adaptés au modèle (saas/ecom/agence/QSR…)\"],\n"
        "      \"resources\": [\"≥4 ressources (stack, infra, prestataires, conformité)\"],\n"
        "      \"roadmap\": [\"jalons sur 24 mois avec livrables; cohérents avec CALIBRATION.growth & hiring\"]\n"
        "    },\n"
        "    \"legal\": {\n"
        "      \"form\": \"string non vide (ex: SAS)\",\n"
        "      \"rationale\": \"string non vide (investisseurs, gouvernance, régime social)\",\n"
        "      \"cap_table\": [\"répartition du capital (exemples)\"],\n"
        "      \"governance\": [\"pacte d’associés, pouvoirs, clauses (préemption, leaver…)\"],\n"
        "      \"tax_social\": [\"IS/TVA, régime social dirigeant\"]\n"
        "    },\n"
        "    \"funding\": {\n"
        "      \"ask\": \"string non vide (montant demandé; rattacher aux besoins BFR/EBITDA/roadmap)\",\n"
        "      \"use_of_funds\": [\"≥4 usages: produit, go-to-market, recrutement, BFR…\"],\n"
        "      \"milestones\": [\"jalons conditionnels liés au financement\"]\n"
        "    },\n"
        "    \"risks\": [\"≥6 risques + parades (marché, technique, réglementaire, finance)\"],\n"
        "    \"glossary\": {\"Terme 1\":\"Définition\", \"Terme 2\":\"Définition\", \"...\":\"...\"}\n"
        "  }\n"
        "}\n\n"

        # === Contraintes rédactionnelles (personnalisation visible)
        "Contraintes:\n"
        "- Style clair, professionnel, factuel. FR/UE; euros; pas de buzzwords.\n"
        "- Chaque section doit intégrer AU MOINS 2 éléments spécifiques extraits de CONTEXTE et/ou CALIBRATION "
        "(ex: persona/geo/price_tier/canaux/positionnement/capacité).\n"
        "- Pas de chiffres contradictoires avec CONTEXTE.metrics/assumptions/CALIBRATION. "
        "Si incertitude: nomme « Hypothèse à valider ».\n\n"

        # === Matrices d'ancrage
        "Tu disposes de 3 blocs de données. Utilise-les comme vérité de référence:\n"
        "[CONTEXTE]\n" + json.dumps(context, ensure_ascii=False) + "\n\n" +
        "[CALIBRATION]\n" + json.dumps(context.get("calibration", {}), ensure_ascii=False) + "\n\n" +

        # === Check de sortie
        "Avant d’émettre le JSON, vérifie mentalement: (1) aucune valeur chiffrée hors CONTEXTE/CALIBRATION, "
        "(2) cohérence sectorielle et géographique, (3) personnalisation visible.\n"
    )

def _validate_bp_copy(copy: Dict[str, Any]) -> list[str]:
    issues = []
    required_top = ["executive_summary","team","project","market","go_to_market","operations","legal","funding","risks","glossary"]
    for k in required_top:
        if k not in copy:
            issues.append(f"Clé manquante: copy.{k}")
    if issues: return issues

    def non_empty_str(k):
        v = copy.get(k)
        if not isinstance(v, str) or not v.strip():
            issues.append(f"copy.{k} doit être un string non vide")

    non_empty_str("executive_summary")
    non_empty_str("team")
    non_empty_str("project")

    # market
    m = copy["market"]
    if not isinstance(m, dict): issues.append("copy.market doit être un objet")
    else:
        if not isinstance(m.get("size_drivers",""), str) or not m["size_drivers"].strip():
            issues.append("copy.market.size_drivers string non vide requis")
        for k, n in [("segments",3),("competition",3),("regulation",3)]:
            if not (isinstance(m.get(k), list) and len(m[k]) >= n):
                issues.append(f"copy.market.{k} doit contenir ≥{n} items")

    # gtm
    gtm = copy["go_to_market"]
    if not isinstance(gtm, dict): issues.append("copy.go_to_market doit être un objet")
    else:
        if not (isinstance(gtm.get("segmentation"), list) and len(gtm["segmentation"]) >= 3):
            issues.append("copy.go_to_market.segmentation ≥3 items")
        if not isinstance(gtm.get("positioning",""), str) or not gtm["positioning"].strip():
            issues.append("copy.go_to_market.positioning string non vide")
        if not (isinstance(gtm.get("mix"), list) and len(gtm["mix"]) >= 4):
            issues.append("copy.go_to_market.mix ≥4 items")
        if not (isinstance(gtm.get("sales_process"), list) and len(gtm["sales_process"]) >= 4):
            issues.append("copy.go_to_market.sales_process ≥4 items")

    # ops
    ops = copy["operations"]
    if not isinstance(ops, dict): issues.append("copy.operations doit être un objet")
    else:
        if not isinstance(ops.get("organization",""), str) or not ops["organization"].strip():
            issues.append("copy.operations.organization string non vide")
        if not (isinstance(ops.get("people"), list) and len(ops["people"]) >= 4):
            issues.append("copy.operations.people ≥4 items")
        if not (isinstance(ops.get("resources"), list) and len(ops["resources"]) >= 4):
            issues.append("copy.operations.resources ≥4 items")
        if not (isinstance(ops.get("roadmap"), list) and len(ops["roadmap"]) >= 3):
            issues.append("copy.operations.roadmap ≥3 items")

    # legal
    leg = copy["legal"]
    if not isinstance(leg, dict): issues.append("copy.legal doit être un objet")
    else:
        for k in ["form","rationale"]:
            if not isinstance(leg.get(k,""), str) or not leg[k].strip():
                issues.append(f"copy.legal.{k} string non vide requis")
        if not (isinstance(leg.get("cap_table"), list) and len(leg["cap_table"]) >= 1):
            issues.append("copy.legal.cap_table ≥1 item")
        if not (isinstance(leg.get("governance"), list) and len(leg["governance"]) >= 2):
            issues.append("copy.legal.governance ≥2 items")
        if not (isinstance(leg.get("tax_social"), list) and len(leg["tax_social"]) >= 2):
            issues.append("copy.legal.tax_social ≥2 items")

    # funding
    fund = copy["funding"]
    if not isinstance(fund, dict): issues.append("copy.funding doit être un objet")
    else:
        if not isinstance(fund.get("ask",""), str) or not fund["ask"].strip():
            issues.append("copy.funding.ask string non vide requis")
        if not (isinstance(fund.get("use_of_funds"), list) and len(fund["use_of_funds"]) >= 4):
            issues.append("copy.funding.use_of_funds ≥4 items")
        if not (isinstance(fund.get("milestones"), list) and len(fund["milestones"]) >= 3):
            issues.append("copy.funding.milestones ≥3 items")

    # risks
    if not (isinstance(copy.get("risks"), list) and len(copy["risks"]) >= 6):
        issues.append("copy.risks ≥6 items")

    # glossary
    gl = copy["glossary"]
    if not isinstance(gl, dict) or len(gl) < 10:
        issues.append("copy.glossary doit contenir ≥10 définitions")
    return issues

def _ensure_list(x):
    if isinstance(x, list):
        return [str(i).strip() for i in x if str(i).strip()]
    if isinstance(x, str) and x.strip():
        return [x.strip()]
    return []

def _defaults_lists_for_sector(sector: str | None) -> dict:
    s = (sector or "").lower()
    if any(k in s for k in ["industrie", "iot", "usine", "manufact"]):
        return {
            "market.segments": [
                "PME industrielles — Responsable Qualité",
                "ETI/Groupes — Directeur Production / QA",
                "Intégrateurs/SSII industriels (partenaires)"
            ],
            "market.competition": [
                "Solutions MES/SCADA avec modules qualité",
                "ERP + add-ons qualité",
                "Outils internes (Excel/BI maison)"
            ],
            "market.regulation": [
                "ISO 9001 / IATF 16949",
                "RGPD / CNIL (données industrielles & RH)",
                "Directive Machines / Sécurité au travail"
            ],
            "gtm.segmentation": [
                "ICP: sites 100–1000 salariés, lignes automatisées",
                "Secondaire: sous-traitants certifiés ISO",
                "Exclusion: ateliers <20 personnes sans data capteurs"
            ],
            "gtm.mix": [
                "Produit: plateforme IA + connecteurs MES/ERP",
                "Prix: abonnement + onboarding + option POC",
                "Distribution: direct + partenaires intégrateurs",
                "Communication: salons (Global Industrie), cas clients, SEO/LinkedIn"
            ],
            "gtm.sales_process": [
                "Lead → qualification (diagnostic données)",
                "POC 4–6 semaines sur une ligne",
                "Déploiement usine + MCO (support & SLA)"
            ],
            "ops.people": [
                "CEO / BizDev Industrie",
                "CTO / Data scientist senior",
                "Ingénieur déploiement (intégrations)",
                "CSM / Support Niveau 1"
            ],
            "ops.resources": [
                "Stack MLOps (tracking, serving, monitoring)",
                "Connecteurs MES/ERP, ETL/IIoT gateway",
                "Outils QA: ticketing, documentation, observabilité"
            ],
            "ops.roadmap": [
                "M0–3: POC client pilote & premiers modèles",
                "M4–12: Connecteurs standards, référentiel défauts",
                "M13–24: Scale multi-sites, marketplace d’algorithmes"
            ],
        }
    # défauts génériques
    return {
        "market.segments": ["Segment 1", "Segment 2", "Segment 3"],
        "market.competition": ["Concurrents A", "B", "Alternatives C"],
        "market.regulation": ["RGPD/CNIL", "Obligations sectorielles", "Code de commerce"],
        "gtm.segmentation": ["ICP prioritaire", "Segments secondaires", "Exclusions"],
        "gtm.mix": ["Produit …", "Prix …", "Distribution …", "Communication …"],
        "gtm.sales_process": ["Lead → Qualif", "Démo/POC", "Closing → Onboarding"],
        "ops.people": ["Rôle 1", "Rôle 2", "Rôle 3"],
        "ops.resources": ["Ressource 1", "Ressource 2", "Ressource 3"],
        "ops.roadmap": ["M0–3 …", "M4–12 …", "M13–24 …"],
    }

async def _generate_bp_copy(
    profil: "ProfilRequest",
    idea_snapshot: Optional[Dict[str, Any]],
    params: Dict[str, Any],
    metrics: Dict[str, Any],
) -> Dict[str, Any]:
    p = _profil_dump(profil)
    context = {
        "sector": p.get("secteur"),
        "objective": p.get("objectif"),
        "idea": (idea_snapshot or {}).get("idee"),
        "persona": (idea_snapshot or {}).get("persona") or p.get("persona"),
        "pain_points": (idea_snapshot or {}).get("pain_points"),
        "products_services": (idea_snapshot or {}).get("products_services"),
        "segments": (idea_snapshot or {}).get("segments"),
        "locations": (idea_snapshot or {}).get("locations"),
        "differentiation_points": (idea_snapshot or {}).get("differentiation_points"),
        "assumptions": {
            "price": params.get("price"),
            "mom_growth": params.get("mom_growth"),
            "gm": params.get("gm"),
            "mkt_ratio": params.get("mkt_ratio"),
            "opex": params.get("opex"),
            "payroll": params.get("payroll"),
            "tax_rate": params.get("tax_rate"),
            "loan_rate": params.get("loan_rate"),
            "loan_years": params.get("loan_years"),
        },
        "metrics": metrics,
        "calibration": metrics.get("calibration"),  # ✅ AJOUTE ceci
        "country_focus": "France",
        "regulatory_hints": ["RGPD/CNIL", "Code de la consommation/commerce", "Fiscalité IS/TVA (ordre de grandeur)"],
    }
    prompt = _prompt_bp_copy(context)

    try:
        resp = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=2000,
        )
        data = _safe_json_loads_bp(resp.choices[0].message.content)
        copy = data.get("copy") or {}
    except Exception:
        copy = {}

    # Coercition + defaults
    sect = p.get("secteur")
    defs = _defaults_lists_for_sector(sect)

    exec_summary = str(copy.get("executive_summary") or "")
    team = str(copy.get("team") or "")
    project = str(copy.get("project") or "")
    value_prop = str(copy.get("value_prop") or "")
    objectives = _ensure_list(copy.get("objectives") or [])

    market = copy.get("market") or {}
    market = market if isinstance(market, dict) else {}
    market_size = str(market.get("size_drivers") or "")
    market_segments = _ensure_list(market.get("segments"))
    market_competition = _ensure_list(market.get("competition"))
    market_regulation = _ensure_list(market.get("regulation"))

    gtm = copy.get("go_to_market") or {}
    gtm = gtm if isinstance(gtm, dict) else {}
    gtm_seg = _ensure_list(gtm.get("segmentation"))
    gtm_pos = str(gtm.get("positioning") or "")
    gtm_mix = _ensure_list(gtm.get("mix"))
    gtm_sales = _ensure_list(gtm.get("sales_process"))

    ops = copy.get("operations") or {}
    ops = ops if isinstance(ops, dict) else {}
    ops_org = str(ops.get("organization") or "")
    ops_people = _ensure_list(ops.get("people"))
    ops_res = _ensure_list(ops.get("resources"))
    ops_road = _ensure_list(ops.get("roadmap"))

    legal = copy.get("legal") or {}
    legal = legal if isinstance(legal, dict) else {}
    legal_form = str(legal.get("form") or "")
    legal_rat = str(legal.get("rationale") or "")
    legal_cap = _ensure_list(legal.get("cap_table"))
    legal_gov = _ensure_list(legal.get("governance"))
    legal_tax = _ensure_list(legal.get("tax_social"))

    glossary = copy.get("glossary")
    glossary = glossary if isinstance(glossary, dict) else {}

    # Inject defaults si vide
    if not market_segments: market_segments = defs["market.segments"]
    if not market_competition: market_competition = defs["market.competition"]
    if not market_regulation: market_regulation = defs["market.regulation"]

    if not gtm_seg: gtm_seg = defs["gtm.segmentation"]
    if not gtm_mix: gtm_mix = defs["gtm.mix"]
    if not gtm_sales: gtm_sales = defs["gtm.sales_process"]

    if not ops_people: ops_people = defs["ops.people"]
    if not ops_res: ops_res = defs["ops.resources"]
    if not ops_road: ops_road = defs["ops.roadmap"]

    # funding
    fnd = copy.get("funding")
    if not isinstance(fnd, dict):
        fnd = {"ask": str(fnd or ""), "use_of_funds": [], "milestones": []}
    if not isinstance(fnd.get("use_of_funds"), list):
        fnd["use_of_funds"] = [str(fnd.get("use_of_funds") or "")]
    if not isinstance(fnd.get("milestones"), list):
        fnd["milestones"] = [str(fnd.get("milestones") or "")]
    copy["funding"] = fnd

    # risks
    rks = copy.get("risks")
    if isinstance(rks, str): rks = [rks]
    if not isinstance(rks, list): rks = []
    copy["risks"] = rks

    # Retour structuré prêt pour le renderer
    return {
        "executive_summary": exec_summary,
        "team": team,
        "project": project,
        "value_prop": value_prop,
        "objectives": objectives,
        "market": {
            "size_drivers": market_size,
            "segments": market_segments,
            "competition": market_competition,
            "regulation": market_regulation,
        },
        "go_to_market": {
            "segmentation": gtm_seg,
            "positioning": gtm_pos,
            "mix": gtm_mix,
            "sales_process": gtm_sales,
        },
        "operations": {
            "organization": ops_org,
            "people": ops_people,
            "resources": ops_res,
            "roadmap": ops_road,
        },
        "legal": {
            "form": legal_form,
            "rationale": legal_rat,
            "cap_table": legal_cap,
            "governance": legal_gov,
            "tax_social": legal_tax,
        },
        "funding": copy["funding"],  # 👈 AJOUTE CECI
        "risks": copy["risks"],  # 👈 ET CECI
        "glossary": glossary,
    }

async def generate_business_plan_structured(profil: ProfilRequest, idea_snapshot: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    p = _profil_dump(profil)
    params = _bp_defaults(p.get("secteur"), p.get("objectif"))

    # Calibration unique par projet
    user_id = getattr(profil, "user_id", None)
    project_title = (idea_snapshot or {}).get("titre") or (idea_snapshot or {}).get("idee") or ""
    cal = build_calibration_snapshot(user_id, (idea_snapshot or {}).get("project_id"), project_title, profil, idea_snapshot or {})

    # Forecast calibré (36 mois)
    fore = _forecast_36m_calibrated(cal, params)

    # Investissements + amortissements (adaptés par projet)
    seed = _seed_from_context(user_id, (idea_snapshot or {}).get("project_id"), project_title)
    adapted_investments = _adapt_investments(params, cal, seed)
    inv_items, dep_m, invest_total = _build_invest_depreciation(adapted_investments, 36)
    invest_out_m = _invest_outflow_monthly(adapted_investments, 36)

    # BFR spécifique + levée recommandée
    bfr = _compute_bfr(cal, fore)
    recommended_ask = _recommended_funding(fore, bfr, cal["runway_target_m"])

    # Montage de financement : equity = ask ; prêt si besoin pour couvrir les uses
    uses_total = float(round(invest_total + bfr, 2))
    equity_rule = max(10000.0, 0.30 * uses_total)
    equity = float(round(min(uses_total, equity_rule), 2))
    loan_needed = float(round(max(0.0, uses_total - equity), 2))    # on complète par dette si nécessaire

    loan_rate  = float(params.get("loan_rate", 0.055))
    loan_years = int(params.get("loan_years", 3))
    loan_sched, loan_int_m, loan_prin_m = _build_loan_schedule(
        principal=loan_needed, rate_year=loan_rate, years=loan_years, start_month=1, horizon_months=36
    )

    # 4) P&L 3 ans (agrégé depuis forecast)
    pnl = _pnl_3y_from_forecast(fore, dep_m, loan_int_m, params.get("tax_rate", 0.25))

    # 5) Trésorerie 12 mois (point de départ = fonds propres + emprunt - capex)
    start_cash, cash12 = _cash_12m_from_forecast(
        fore, loan_int_m, loan_prin_m, start_cash=(equity + loan_needed - invest_total)
    )

    # Seuil de rentabilité (depuis les séries)
    breakeven = _breakeven(cal, params, fore)

    # 7) Besoin de financement equity (annonce lisible côté "funding")
    recommended_ask = _recommended_funding(fore, bfr, cal["runway_target_m"])

    # Métriques pour la COPY (avec calibration incluse)
    metrics = {
        "invest_total_eur": float(invest_total),
        "bfr_eur": float(bfr),
        "initial_equity_eur": float(equity),
        "initial_loan_eur": float(loan_needed),
        "breakeven_revenue_eur": breakeven["revenue"],
        "breakeven_hint": breakeven["month"],
        "y1_revenue_eur": round(sum(fore["revenue"][:12]), 2),
        "y2_revenue_eur": round(sum(fore["revenue"][12:24]), 2),
        "y3_revenue_eur": round(sum(fore["revenue"][24:36]), 2),
        "y1_ebitda_eur": round(sum(fore["ebitda"][:12]), 2),
        "y2_ebitda_eur": round(sum(fore["ebitda"][12:24]), 2),
        "y3_ebitda_eur": round(sum(fore["ebitda"][24:36]), 2),
        "calibration": cal,
    }

    copy = await _generate_bp_copy(profil, idea_snapshot, params, metrics)

    # P&L 3 ans (agrégé) et Cash 12 mois (détaillé)
    pnl_3y = _pnl_3y_from_series(fore, dep_m, loan_int_m, float(params.get("tax_rate", 0.25)))
    start_cash, cash12 = _cash_12m_from_series(
        fore, invest_out_m, loan_int_m, loan_prin_m, equity_inflow=equity, loan_inflow=loan_needed
    )

    # Assemblage final
    return {
        "meta": {
            "sector_category": params.get("category"),
            "sector": p.get("secteur"),
            "objective": p.get("objectif"),
            "persona": (idea_snapshot or {}).get("persona") or p.get("persona"),
        },
        "narrative": {
            "executive_summary": copy.get("executive_summary", ""),
            "team": copy.get("team", ""),
            "project": copy.get("project", ""),
            "value_prop": copy.get("value_prop", ""),
            "objectives": copy.get("objectives", []),
            "market": copy.get("market", {}),
            "go_to_market": copy.get("go_to_market", {}),
            "operations": copy.get("operations", {}),
            "legal": copy.get("legal", {}),  # ✅ LÉGAL CONSERVÉ
            "funding": {                      # ✅ FINANCEMENT TEXTUEL + CHIFFRÉ
                **copy.get("funding", {}),
                "recommended_ask_eur": round(recommended_ask, 2),  # 👈 recommandé (runway + BFR)
                "initial_plan": {  # 👈 miroir de la section financière
                    "uses": {
                        "investments": float(invest_total),
                        "working_capital": float(bfr),
                        "total": round(uses_total, 2),
                    },
                    "sources": {
                        "equity": round(equity, 2),
                        "loan": round(loan_needed, 2),
                        "total": round(equity + loan_needed, 2),
                    }
                },
                "loan_needed_eur": round(loan_needed, 2),  # rappel utile
                "bfr_eur": round(bfr, 2),
                "uses_total_eur": round(uses_total, 2),
            },
            "risks": copy.get("risks", []),
            "glossary": copy.get("glossary", {}),
        },
        "assumptions": params,
        "calibration_used": cal,
        "investments": {
            "items": inv_items,
            "total": invest_total,
            "depreciation_month": [round(x, 2) for x in dep_m],   # 1-indexé
        },
        "financing": {
            "initial_uses": {
                "investments": float(invest_total),
                "working_capital": float(bfr),
                "total": round(uses_total, 2),
            },
            "initial_sources": {
                "equity": round(equity, 2),
                "loan": round(loan_needed, 2),
                "total": round(equity + loan_needed, 2),
            },
            "loan": {
                "rate": loan_rate,
                "years": loan_years,
                "schedule": loan_sched,
            },
            "three_year_view": {
                "loan_outstanding_end_y1": loan_sched[11]["balance"] if len(loan_sched) >= 12 else loan_needed,
                "loan_outstanding_end_y2": loan_sched[23]["balance"] if len(loan_sched) >= 24 else max(0.0,
                                                                                                       loan_needed),
                "loan_outstanding_end_y3": loan_sched[35]["balance"] if len(loan_sched) >= 36 else 0.0,
            },
        },
        "pnl_3y": pnl_3y,                     # ✅ PLUS VIDE
        "cash_12m": {"start": start_cash, "months": cash12},  # ✅ PLUS VIDE
        "breakeven": breakeven,
        # === Séries pour graphiques (déjà calibrées)
        "series_36m": {
            "revenue": fore["revenue"],
            "ebitda": fore["ebitda"],
            "cogs": fore["cogs"],
            "marketing": fore["marketing"],
            "fixed": fore["fixed"],
            "payroll": fore["payroll"],
        },

        # === ANNEXES obligatoires (affichées par ton renderer)
        "annexes": {
            "Pièces juridiques": (
                "Projet de statuts (SAS/SARL), projet de pacte d’associés, "
                "projet de bail commercial/attestation domiciliation, Kbis (si existant), "
                "CNI dirigeant, attestations fiscales & sociales."
            ),
            "Pièces financières": (
                "Devis/factures d’investissements, RIB, tableau d’amortissements, "
                "prévisionnel 3 ans (P&L), plan de trésorerie 12 mois, échéancier d’emprunt."
            ),
            "Justificatifs opérationnels": (
                "Contrats/fiches de poste (si recrutements), conventions partenaires, "
                "polices d’assurances, preuves de propriété intellectuelle (si applicable)."
            )
        },
    }                  # revenue, ebitda, cogs, marketing, fixed, payroll


# PLAN D'ACTION
# ─────────────────────────────────────────────────────────────────────────────
class PlanTask(BaseModel):
    id: str
    title: str
    desc: Optional[str] = ""
    owner: Optional[str] = None
    estimate_h: Optional[float] = None
    due_offset_days: Optional[int] = None
    tags: List[str] = []
    deps: List[str] = []

class WeekPlan(BaseModel):
    week: int
    theme: str
    goals: List[str] = []
    kpis: List[str] = []
    tasks: List[PlanTask] = []

class CalendarEvent(BaseModel):
    title: str
    description: Optional[str] = ""
    start_iso: str
    end_iso: str
    tags: List[str] = []

class PlanResponse(BaseModel):
    plan: List[str]                          # compat UI
    weeks: Optional[List[WeekPlan]] = None   # nouveau
    schedule: Optional[List[CalendarEvent]] = None  # nouveau

def _load_plan_context_from_deliverables(project_id: int) -> dict:
    kinds = ["offer", "brand", "landing", "marketing", "model"]
    ctx = {}
    with get_session() as s:
        for k in kinds:
            d = s.exec(
                select(Deliverable)
                .where(Deliverable.project_id == project_id, Deliverable.kind == k)
                .order_by(Deliverable.created_at.desc())
            ).first()
            if not d:
                continue
            ctx[k] = d.json_content or {}
            if k == "landing" and d.file_path:
                try:
                    with open(d.file_path, "r", encoding="utf-8") as f:
                        ctx["landing_html"] = f.read()[:20000]  # snippet safe
                except Exception:
                    pass
    return ctx

def _normalize_owner_fr(owner: str | None) -> str | None:
    if not owner:
        return owner
    m = {
        "founder": "fondateur",
        "sales": "ventes",
        "marketing": "marketing",
        "tech": "tech",
        "engineering": "tech",
        "legal": "juridique",
        "finance": "finance",
        "ops": "ops",
        "operations": "ops",
        "data": "data",
        "product": "produit",
        "support": "support",
        "customer success": "support",
        "cs": "support",
    }
    key = owner.strip().lower()
    return m.get(key, owner)

def _prompt_action_plan(context: dict) -> str:
    return (
      # 🔒 Langue verrouillée
      "LANG=fr-FR — Rédige TOUT le contenu en FRANÇAIS (titres, thèmes, objectifs, tâches, descriptions, KPI, tags). "
      "Interdiction d’utiliser de l’anglais (sauf sigles usuels : RGPD, KPI, CRM, etc.).\n"
      "Réponds EXCLUSIVEMENT par un JSON brut avec EXACTEMENT la clé 'weeks'. Aucune autre clé. Pas de ```.\n\n"
      "Objectif: Produire un plan d’action exhaustif et planifiable pour LANCER le projet en France/UE, "
      "cohérent avec le contexte fourni (offre, brand, landing, marketing, modèle éco). "
      "Couvrir produit, marketing, ventes, juridique, finance, ops, data, support.\n\n"
      "Schéma STRICT:\n"
      "{\n"
      '  "weeks":[{\n'
      '    "week":1,\n'
      '    "theme":"Focus de la semaine",\n'
      '    "goals":["Résultat(s) mesurable(s) en fin de semaine"],\n'
      '    "kpis":["KPI 1","KPI 2"],\n'
      '    "tasks":[{\n'
      '      "id":"T1",\n'
      '      "title":"Action claire (≤80 caractères)",\n'
      '      "desc":"Détails concrets (quoi, comment) (≤200 caractères)",\n'
      '      "owner":"fondateur|marketing|ventes|tech|ops|juridique|finance|data|produit|support",\n'
      '      "estimate_h":2.5,\n'
      '      "due_offset_days":2,\n'
      '      "tags":["mise_en_place","croissance","réunion","conformité"],\n'
      '      "deps":["T0"]\n'
      '    }]\n'
      '  }]\n'
      "}\n\n"
      "Règles:\n"
      "- EXACTEMENT 4 semaines ; 5 à 6 tâches par semaine (max 6).\n"
      "- Pas d’anglais ; pas de retours à la ligne dans les chaînes.\n"
      "- Chaque tâche: actionnable, owner en français, estimate_h et due_offset_days renseignés.\n"
      "- Inclure kick-off, points hebdo, jalons démo/validation si pertinents.\n\n"
      f"[CONTEXTE]\n{json.dumps(context, ensure_ascii=False)}"
    )

def _next_monday(d: datetime.date | None = None) -> datetime.date:
    d = d or datetime.date.today()
    return d + datetime.timedelta(days=(7 - d.weekday()) % 7 or 7)

def _schedule_from_weeks(
    weeks: list[WeekPlan],
    start_date: datetime.date | None = None,
    mode: str = "week_blocks",  # "week_blocks" = chaque tâche occupe toute la semaine
) -> list[CalendarEvent]:
    """
    Génère la liste d'événements calendrier.
    - mode="week_blocks": chaque tâche devient un événement "journée entière" couvrant la semaine (lundi→lundi).
    - start_date par défaut: prochain lundi (S1 = semaine suivant la génération).
    """
    start = start_date or _next_monday()  # prochain lundi
    events: list[CalendarEvent] = []

    if mode == "week_blocks":
        for w in weeks:
            # Semaine S{w.week} -> plage lundi 00:00 (date-only) → lundi suivant 00:00 (exclusif)
            week_start = start + datetime.timedelta(days=(w.week - 1) * 7)
            week_end   = week_start + datetime.timedelta(days=7)

            # ICS "all-day" = on stocke des dates SANS heure (YYYY-MM-DD)
            s_date = week_start.isoformat()            # "2025-08-18"
            e_date = week_end.isoformat()              # "2025-08-25" (exclusif)

            for t in w.tasks:
                title = f"[S{w.week}] {t.title}"
                desc  = t.desc or ""
                tags  = (t.tags or [])
                events.append(CalendarEvent(
                    title=title,
                    description=desc,
                    start_iso=s_date,   # date-only => all-day
                    end_iso=e_date,     # date-only => all-day multi-jour
                    tags=tags + ["allday", f"S{w.week}"]
                ))
        return events

    # (fallback ancien mode : créneaux 2h, offsets intra-semaine)
    # slots par défaut: matin 09:00-11:00, aprem 14:00-16:00
    def slot_for_offset(offset: int, duration_hours: float | None):
        day = start + datetime.timedelta(days=offset)
        h = 9 if offset % 2 == 0 else 14
        dur_h = duration_hours or 2.0
        dt_start = datetime.datetime.combine(day, datetime.time(hour=h, minute=0))
        dt_end   = dt_start + datetime.timedelta(hours=dur_h)
        return dt_start, dt_end

    # weekly review chaque vendredi 16:00-17:00
    def weekly_review_date(week_idx: int):
        monday = start + datetime.timedelta(days=(week_idx-1)*7)
        friday = monday + datetime.timedelta(days=4)
        dt_start = datetime.datetime.combine(friday, datetime.time(16,0))
        dt_end   = dt_start + datetime.timedelta(hours=1)
        return dt_start, dt_end

    for w in weeks:
        s,e = weekly_review_date(w.week)
        events.append(CalendarEvent(
            title=f"Revue hebdomadaire — S{w.week}: {w.theme}",
            description="Revue des objectifs & KPI de la semaine",
            start_iso=s.isoformat(),
            end_iso=e.isoformat(),
            tags=["review","management"]
        ))
        for t in w.tasks:
            try:
                offset = int(t.due_offset_days or (w.week-1)*7 + 2)
                est = float(t.estimate_h) if t.estimate_h else 2.0
            except Exception:
                offset, est = (w.week-1)*7 + 2, 2.0
            s,e = slot_for_offset(offset, est)
            events.append(CalendarEvent(
                title=f"[S{w.week}] {t.title}",
                description=(t.desc or ""),
                start_iso=s.isoformat(),
                end_iso=e.isoformat(),
                tags=t.tags or []
            ))
    return events

# --- ICS utils (RFC5545) -----------------------------------------------------

def _ics_escape(s: str) -> str:
    if not s:
        return ""
    # ordre: backslash -> ; -> , -> newlines
    s = s.replace("\\", "\\\\").replace(";", r"\;").replace(",", r"\,")
    s = s.replace("\r\n", r"\n").replace("\n", r"\n").replace("\r", r"\n")
    return s

def _to_utc_basic(dt_iso: str | None) -> str:
    """
    Convertit une chaîne ISO quelconque -> format 'YYYYMMDDTHHMMSSZ'
    Si None/vide: now+1h.
    """
    if not dt_iso:
        dt = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=1)
        return dt.strftime("%Y%m%dT%H%M%SZ")
    try:
        dt = datetime.datetime.fromisoformat(dt_iso.replace("Z", "+00:00"))
    except Exception:
        # date seule (YYYY-MM-DD)
        try:
            dt = datetime.datetime.strptime(dt_iso, "%Y-%m-%d")
        except Exception:
            dt = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=1)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.timezone.utc)
    else:
        dt = dt.astimezone(datetime.timezone.utc)
    return dt.strftime("%Y%m%dT%H%M%SZ")

def _ics_from_events(project_title: str, events: List[CalendarEvent] | List[dict]) -> str:
    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    def _get(ev, key: str):
        if hasattr(ev, key):
            return getattr(ev, key)
        if isinstance(ev, dict):
            return ev.get(key)
        return None

    def _is_date_only(s: str | None) -> bool:
        return bool(s) and "T" not in s  # ex: "2025-08-18"

    def _to_basic_date(s: str) -> str:
        # "YYYY-MM-DD" -> "YYYYMMDD"
        return s.replace("-", "")

    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//CreeTonBiz//ActionPlan//FR",
        f"X-WR-CALNAME:{_ics_escape(project_title)}",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
    ]

    for ev in (events or []):
        title = _get(ev, "title") or project_title
        desc  = _get(ev, "description") or ""
        s_iso = _get(ev, "start_iso")
        e_iso = _get(ev, "end_iso")

        if not s_iso or not e_iso:
            continue

        # Date-only => all-day (VALUE=DATE). Sinon => datetime UTC.
        if _is_date_only(s_iso) and _is_date_only(e_iso):
            dtstart = f"DTSTART;VALUE=DATE:{_to_basic_date(s_iso)}"
            dtend   = f"DTEND;VALUE=DATE:{_to_basic_date(e_iso)}"
        else:
            dtstart = f"DTSTART:{_to_utc_basic(s_iso)}"
            dtend   = f"DTEND:{_to_utc_basic(e_iso)}"

        lines += [
            "BEGIN:VEVENT",
            f"UID:{uuid.uuid4().hex}@creetonbiz",
            f"DTSTAMP:{now}",
            dtstart,
            dtend,
            f"SUMMARY:{_ics_escape(title)}",
            f"DESCRIPTION:{_ics_escape(desc)}",
            "BEGIN:VALARM",
            "TRIGGER:-PT30M",
            "ACTION:DISPLAY",
            "DESCRIPTION:Rappel",
            "END:VALARM",
            "END:VEVENT",
        ]

    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"

def _normalize_owner_fr(owner: str | None) -> str | None:
    if not owner:
        return owner
    m = {
        "founder": "fondateur",
        "founders": "fondateur",
        "sales": "ventes",
        "marketing": "marketing",
        "tech": "tech",
        "engineering": "tech",
        "legal": "juridique",
        "finance": "finance",
        "ops": "ops",
        "operations": "ops",
        "data": "data",
        "product": "produit",
        "support": "support",
        "customer success": "support",
        "cs": "support",
    }
    key = owner.strip().lower()
    return m.get(key, owner)

def _text_has_english(s: str | None) -> bool:
    if not s: return False
    s = s.lower()
    # marqueurs simples suffisants pour détecter l’anglais courant
    markers = ("project", "define", "create", "develop", "launch", "ensure",
               "review", "meeting", "research", "plan", "strategy", "setup",
               "kickoff", "prototype", "deliverable")
    return any(m in s for m in markers)

def _weeks_need_translation(weeks: list) -> bool:
    for w in weeks:
        if _text_has_english(getattr(w, "theme", None)):
            return True
        for s in (getattr(w, "goals", []) or []):
            if _text_has_english(s): return True
        for s in (getattr(w, "kpis", []) or []):
            if _text_has_english(s): return True
        for t in (getattr(w, "tasks", []) or []):
            title = getattr(t, "title", None) if not isinstance(t, dict) else t.get("title")
            desc  = getattr(t, "desc", None)  if not isinstance(t, dict) else t.get("desc")
            if _text_has_english(title) or _text_has_english(desc):
                return True
    return False

async def _translate_weeks_to_french(weeks: list) -> list:
    # On traduit uniquement les champs textuels, on ne touche pas aux nombres/ids.
    raw = [w.dict() if hasattr(w, "dict") else w for w in weeks]
    prompt = (
        "LANG=fr-FR — Traduire en FRANÇAIS tous les textes de ce plan d’action.\n"
        "NE MODIFIE PAS la structure JSON, ni les identifiants ('id'), ni 'week', ni 'estimate_h', ni 'due_offset_days'.\n"
        "Réponds EXCLUSIVEMENT par un JSON brut avec EXACTEMENT la clé 'weeks'. Pas d’autres clés. Pas de ```.\n\n"
        + json.dumps({"weeks": raw}, ensure_ascii=False)
    )
    resp = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.0,
        max_tokens=4000,
    )
    data = _parse_json_strict(resp.choices[0].message.content)
    weeks_json = data.get("weeks") if isinstance(data, dict) else data
    # Reparse via Pydantic pour sécuriser le schéma
    return [WeekPlan(**w) for w in weeks_json]

async def generate_plan(
    profil: "ProfilRequest",
    idea_snapshot: Optional[Dict[str, Any]] = None,
    project_id: Optional[int] = None,   # 👈 on accepte project_id pour charger le contexte
) -> PlanResponse:
    p = _profil_dump(profil)
    ctx = {
        "profil": {"secteur": p.get("secteur"), "objectif": p.get("objectif")},
        "verbatim": idea_snapshot or {},
    }
    if project_id:
        ctx["deliverables"] = _load_plan_context_from_deliverables(project_id)

    prompt = _prompt_action_plan(ctx)
    resp = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
        max_tokens=3000,
    )
    data = _parse_json_strict(resp.choices[0].message.content)
    if "weeks" not in data or not isinstance(data["weeks"], list) or len(data["weeks"]) == 0:
        raise HTTPException(status_code=500, detail="Plan d’action invalide (clé 'weeks').")

    # Pydantic parse → structure propre
    weeks = [WeekPlan(**w) for w in data["weeks"]]

    # 🔁 Retraduction FR si nécessaire
    if _weeks_need_translation(weeks):
        try:
            weeks = await _translate_weeks_to_french(weeks)
        except Exception:
            # en cas d'échec, on continue avec la version d’origine (mais on normalise les owners)
            pass

    # 🔤 Normalise les owners en français
    for w in weeks:
        for t in w.tasks:
            t.owner = _normalize_owner_fr(t.owner)

    events = _schedule_from_weeks(weeks, mode="week_blocks")

    # compat: on génère 4 lignes "Semaine i: …"
    legacy = []
    for w in weeks:
        tasks = "; ".join([f"{t.title} ({t.owner or '—'})" for t in w.tasks])
        legacy.append(f"Semaine {w.week}: {w.theme} — {tasks}")

    return PlanResponse(plan=legacy, weeks=weeks, schedule=events)