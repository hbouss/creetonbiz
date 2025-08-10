# backend/services/domain_service.py
import os
from typing import List, Dict, Optional
import httpx

# ---------- Public API ----------

def suggest_domains(brand_name: str, tlds: List[str] | None = None) -> List[str]:
    tlds = tlds or [".com", ".io", ".co", ".fr"]
    base = (brand_name or "").strip().lower().replace(" ", "")
    base = "".join(ch for ch in base if ch.isalnum()) or "brand"
    return [f"{base}{t}" for t in tlds]

async def check_domains_availability(domains: List[str]) -> Dict[str, Optional[bool]]:
    """
    Retourne { "foo.com": True|False|None }
    True  = disponible
    False = pris/réservé
    None  = non vérifié (erreur ou pas de credentials)
    """
    domains = [d.strip().lower() for d in domains if d and "." in d]
    if not domains:
        return {}

    # 1) Domainr natif (clé OU client_id/secret)
    out = await _check_domainr_native(domains)
    if out:  # on a une réponse exploitable
        return out

    # 2) Domainr via RapidAPI
    out = await _check_domainr_rapidapi(domains)
    if out:
        return out

    # 3) Fallback RDAP (lent, partiel)
    return await _check_rdap(domains)

# ---------- Implémentations ----------

def _domainr_status_to_bool(status_list: List[str]) -> Optional[bool]:
    """
    Mapping minimal : Domainr renvoie une liste de statuts.
    - 'inactive' => souvent dispo
    - 'active' / 'undelegated' / 'reserved' / 'marketed' / 'premium' => pris/non-dispo
    """
    s = {str(x).lower() for x in (status_list or [])}
    if "inactive" in s or "available" in s:
        return True
    if s.intersection({"active", "undelegated", "reserved", "marketed", "premium", "zone", "dns"}):
        return False
    return None

async def _check_domainr_native(domains: List[str]) -> Dict[str, Optional[bool]]:
    key = os.getenv("DOMAINR_API_KEY")
    cid = os.getenv("DOMAINR_CLIENT_ID")
    csecret = os.getenv("DOMAINR_CLIENT_SECRET")

    params: List[tuple[str, str]] = []
    if key:
        params.append(("key", key))
    elif cid and csecret:
        params.append(("client_id", cid))
        params.append(("client_secret", csecret))
    else:
        return {}

    # Domainr autorise domain=... répété plusieurs fois
    for d in domains:
        params.append(("domain", d))

    url = "https://api.domainr.com/v2/status"
    try:
        async with httpx.AsyncClient(timeout=12) as http:
            r = await http.get(url, params=params)
        if r.status_code != 200:
            return {}
        data = r.json()
        out: Dict[str, Optional[bool]] = {d: None for d in domains}
        for item in data.get("status", []):
            dom = item.get("domain")
            st  = item.get("status") or []
            if dom:
                out[dom.lower()] = _domainr_status_to_bool(st)
        return out
    except Exception:
        return {}

async def _check_domainr_rapidapi(domains: List[str]) -> Dict[str, Optional[bool]]:
    """
    Pour clé RapidAPI : DOMAINR_RAPIDAPI_KEY
    Endpoint: https://domainr.p.rapidapi.com/v2/status
    Headers:  X-RapidAPI-Key / X-RapidAPI-Host
    """
    rkey = os.getenv("DOMAINR_RAPIDAPI_KEY")
    if not rkey:
        return {}

    headers = {
        "X-RapidAPI-Key": rkey,
        "X-RapidAPI-Host": "domainr.p.rapidapi.com",
    }

    # RapidAPI ne supporte pas le multi-domain dans une seule requête de manière fiable → on boucle
    out: Dict[str, Optional[bool]] = {d: None for d in domains}
    try:
        async with httpx.AsyncClient(timeout=12) as http:
            for d in domains:
                resp = await http.get("https://domainr.p.rapidapi.com/v2/status",
                                      headers=headers, params={"domain": d})
                if resp.status_code != 200:
                    continue
                data = resp.json()
                if not data.get("status"):
                    continue
                st = data["status"][0].get("status") or []
                out[d] = _domainr_status_to_bool(st)
        return out
    except Exception:
        return {}

async def _check_rdap(domains: List[str]) -> Dict[str, Optional[bool]]:
    """
    Fallback très basique via rdap.org :
    - 200 => le domaine existe => False
    - 404 => non trouvé => True
    - autre => None
    """
    out: Dict[str, Optional[bool]] = {d: None for d in domains}
    try:
        async with httpx.AsyncClient(timeout=10) as http:
            for d in domains:
                url = f"https://rdap.org/domain/{d}"
                r = await http.get(url)
                if r.status_code == 404:
                    out[d] = True
                elif r.status_code == 200:
                    out[d] = False
                else:
                    out[d] = None
        return out
    except Exception:
        return out