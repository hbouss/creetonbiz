# backend/services/premium_service.py
import os
import re
import json
import httpx
from typing import Optional, Dict, Any
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

# ─────────────────────────────────────────────────────────────────────────────
# OFFRE
# ─────────────────────────────────────────────────────────────────────────────

async def generate_offer(profil: ProfilRequest, idea_snapshot: Optional[Dict[str, Any]] = None) -> OfferResponse:
    """
    Retour JSON STRICT avec exactement:
      - offer (string détaillée mais concise)
      - persona (string) → doit être identique au VERBATIM si fourni
      - pain_points (liste de strings courtes)
    """
    p = _profil_dump(profil)
    prompt = (
        "Tu es un consultant senior. Réponds EXCLUSIVEMENT par un JSON brut (aucune balise Markdown, aucun commentaire) "
        "avec EXACTEMENT les clés suivantes: "
        '["offer","persona","pain_points"].\n'
        "CONTRAINTES:\n"
        "- Si un bloc VERBATIM est fourni, la clé 'persona' doit être STRICTEMENT égale au champ persona du VERBATIM.\n"
        "- 'offer' doit s'appuyer sur 'idee' du VERBATIM sans la déformer.\n"
        "- 'pain_points' est une liste de 5 à 7 éléments, chacun une phrase très courte.\n"
        "- N'ajoute AUCUNE autre clé.\n"
        + _verbatim_block(idea_snapshot) +
        f"\n[PROFIL] secteur={p.get('secteur')} • objectif={p.get('objectif')} • compétences={_competences_str(profil)}"
    )

    resp = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.5,
        max_tokens=500,
    )
    data = _parse_json_strict(resp.choices[0].message.content)

    # Normalisation pain_points
    pp = data.get("pain_points")
    if isinstance(pp, str):
        lines = [line.strip("- •").strip() for line in pp.splitlines() if line.strip()]
        data["pain_points"] = lines
    elif isinstance(pp, list):
        data["pain_points"] = [str(item).strip() for item in pp if str(item).strip()]
    else:
        data["pain_points"] = []

    # Persona: force le VERBATIM si fourni
    if idea_snapshot and idea_snapshot.get("persona"):
        data["persona"] = idea_snapshot["persona"]

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

async def generate_brand(profil: ProfilRequest, idea_snapshot: Optional[Dict[str, Any]] = None) -> BrandResponse:
    """
    Si VERBATIM (nom/slogan) est présent → on le reprend tel quel (pas d'appel IA).
    Sinon, on génère (toujours JSON strict).
    Puis on vérifie (facultatif) la dispo de domaine via Namecheap.
    """
    brand_name = (idea_snapshot or {}).get("nom")
    slogan = (idea_snapshot or {}).get("slogan")

    if not brand_name or not slogan:
        p = _profil_dump(profil)
        prompt = (
            "Réponds EXCLUSIVEMENT par un JSON brut avec EXACTEMENT les clés 'brand_name' et 'slogan'.\n"
            "Aucune autre clé, aucun Markdown.\n"
            + _verbatim_block(idea_snapshot) +
            f"\n[PROFIL] secteur={p.get('secteur')} • objectif={p.get('objectif')}"
        )
        resp = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.5,
            max_tokens=120,
        )
        data = _parse_json_strict(resp.choices[0].message.content)
        missing = [k for k in ("brand_name", "slogan") if k not in data]
        if missing:
            raise HTTPException(status_code=500, detail=f"Clés manquantes: {missing}")
        brand_name, slogan = data["brand_name"], data["slogan"]

    # Forcer VERBATIM si dispo
    if idea_snapshot:
        if idea_snapshot.get("nom"):
            brand_name = idea_snapshot["nom"]
        if idea_snapshot.get("slogan"):
            slogan = idea_snapshot["slogan"]

    domain = (brand_name or "").replace(" ", "") + ".com"

    # Vérification Namecheap (optionnelle)
    api_user = os.getenv("NAMECHEAP_USER")
    api_key = os.getenv("NAMECHEAP_KEY")
    client_ip = os.getenv("CLIENT_IP")
    if not (api_user and api_key and client_ip):
        return BrandResponse(brand_name=brand_name, slogan=slogan, domain=domain, domain_available=None)

    url = (
        "https://api.namecheap.com/xml.response"
        f"?ApiUser={api_user}&ApiKey={api_key}&UserName={api_user}"
        f"&ClientIp={client_ip}&Command=namecheap.domains.check&DomainList={domain}"
    )
    async with httpx.AsyncClient() as http:
        r = await http.get(url)
    tree = ET.fromstring(r.text)
    available = tree.find(".//DomainCheckResult").get("Available") == "true"
    return BrandResponse(brand_name=brand_name, slogan=slogan, domain=domain, domain_available=available)

# ─────────────────────────────────────────────────────────────────────────────
# LANDING
# ─────────────────────────────────────────────────────────────────────────────

async def generate_landing(profil: ProfilRequest, idea_snapshot: Optional[Dict[str, Any]] = None) -> LandingResponse:
    """
    Retour JSON STRICT avec exactement:
      - html : landing responsive
    Contraintes: si VERBATIM, le header/hero DOIT afficher nom et slogan EXACTS.
    """
    p = _profil_dump(profil)
    prompt = (
        "Réponds EXCLUSIVEMENT par un JSON brut avec EXACTEMENT la clé 'html'.\n"
        "La landing doit être responsive (HTML/CSS inline minimal), propre, sans frameworks.\n"
        "CONTRAINTES:\n"
        "- Si VERBATIM est fourni, afficher en HERO: nom et slogan EXACTS (copier-coller), sans reformulation.\n"
        "- Le texte de présentation doit rester aligné avec 'idee' (ne pas la déformer).\n"
        "- Aucune autre clé que 'html'.\n"
        + _verbatim_block(idea_snapshot) +
        f"\n[PROFIL] secteur={p.get('secteur')} • objectif={p.get('objectif')} • compétences={_competences_str(profil)}"
    )
    resp = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.5,
        max_tokens=1500,
    )
    data = _parse_json_strict(resp.choices[0].message.content)
    if "html" not in data:
        raise HTTPException(status_code=500, detail="Clé 'html' manquante dans la réponse JSON")
    return LandingResponse(html=data["html"])

# ─────────────────────────────────────────────────────────────────────────────
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
# PLAN D'ACTION
# ─────────────────────────────────────────────────────────────────────────────

async def generate_plan(profil: ProfilRequest, idea_snapshot: Optional[Dict[str, Any]] = None) -> PlanResponse:
    """
    Retour JSON STRICT avec exactement:
      - plan (liste de chaînes; 4 blocs 'Semaine 1..4: ...')
    Contraintes: alignement avec idee VERBATIM, pas d'autres clés.
    """
    p = _profil_dump(profil)
    prompt = (
        "Réponds EXCLUSIVEMENT par un JSON brut avec EXACTEMENT la clé 'plan'.\n"
        "Le 'plan' doit être une LISTE de 4 éléments ('Semaine 1: ...' à 'Semaine 4: ...').\n"
        "CONTRAINTES:\n"
        "- Aligné strictement avec 'idee' du VERBATIM, sans la déformer.\n"
        "- Aucune autre clé.\n"
        + _verbatim_block(idea_snapshot) +
        f"\n[PROFIL] secteur={p.get('secteur')} • objectif={p.get('objectif')}"
    )
    resp = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.5,
        max_tokens=500,
    )
    data = _parse_json_strict(resp.choices[0].message.content)
    if "plan" not in data:
        raise HTTPException(status_code=500, detail="Clé 'plan' manquante dans la réponse JSON")
    plan_list = data.get("plan")
    if not isinstance(plan_list, list):
        plan_list = [str(plan_list)]
    # Normalise en strings
    normalized = []
    for i, elem in enumerate(plan_list, start=1):
        if isinstance(elem, dict):
            tasks = elem.get("tâches") or elem.get("taches") or elem.get("tasks") or elem
            if isinstance(tasks, list):
                tasks_str = ", ".join(str(t) for t in tasks)
            else:
                tasks_str = str(tasks)
            normalized.append(f"Semaine {i}: {tasks_str}")
        else:
            s = str(elem)
            normalized.append(s if s.lower().startswith("semaine") else f"Semaine {i}: {s}")
    return PlanResponse(plan=normalized)