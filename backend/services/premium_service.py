# backend/services/premium_service.py
import os
import json
import httpx
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

async def generate_offer(profil: ProfilRequest) -> OfferResponse:
    prompt = (
        f"Réponds exclusivement par un JSON brut contenant uniquement les clés 'offer', 'persona', 'pain_points', "
        f"sans commentaires ni balises, pour le secteur {profil.secteur} avec objectif {profil.objectif}."
    )
    resp = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7,
        max_tokens=500,
    )
    content = resp.choices[0].message.content.strip()
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        start = content.find("{")
        end = content.rfind("}")
        if start == -1 or end == -1:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Impossible d'extraire JSON: {content}"
            )
        snippet = content[start:end+1]
        try:
            data = json.loads(snippet)
        except json.JSONDecodeError:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"JSON invalide extrait: {snippet}"
            )
    # Normalisation de pain_points en liste de chaînes
    pp = data.get("pain_points")
    if isinstance(pp, str):
        lines = [line.strip('- ').strip() for line in pp.splitlines() if line.strip()]
        data["pain_points"] = lines
    elif isinstance(pp, list):
        data["pain_points"] = [str(item) for item in pp]
    else:
        data["pain_points"] = [str(pp)]
    missing = [k for k in ("offer", "persona", "pain_points") if k not in data]
    if missing:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Clés manquantes: {missing}"
        )
    return OfferResponse(**data)

async def generate_business_model(profil: ProfilRequest) -> BusinessModelResponse:
    prompt = (
        f"Réponds exclusivement par un JSON brut contenant uniquement la clé 'model', "
        f"sans explications ni balises, pour un business dans le secteur {profil.secteur} avec objectif {profil.objectif}."
    )
    resp = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7,
        max_tokens=100,
    )
    content = resp.choices[0].message.content.strip()
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        start = content.find("{")
        end = content.rfind("}")
        if start == -1 or end == -1:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Impossible d'extraire JSON: {content}"
            )
        snippet = content[start:end+1]
        try:
            data = json.loads(snippet)
        except json.JSONDecodeError:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"JSON invalide extrait: {snippet}"
            )
    if 'model' not in data:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Clé 'model' manquante dans la réponse JSON"
        )
    return BusinessModelResponse(model=data['model'])

async def generate_brand(profil: ProfilRequest) -> BrandResponse:
    prompt = (
        f"Réponds exclusivement par un JSON brut contenant uniquement les clés 'brand_name' et 'slogan', "
        f"sans explications ni balises, pour un business secteur {profil.secteur} avec objectif {profil.objectif}."
    )
    resp = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7,
        max_tokens=200,
    )
    content = resp.choices[0].message.content.strip()
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        start = content.find("{")
        end = content.rfind("}")
        if start == -1 or end == -1:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Impossible d'extraire JSON: {content}"
            )
        snippet = content[start:end+1]
        try:
            data = json.loads(snippet)
        except json.JSONDecodeError:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"JSON invalide extrait: {snippet}"
            )
    missing = [k for k in ("brand_name", "slogan") if k not in data]
    if missing:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Clés manquantes: {missing}"
        )
    domain = data["brand_name"].replace(" ", "") + ".com"
    api_user = os.getenv("NAMECHEAP_USER")
    api_key = os.getenv("NAMECHEAP_KEY")
    client_ip = os.getenv("CLIENT_IP")
    if not (api_user and api_key and client_ip):
        return BrandResponse(
            brand_name=data["brand_name"],
            slogan=data["slogan"],
            domain=domain,
            domain_available=None,
        )
    url = (
        "https://api.namecheap.com/xml.response"
        f"?ApiUser={api_user}&ApiKey={api_key}&UserName={api_user}"
        f"&ClientIp={client_ip}&Command=namecheap.domains.check&DomainList={domain}"
    )
    async with httpx.AsyncClient() as http:
        r = await http.get(url)
    tree = ET.fromstring(r.text)
    available = tree.find('.//DomainCheckResult').get('Available') == 'true'
    return BrandResponse(
        brand_name=data["brand_name"],
        slogan=data["slogan"],
        domain=domain,
        domain_available=available,
    )

async def generate_landing(profil: ProfilRequest) -> LandingResponse:
    prompt = (
        f"Réponds exclusivement par un JSON brut contenant uniquement la clé 'html' correspondant à une landing page HTML responsive, "
        f"pour un business secteur {profil.secteur}, objectif {profil.objectif}, compétences {', '.join(profil.competences)}."
    )
    resp = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7,
        max_tokens=1500,
    )
    content = resp.choices[0].message.content.strip()
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        start = content.find("{")
        end = content.rfind("}")
        if start == -1 or end == -1:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Impossible d'extraire JSON: {content}"
            )
        snippet = content[start:end+1]
        try:
            data = json.loads(snippet)
        except json.JSONDecodeError:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"JSON invalide extrait: {snippet}"
            )
    if 'html' not in data:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Clé 'html' manquante dans la réponse JSON"
        )
    return LandingResponse(html=data['html'])

async def generate_marketing(profil: ProfilRequest) -> MarketingResponse:
    prompt = (
        f"Réponds exclusivement par un JSON brut contenant uniquement les clés 'ads_strategy', 'seo_plan', 'social_plan', "
        f"sans explications ni balises, pour un business secteur {profil.secteur}, objectif {profil.objectif}."
    )
    resp = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7,
        max_tokens=500,
    )
    content = resp.choices[0].message.content.strip()
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        start = content.find("{")
        end = content.rfind("}")
        if start == -1 or end == -1:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Impossible d'extraire JSON: {content}"
            )
        snippet = content[start:end+1]
        try:
            data = json.loads(snippet)
        except json.JSONDecodeError:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"JSON invalide extrait: {snippet}"
            )
    # Coercition en chaînes
    for key in ("ads_strategy", "seo_plan", "social_plan"):
        val = data.get(key)
        if not isinstance(val, str):
            data[key] = json.dumps(val)
    missing = [k for k in ("ads_strategy","seo_plan","social_plan") if k not in data]
    if missing:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Clés manquantes: {missing}"
        )
    return MarketingResponse(**data)

async def generate_plan(profil: ProfilRequest) -> PlanResponse:
    prompt = (
        f"Réponds exclusivement par un JSON brut contenant uniquement la clé 'plan' (liste de tâches), "
        f"sans explications ni balises, pour un plan d'action sur 4 semaines pour un business secteur {profil.secteur}, objectif {profil.objectif}."
    )
    resp = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7,
        max_tokens=500,
    )
    content = resp.choices[0].message.content.strip()
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        start = content.find("{")
        end = content.rfind("}")
        if start == -1 or end == -1:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Impossible d'extraire JSON: {content}"
            )
        snippet = content[start:end+1]
        try:
            data = json.loads(snippet)
        except json.JSONDecodeError:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"JSON invalide extrait: {snippet}"
            )
    plan_list = data.get('plan')
    if isinstance(plan_list, list) and plan_list and isinstance(plan_list[0], dict):
        normalized = []
        for elem in plan_list:
            week = elem.get('semaine') or elem.get('week') or ''
            tasks = elem.get('tâches') or elem.get('taches') or elem.get('tasks') or []
            if isinstance(tasks, list):
                tasks_str = ", ".join(str(t) for t in tasks)
            else:
                tasks_str = str(tasks)
            normalized.append(f"Semaine {week}: {tasks_str}")
        data['plan'] = normalized
    else:
        data['plan'] = [str(item) for item in plan_list] if isinstance(plan_list, list) else [str(plan_list)]
    if 'plan' not in data:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Clé 'plan' manquante dans la réponse JSON"
        )
    return PlanResponse(plan=data['plan'])