# backend/services/premium_service.py
import os
import re
import json
from textwrap import dedent

import httpx
from typing import Optional, Dict, Any, List, Tuple
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

def _forecast_36m(params: dict):
    """Construit les 36 mois de revenus, coûts, EBITDA, etc."""
    price       = params["price"]
    units_m1    = params["units_m1"]
    g           = params["mom_growth"]
    gm          = params["gm"]
    var_rate    = params["var_rate"]
    opex        = params["opex"]
    payroll     = params["payroll"]
    mkt_ratio   = params["mkt_ratio"]

    rev   = [0.0] * 37
    cog   = [0.0] * 37
    gross = [0.0] * 37
    mkt   = [0.0] * 37
    fix   = [0.0] * 37
    ebitda= [0.0] * 37

    units = [0.0] * 37
    units[1] = units_m1
    for m in range(2, 37):
        units[m] = units[m-1] * (1 + g)

    for m in range(1, 37):
        rev[m]    = units[m] * price
        cog[m]    = rev[m] * var_rate
        gross[m]  = rev[m] - cog[m]
        mkt[m]    = rev[m] * mkt_ratio
        fix[m]    = opex + payroll
        ebitda[m] = gross[m] - mkt[m] - fix[m]

    return {
        "units": units, "revenue": rev, "cogs": cog, "gross": gross,
        "marketing": mkt, "fixed": fix, "ebitda": ebitda
    }

def _aggregate_years(series: list[float]) -> list[float]:
    """Somme par année 1..3 depuis une série mensuelle 1..36"""
    y1 = sum(series[1:13])
    y2 = sum(series[13:25])
    y3 = sum(series[25:37])
    return [y1, y2, y3]

def _pnl_3y(params: dict, dep_m: list[float], loan_int_m: list[float], tax_rate: float):
    f = _forecast_36m(params)
    rev_y   = _aggregate_years(f["revenue"])
    cogs_y  = _aggregate_years(f["cogs"])
    gross_y = _aggregate_years(f["gross"])
    mkt_y   = _aggregate_years(f["marketing"])
    fix_y   = _aggregate_years(f["fixed"])
    ebitda_y= _aggregate_years(f["ebitda"])
    dep_y   = _aggregate_years(dep_m)
    int_y   = _aggregate_years(loan_int_m)

    ebit_y  = [ebitda_y[i] - dep_y[i] for i in range(3)]
    ebt_y   = [ebit_y[i] - int_y[i] for i in range(3)]
    tax_y   = [max(0.0, ebt_y[i]) * tax_rate for i in range(3)]
    net_y   = [ebt_y[i] - tax_y[i] for i in range(3)]

    return {
        "revenue": rev_y, "cogs": cogs_y, "gross": gross_y,
        "marketing": mkt_y, "fixed": fix_y, "ebitda": ebitda_y,
        "depreciation": dep_y, "interest": int_y,
        "ebit": ebit_y, "ebt": ebt_y, "tax": tax_y, "net": net_y
    }

def _cash_12m(params: dict, dep_m: list[float], loan_sched: list[dict], loan_int_m: list[float], loan_prin_m: list[float], equity: float, invest_total: float):
    """Trésorerie sur 12 mois (approche directe simple, encaissements = CA, délais ignorés)."""
    f = _forecast_36m(params)
    cash = []
    start = equity + (loan_sched[0]["principal"] + loan_sched[0]["interest"] if loan_sched else 0.0) - invest_total
    # on ne décaisse pas la dotation (non cash)
    bal = start
    for m in range(1, 13):
        inflow  = f["revenue"][m]
        outflow = f["cogs"][m] + f["marketing"][m] + f["fixed"][m] + loan_int_m[m] + loan_prin_m[m]
        bal += inflow - outflow
        cash.append({"month": m, "in": round(inflow, 2), "out": round(outflow, 2), "end": round(bal, 2)})
    return start, cash

def _break_even(params: dict):
    """Point mort basé sur marge contributive = GM% - mkt_ratio."""
    mc_ratio = params["gm"] - params["mkt_ratio"]
    fixed_year = (params["opex"] + params["payroll"]) * 12
    if mc_ratio <= 0:
        return {"revenue": None, "comment": "Marge contributive négative (revoyez la structure de coûts)."}
    rev_needed = fixed_year / mc_ratio
    months = 12 * (1 + 0.0)  # approx
    return {"revenue": round(rev_needed, 2), "month_hint": "entre M10 et M18 selon la traction"}

async def generate_business_plan_structured(profil: ProfilRequest, idea_snapshot: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Construit un Business Plan structuré et chiffré sur 3 ans."""
    p = _profil_dump(profil)
    params = _bp_defaults(p.get("secteur"), p.get("objectif"))

    # Investissements & amortissements
    inv_items, dep_m, invest_total = _build_invest_depreciation(params["investments"], 36)

    # BFR simplifié = 1 mois de charges d'exploitation (hors amort & intérêts)
    fore = _forecast_36m(params)
    bfr = (fore["cogs"][1] + fore["marketing"][1] + fore["fixed"][1])

    # Financement initial : 30% fonds propres par défaut
    uses_total = invest_total + bfr
    equity = max(0.3 * uses_total, 1.0)
    loan_needed = max(0.0, uses_total - equity)

    loan_sched, loan_int_m, loan_prin_m = _build_loan_schedule(
        principal=loan_needed, rate_year=params["loan_rate"], years=params["loan_years"], start_month=1, horizon_months=36
    )

    # P&L 3 ans
    pnl = _pnl_3y(params, dep_m, loan_int_m, params["tax_rate"])

    # Trésorerie 12 mois
    start_cash, cash12 = _cash_12m(params, dep_m, loan_sched, loan_int_m, loan_prin_m, equity, invest_total)

    # Seuil de rentabilité
    breakeven = _break_even(params)

    # Narratif (adapté au VERBATIM si présent)
    idea = (idea_snapshot or {}).get("idee")
    persona = (idea_snapshot or {}).get("persona")
    exec_summary = (
        f"Projet dans le secteur « {p.get('secteur') or '—'} ». "
        f"Modèle économique avec prix moyen {params['price']} € et croissance mensuelle visée {int(params['mom_growth']*100)}%. "
        f"Marge brute cible {int(params['gm']*100)}%, dépenses marketing {int(params['mkt_ratio']*100)}% du CA. "
        f"Investissements initiaux de {int(invest_total)} € et BFR estimé à {int(bfr)} €. "
        f"Financement prévu : {int(0.3*uses_total)} € en fonds propres et {int(loan_needed)} € de dette. "
        f"Objectif : atteindre le point mort aux alentours de {breakeven.get('month_hint')}."
    )

    return {
        "meta": {
            "sector_category": params["category"],
            "sector": p.get("secteur"),
            "objective": p.get("objectif"),
            "persona": persona or p.get("persona"),
        },
        "narrative": {
            "executive_summary": exec_summary,
            "team": p.get("fondateur") or "Compléter les CV & rôles clés.",
            "project": idea or "Compléter la description précise du projet.",
            "market": "Résumer l'étude de marché (clients, concurrence, risques) — à compléter avec données locales.",
            "go_to_market": "Segmentation, positionnement, mix marketing (produit, prix, distribution, communication).",
            "operations": "Organisation, moyens matériels/immatériels, processus clefs et partenaires.",
        },
        "assumptions": params,
        "investments": {
            "items": inv_items, "total": invest_total, "depreciation_month": [round(x, 2) for x in dep_m]
        },
        "financing": {
            "initial_uses": {"investments": invest_total, "working_capital": round(bfr, 2), "total": round(uses_total, 2)},
            "initial_sources": {"equity": round(equity, 2), "loan": round(loan_needed, 2), "total": round(equity + loan_needed, 2)},
            "loan": {"rate": params["loan_rate"], "years": params["loan_years"], "schedule": loan_sched},
            "three_year_view": {
                "loan_outstanding_end_y1": loan_sched[12-1]["balance"] if loan_sched and len(loan_sched)>=12 else loan_needed,
                "loan_outstanding_end_y2": loan_sched[24-1]["balance"] if loan_sched and len(loan_sched)>=24 else max(0.0, loan_needed),
                "loan_outstanding_end_y3": loan_sched[36-1]["balance"] if loan_sched and len(loan_sched)>=36 else 0.0,
            }
        },
        "pnl_3y": pnl,
        "cash_12m": {"start": round(start_cash, 2), "months": cash12},
        "breakeven": breakeven,
        "series_36m": {
            "revenue": [round(x, 2) for x in fore["revenue"]],
            "ebitda": [round(x, 2) for x in fore["ebitda"]],
        }
    }

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