# backend/services/market_calibrator.py
from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, Any, Optional
import math

# ⚠️ Données FR de base (ordres de grandeur plausibles) → à raffiner/étendre.
# On part d’une base nationale et on ajuste ensuite selon le modèle.
_SECTOR_BASE_FR: Dict[str, dict] = {
    "saas_b2b": {
        "label": "SaaS B2B",
        "arpu_month": 60.0,           # panier mensuel moyen
        "gross_margin": 0.85,         # marge brute
        "cac": 500.0,                 # coût d’acquisition par client
        "lead_to_trial": 0.12,
        "trial_to_paid": 0.22,
        "churn_m": 0.02,
        "opex_fixed_m": 16000.0,      # loyers, salaires, outils (plancher)
        "marketing_ratio": 0.18,      # % CA réinvesti en MKT
        "seasonality": [1]*12,
        "growth_yoy": [2.2, 1.6, 1.4],
    },
    "ecommerce_d2c": {
        "label": "E-commerce D2C",
        "aov": 52.0,
        "conv_rate": 0.017,
        "return_rate": 0.08,
        "gross_margin": 0.50,
        "cac": 18.0,
        "opex_fixed_m": 14000.0,
        "marketing_ratio": 0.12,
        "seasonality": [0.9,0.95,0.95,1.0,1.0,1.05,1.0,0.95,1.05,1.15,1.25,1.4],
        "growth_yoy": [1.8, 1.5, 1.3],
    },
    "services_agency": {
        "label": "Services / Agence B2B",
        "day_rate": 650.0,
        "utilization": 0.68,
        "heads_start": 2,
        "heads_hire_each_q": 1,
        "gross_margin": 0.55,
        "opex_fixed_m": 22000.0,
        "marketing_ratio": 0.06,
        "seasonality": [1.0,0.95,1.02,1.05,1.07,1.02,0.95,0.92,1.02,1.08,1.05,0.98],
        "growth_yoy": [1.6, 1.4, 1.3],
    },
    "qsr_restaurant": {
        "label": "Restauration rapide",
        "avg_ticket": 12.0,
        "covers_per_day": 150,
        "days_open_m": 28,
        "gross_margin": 0.64,
        "opex_fixed_m": 30000.0,
        "marketing_ratio": 0.04,
        "seasonality": [0.95,0.92,0.98,1.02,1.05,1.10,1.15,1.10,1.02,0.98,1.05,1.08],
        "growth_yoy": [1.2, 1.1, 1.08],
    },
}

def _resolve_sector_key(text: Optional[str]) -> str:
    s = (text or "").lower()
    if "saas" in s or "logiciel" in s or "b2b" in s: return "saas_b2b"
    if "ecom" in s or "boutique" in s or "d2c" in s or "shop" in s: return "ecommerce_d2c"
    if "agence" in s or "service" in s or "conseil" in s: return "services_agency"
    if "restau" in s or "qsr" in s or "food" in s: return "qsr_restaurant"
    return "saas_b2b"

@dataclass
class MarketSnapshot:
    sector_key: str
    country: str = "FR"
    # hypothèses calibrées (valeurs finales)
    params: Dict[str, Any] = None
    # sources & notes pour audit (tu peux y pousser des URLs si tu ajoutes des fetchs)
    sources: Dict[str, Any] = None
    rationale: Dict[str, Any] = None

def _clip(x: float, lo: float, hi: float) -> float:
    return float(max(lo, min(hi, x)))

def _blend(user: Dict[str, Any], base: Dict[str, Any]) -> Dict[str, Any]:
    """Priorise l’input projet si présent, sinon fallback marché FR; applique des bornes réalistes."""
    out = {**base}
    for k, v in (user or {}).items():
        if v is None: continue
        out[k] = v

    # bornes sectorielles génériques
    if "gross_margin" in out: out["gross_margin"] = _clip(out["gross_margin"], 0.35, 0.95)
    if "marketing_ratio" in out: out["marketing_ratio"] = _clip(out["marketing_ratio"], 0.02, 0.35)
    if "churn_m" in out: out["churn_m"] = _clip(out["churn_m"], 0.0, 0.15)
    if "conv_rate" in out: out["conv_rate"] = _clip(out["conv_rate"], 0.004, 0.06)
    if "return_rate" in out: out["return_rate"] = _clip(out["return_rate"], 0.0, 0.35)
    if "cac" in out: out["cac"] = _clip(out["cac"], 5.0, 5000.0)
    if "arpu_month" in out: out["arpu_month"] = _clip(out["arpu_month"], 5.0, 800.0)
    if "aov" in out: out["aov"] = _clip(out["aov"], 5.0, 500.0)
    if "opex_fixed_m" in out: out["opex_fixed_m"] = _clip(out["opex_fixed_m"], 5000.0, 200000.0)

    # croissance → transforme YoY en facteur mensuel (facilite ton forecast)
    yoy = out.get("growth_yoy") or [1.5, 1.3, 1.2]
    out["growth_m"] = [(g ** (1/12.0)) for g in yoy]
    return out

def calibrate_market(
    sector_text: Optional[str],
    country: str = "FR",
    # “intentions” / infos projet pour surcharger: prix, GM, CAC, etc.
    user_overrides: Optional[Dict[str, Any]] = None,
    # plus tard: geo="Paris", naf="62.01Z", taille, etc.
) -> MarketSnapshot:
    key = _resolve_sector_key(sector_text)
    base = _SECTOR_BASE_FR[key]
    params = _blend(user_overrides or {}, base)
    sources = {
        "country_base": "FR — tableaux internes (à remplacer/étendre par INSEE/Eurostat quand dispo)",
    }
    rationale = {
        "sector_detected": base["label"],
        "rules": "Bornes réalistes par métrique + conversion YoY->mensuel; priorité aux inputs projet.",
    }
    return MarketSnapshot(sector_key=key, country=country, params=params, sources=sources, rationale=rationale)