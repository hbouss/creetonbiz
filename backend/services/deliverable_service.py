# backend/services/deliverable_service.py
import os
from datetime import datetime
from backend.db import get_session
from backend.models import Deliverable
import html, re
from typing import Any
from pathlib import Path
import shutil
import unicodedata

STORAGE_DIR = os.path.join(os.path.dirname(__file__), "..", "storage")
# --- Publication "1 clic" ---
PUBLIC_WEBROOT = os.path.expanduser("~/public_sites")  # dossier servi par Nginx
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "http://pages.localtest.me:8080")

# Retire les caractères de contrôle interdits par Postgres (\x00 notamment)
# On conserve \n, \r, \t pour ne pas casser les retours à la ligne.
_CONTROL_CHARS_RE = re.compile(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]')

def _sanitize_for_json(obj: Any) -> Any:
    if obj is None:
        return None
    if isinstance(obj, str):
        # normalise les retours à la ligne CRLF -> LF et supprime les contrôles
        s = obj.replace("\r\n", "\n").replace("\r", "\n")
        return _CONTROL_CHARS_RE.sub("", s)
    if isinstance(obj, list):
        return [_sanitize_for_json(x) for x in obj]
    if isinstance(obj, dict):
        # nettoie aussi les clés au cas où
        return { _sanitize_for_json(str(k)): _sanitize_for_json(v) for k, v in obj.items() }
    # nombres, booléens, etc. inchangés
    return obj

def save_deliverable(
    user_id: int,
    kind: str,
    data: dict,
    title: str | None = None,
    file_path: str | None = None,
    project_id: int | None = None,
):
    # ✅ supprime \x00, \x01.. etc. et normalise les retours à la ligne
    clean_data = _sanitize_for_json(data or {})
    clean_title = _sanitize_for_json(title) if isinstance(title, str) else title
    clean_path = _sanitize_for_json(file_path) if isinstance(file_path, str) else file_path

    with get_session() as s:
        d = Deliverable(
            user_id=user_id,
            project_id=project_id,
            kind=kind,
            title=clean_title,
            json_content=clean_data,     # ✅ on enregistre l’objet nettoyé (dict)
            file_path=clean_path,
        )
        s.add(d)
        s.commit()
        s.refresh(d)
        return d.id


def write_landing_file(user_id: int, html_str: str) -> str:
    safe_html = _CONTROL_CHARS_RE.sub("", (html_str or "").replace("\r\n", "\n").replace("\r", "\n"))
    # Ex: backend/storage/landings/<user_id>/landing-<timestamp>.html
    folder = os.path.join(STORAGE_DIR, "landings", str(user_id))
    os.makedirs(folder, exist_ok=True)
    ts = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    path = os.path.join(folder, f"landing-{ts}.html")
    with open(path, "w", encoding="utf-8") as f:
        f.write(safe_html)
    return path

def _slugify(s: str) -> str:
    s = (s or "").strip().lower()
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s or "page"
def inject_logo_data_uri(html_str: str, data_uri: str, brand_name: str | None = None) -> str:
    """
    Injecte un <img src="data:..."> dans le header/hero ou juste après <body>.
    - Si la landing contient un placeholder <div id="brand-logo-slot"></div>, on le remplace.
    - Sinon: on essaie d'insérer dans <header>, puis fallback juste après <body>.
    """
    if not html_str or not data_uri:
        return html_str

    alt = _html.escape(brand_name or "Logo")
    img = f'<img src="{data_uri}" alt="{alt}" style="height:48px;width:auto;display:block"/>'

    # 1) Placeholder explicite
    if '<div id="brand-logo-slot"></div>' in html_str:
        return html_str.replace('<div id="brand-logo-slot"></div>', img, 1)

    # 2) Insertion dans <header>
    m = re.search(r'<header[^>]*>', html_str, flags=re.IGNORECASE)
    if m:
        i = m.end()
        return html_str[:i] + img + html_str[i:]

    # 3) Fallback: juste après <body>
    m = re.search(r'<body[^>]*>', html_str, flags=re.IGNORECASE)
    if m:
        i = m.end()
        block = f'<div class="brand-logo" style="padding:12px 0;display:flex;align-items:center">{img}</div>'
        return html_str[:i] + block + html_str[i:]

    # 4) Ultime fallback: au tout début
    return img + html_str

def publish_landing_to_webroot(
    user_id: int,
    project_id: int,
    project_title: str,
    html_path: str,
) -> str:
    """
    Copie la landing générée (html_path) vers le webroot public Nginx :
      ~/public_sites/u<user_id>/<slug>/index.html

    Retourne l'URL publique.
    """
    if not html_path or not os.path.exists(html_path):
        raise FileNotFoundError(f"Landing HTML introuvable: {html_path}")

    slug = _slugify(project_title) + f"-{project_id}"
    dest_dir = os.path.join(PUBLIC_WEBROOT, f"u{user_id}", slug)
    os.makedirs(dest_dir, exist_ok=True)

    # Option: minifier très léger (on garde simple, pas d’external lib)
    with open(html_path, "r", encoding="utf-8") as f:
        html = f.read()

    # S’assure qu’on a bien un charset (évite 'âœ…')
    if "<meta charset" not in html.lower():
        html = html.replace("<head>", "<head><meta charset=\"utf-8\">", 1)

    dest_index = os.path.join(dest_dir, "index.html")
    with open(dest_index, "w", encoding="utf-8") as f:
        f.write(html)

    return f"{PUBLIC_BASE_URL}/u{user_id}/{slug}/"


# ---------------------- OFFRE : rendu HTML (rapport) -------------------------

def _pct_from_label(label: str, mapping: dict[str, int], default: int = 50) -> int:
    if not isinstance(label, str):
        return default
    key = label.strip().lower()
    return mapping.get(key, default)


def render_offer_report_html(
    offer: dict,
    persona: str,
    pain_points: list[str],
    project_title: str = "Offre",
    idea_text: str | None = None,
) -> str:
    # Sécurise les champs
    mo = offer.get("market_overview", {}) or {}
    dm = offer.get("demand_analysis", {}) or {}
    ca = offer.get("competitor_analysis", {}) or {}
    er = offer.get("environment_regulation", {}) or {}
    synthesis = offer.get("synthesis") or ""

    # Mappings pour barres “graphiques”
    pace_pct = _pct_from_label(
        er.get("tech_evolution_pace", ""),
        {"lent": 33, "modéré": 66, "modere": 66, "rapide": 100},
        50,
    )
    budget_pct = _pct_from_label(
        dm.get("budget", ""),
        {"faible": 30, "moyen": 60, "élevé": 90, "eleve": 90},
        50,
    )
    trend_pct = _pct_from_label(
        dm.get("customer_count_trend", ""),
        {"en baisse": 33, "stable": 50, "en hausse": 85},
        50,
    )
    state_pct = _pct_from_label(
        mo.get("current_state", ""),
        {"régression": 25, "regression": 25, "stagnation": 50, "progression": 80},
        50,
    )

    def li(items):
        if not items:
            return "<li>-</li>"
        return "".join(f"<li>{str(x)}</li>" for x in items)

    def competitor_li(items):
        out = []
        for c in items or []:
            if isinstance(c, dict):
                out.append(
                    f"<li><strong>{c.get('name','(inconnu)')}</strong> — "
                    f"Positionnement : {c.get('positioning','-')}. "
                    f"Forces : {c.get('strengths','-')}. "
                    f"Faiblesses : {c.get('weaknesses','-')}.</li>"
                )
            else:
                out.append(f"<li>{str(c)}</li>")
        return "".join(out) or "<li>-</li>"

    style = """
    <style>
      :root{--bg:#0f172a;--panel:#111827;--card:#1f2937;--muted:#9ca3af;--ink:#e5e7eb;--accent:#10b981;--blue:#2563eb;--yellow:#d97706;}
      *{box-sizing:border-box} body{margin:0;font-family:Inter,system-ui,-apple-system,Segoe UI,Roboto,Arial,Helvetica,sans-serif;background:var(--bg);color:var(--ink);}
      .wrap{max-width:980px;margin:40px auto;padding:0 20px}
      .card{background:var(--card);border-radius:16px;padding:24px;margin-bottom:16px;box-shadow:0 8px 24px rgba(0,0,0,.25)}
      h1{font-size:28px;margin:0 0 6px}
      h2{font-size:20px;margin:0 0 12px;color:var(--ink)}
      h3{font-size:16px;margin:14px 0 8px;color:#f3f4f6}
      p{color:#d1d5db;line-height:1.55;margin:6px 0}
      .muted{color:var(--muted);font-size:12px}
      .tag{display:inline-block;padding:2px 8px;border-radius:999px;background:#374151;color:#e5e7eb;font-size:12px;margin-right:6px}
      .grid{display:grid;grid-template-columns:1fr 1fr;gap:16px}
      .kpis{display:grid;grid-template-columns:repeat(4,1fr);gap:10px}
      .kpi{background:#111827;border-radius:12px;padding:12px}
      ul{margin:8px 0 0 18px}
      .bar{background:#111827;border-radius:999px;height:8px;overflow:hidden}
      .bar > span{display:block;height:100%;background:var(--accent);width:0;transition:width .3s}
      .chip{background:#0b1220;border:1px solid #1f2a44;padding:8px 10px;border-radius:10px;color:#cfd7ff}
      .divider{height:1px;background:#253048;margin:14px 0}
      .header{display:flex;justify-content:space-between;align-items:flex-end;margin-bottom:10px}
      .small{font-size:13px}
      .idea{white-space:pre-wrap}
      .foot{margin-top:12px;font-size:12px;color:#9ca3af}
    </style>
    """

    html_out = f"""<!doctype html>
<html lang="fr">
<meta charset="utf-8"/>
<title>{project_title}</title>
{style}
<body>
  <div class="wrap">
    <div class="card">
      <div class="header">
        <div>
          <h1>{project_title}</h1>
          <p class="muted">Rapport d'opportunité — généré automatiquement</p>
        </div>
        <div>
          <span class="tag">Offre</span>
          <span class="tag">Analyse marché</span>
          <span class="tag">Synthèse exéc.</span>
        </div>
      </div>
      {"<h3>Idée (verbatim)</h3><p class='idea'>"+idea_text+"</p>" if idea_text else ""}
      <div class="divider"></div>
      <div class="kpis">
        <div class="kpi">
          <div class="muted small">État du marché</div>
          <div class="bar"><span style="width:{state_pct}%"></span></div>
        </div>
        <div class="kpi">
          <div class="muted small">Évolution du nombre de clients</div>
          <div class="bar"><span style="width:{trend_pct}%"></span></div>
        </div>
        <div class="kpi">
          <div class="muted small">Budget client moyen</div>
          <div class="bar"><span style="width:{budget_pct}%"></span></div>
        </div>
        <div class="kpi">
          <div class="muted small">Rythme d'innovation</div>
          <div class="bar"><span style="width:{pace_pct}%"></span></div>
        </div>
      </div>
    </div>

    <div class="grid">
      <div class="card">
        <h2>🎯 Persona cible</h2>
        <p>{persona or "-"}</p>
      </div>
      <div class="card">
        <h2>😖 Points de douleur</h2>
        <ul>{li(pain_points)}</ul>
      </div>
    </div>

    <div class="card">
      <h2>📈 Étude du marché</h2>
      <h3>Volume</h3>
      <p>{mo.get("volume","-")}</p>
      <h3>Situation actuelle</h3>
      <p>{mo.get("current_state","-")}</p>
      <h3>Tendances</h3>
      <ul>{li(mo.get("trends"))}</ul>
      <h3>Produits / Services</h3>
      <ul>{li(mo.get("products_services"))}</ul>
      <h3>Principaux acteurs</h3>
      <ul>{li(mo.get("main_players"))}</ul>
    </div>

    <div class="card">
      <h2>🧭 Étude de la demande</h2>
      <h3>Segments</h3>
      <ul>{li(dm.get("segments"))}</ul>
      <h3>Évolution du nombre de clients</h3>
      <p>{dm.get("customer_count_trend","-")}</p>
      <h3>Localisations</h3>
      <ul>{li(dm.get("locations"))}</ul>
      <h3>Comportements</h3>
      <ul>{li(dm.get("behaviors"))}</ul>
      <h3>Critères de choix</h3>
      <ul>{li(dm.get("choice_criteria"))}</ul>
      <h3>Budget</h3>
      <p>{dm.get("budget","-")}</p>
    </div>

    <div class="card">
      <h2>🏁 Analyse de l'offre (concurrence)</h2>
      <h3>Concurrents directs</h3>
      <ul>{competitor_li(ca.get("direct"))}</ul>
      <h3>Concurrents indirects</h3>
      <ul>{li(ca.get("indirect"))}</ul>
      <h3>Points de différenciation</h3>
      <ul>{li(ca.get("differentiation_points"))}</ul>
      <h3>Facteurs de succès</h3>
      <ul>{li(ca.get("success_factors"))}</ul>
      <h3>Échecs & leçons</h3>
      <ul>{li(ca.get("failures_lessons"))}</ul>
    </div>

    <div class="card">
      <h2>🌐 Environnement & réglementation</h2>
      <h3>Innovations</h3>
      <ul>{li(er.get("innovations"))}</ul>
      <h3>Cadre réglementaire</h3>
      <ul>{li(er.get("regulatory_framework"))}</ul>
      <h3>Associations / acteurs</h3>
      <ul>{li(er.get("associations"))}</ul>
      <h3>Barrières à l'entrée</h3>
      <ul>{li(er.get("entry_barriers"))}</ul>
    </div>

    <div class="card">
      <h2>🧩 Synthèse exécutive</h2>
      <p>{synthesis or "-"}</p>
      <p class="foot">Ce rapport est une base d'aide à la décision, à compléter par des données de terrain.</p>
    </div>
  </div>
</body>
</html>"""
    return html_out


# ---------------------- BRAND : helpers & rendu HTML (brand book) ------------

def _initials(name: str) -> str:
    parts = re.findall(r"[A-Za-zÀ-ÖØ-öø-ÿ]+", name or "")
    if not parts:
        return "B"
    if len(parts) == 1:
        return parts[0][:2].upper()
    return (parts[0][0] + parts[1][0]).upper()


def _placeholder_logo_svg(text: str, color_hex: str) -> str:
    # fallback simple
    fill = color_hex if isinstance(color_hex, str) and color_hex.startswith("#") else "#4F46E5"
    return f"""<svg width="120" height="120" viewBox="0 0 120 120" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="Logo">
  <circle cx="60" cy="60" r="56" fill="{fill}" />
  <text x="50%" y="54%" dominant-baseline="middle" text-anchor="middle" font-family="Inter, Arial, sans-serif" font-size="42" fill="#ffffff">{html.escape(text)}</text>
</svg>"""


# --- Helpers "design" pour 3 concepts de logos pros et différents ------------

def _pick_palette_colors(pal: list[dict]) -> tuple[str, str, str]:
    """Retourne (primary, secondary, accent) depuis la palette normalisée."""
    p = pal[0]["hex"] if pal and pal[0].get("hex") else "#4F46E5"   # Indigo
    s = pal[1]["hex"] if len(pal) > 1 and pal[1].get("hex") else "#22D3EE"   # Cyan
    a = pal[2]["hex"] if len(pal) > 2 and pal[2].get("hex") else "#F59E0B"   # Amber
    return p, s, a


def _infer_motif(text: str | None) -> str:
    """Déduit un motif iconographique à partir du contexte."""
    t = (text or "").lower()
    mapping = [
        (("beauté", "beauty", "cosmétique", "cosmetique", "skin", "makeup"), "drop"),
        (("santé", "health", "médical", "medical", "care"), "cross"),
        (("édu", "edu", "apprent", "learn", "school", "formation"), "book"),
        (("écologie", "durable", "green", "environ", "climat", "solar", "solaire"), "leaf"),
        (("finance", "banque", "invest", "fintech", "bourse"), "chart"),
        (("commerce", "retail", "e-commerce", "ecommerce", "shop"), "bag"),
        (("mobilité", "transport", "logistique", "delivery"), "wheel"),
        (("énergie", "energy", "électri", "electric", "power"), "bolt"),
        (("ia", "intelligence artificielle", "data", "saas", "tech", "software"), "hex"),
    ]
    for keys, m in mapping:
        if any(k in t for k in keys):
            return m
    return "spark"  # défaut


def _svg_defs(primary: str, secondary: str, accent: str) -> str:
    return f"""
    <defs>
      <linearGradient id="gradA" x1="0" y1="0" x2="1" y2="1">
        <stop offset="0%" stop-color="{primary}" />
        <stop offset="100%" stop-color="{secondary}" />
      </linearGradient>
      <linearGradient id="gradB" x1="0" y1="1" x2="1" y2="0">
        <stop offset="0%" stop-color="{secondary}" />
        <stop offset="100%" stop-color="{accent}" />
      </linearGradient>
      <filter id="softShadow" x="-20%" y="-20%" width="140%" height="140%">
        <feDropShadow dx="0" dy="2" stdDeviation="3" flood-color="#000" flood-opacity="0.25"/>
      </filter>
    </defs>
    """


def _svg_symbol_for_motif(motif: str, fill: str, stroke: str = "#0f172a") -> str:
    if motif == "leaf":
        return f'<path d="M90,30 C40,20 20,60 30,85 C55,95 95,75 90,30 Z" fill="url(#gradA)" stroke="{stroke}" stroke-width="2"/>'
    if motif == "drop":
        return f'<path d="M70,18 C70,18 45,45 45,65 a25,25 0 1,0 50,0 C95,45 70,18 70,18 Z" fill="url(#gradA)" stroke="{stroke}" stroke-width="2"/>'
    if motif == "cross":
        return f'<path d="M60 20 h20 v25 h25 v20 h-25 v25 h-20 v-25 h-25 v-20 h25z" fill="url(#gradA)" filter="url(#softShadow)"/>'
    if motif == "book":
        return f'<path d="M40,25 h35 q15,0 15,15 v55 q0,15 -15,15 h-35 z M40,25 v70 q15,-10 35,-10 V25" fill="url(#gradA)" stroke="{stroke}" stroke-width="2"/>'
    if motif == "bolt":
        return f'<path d="M70,15 L45,70 h20 l-10,40 40,-60 h-22 l12,-35 z" fill="url(#gradB)" />'
    if motif == "bag":
        return f'<path d="M40,50 h60 v45 a10,10 0 0 1 -10,10 h-40 a10,10 0 0 1 -10,-10 z M55,50 v-5 a15,15 0 0 1 30,0 v5" fill="url(#gradA)" stroke="{stroke}" stroke-width="2"/>'
    if motif == "wheel":
        return f'<circle cx="70" cy="70" r="36" fill="none" stroke="url(#gradA)" stroke-width="12"/><circle cx="70" cy="70" r="6" fill="{stroke}"/><path d="M70 34 V64 M34 70 H64 M70 106 V76 M106 70 H76" stroke="{stroke}" stroke-width="4" stroke-linecap="round"/>'
    if motif == "chart":
        return f'<rect x="40" y="65" width="14" height="35" fill="url(#gradA)"/><rect x="60" y="50" width="14" height="50" fill="url(#gradB)"/><rect x="80" y="40" width="14" height="60" fill="url(#gradA)"/><path d="M38,102 H100" stroke="{stroke}" stroke-width="2"/>'
    if motif == "hex":
        return f'<polygon points="70,26 100,43 100,77 70,94 40,77 40,43" fill="url(#gradA)" stroke="{stroke}" stroke-width="2"/>'
    # spark (défaut)
    return f'<path d="M70,24 l10,26 28,8 -28,8 -10,26 -10,-26 -28,-8 28,-8z" fill="url(#gradB)" />'


def _logo_concept_monogram(initials: str, primary: str, secondary: str) -> str:
    return f"""
<svg width="220" height="220" viewBox="0 0 220 220" xmlns="http://www.w3.org/2000/svg" role="img">
  {_svg_defs(primary, secondary, "#ffffff")}
  <rect x="14" y="14" width="192" height="192" rx="28" fill="url(#gradA)" filter="url(#softShadow)"/>
  <text x="50%" y="53%" text-anchor="middle" font-family="Inter, Arial, sans-serif"
        font-size="96" font-weight="800" fill="#0f172a" opacity="0.92">{html.escape(initials)}</text>
</svg>""".strip()


def _logo_concept_emblem(motif: str, primary: str, secondary: str, accent: str) -> str:
    return f"""
<svg width="220" height="220" viewBox="0 0 140 140" xmlns="http://www.w3.org/2000/svg" role="img">
  {_svg_defs(primary, secondary, accent)}
  <circle cx="70" cy="70" r="58" fill="#0b1220"/>
  <circle cx="70" cy="70" r="56" fill="none" stroke="url(#gradB)" stroke-width="6"/>
  {_svg_symbol_for_motif(motif, primary)}
</svg>""".strip()


def _logo_concept_symbol_wordmark(motif: str, brand_name: str, primary: str, secondary: str) -> str:
    safe_name = html.escape(brand_name or "")
    return f"""
<svg width="460" height="160" viewBox="0 0 460 160" xmlns="http://www.w3.org/2000/svg" role="img">
  {_svg_defs(primary, secondary, "#F59E0B")}
  <rect x="12" y="20" width="120" height="120" rx="22" fill="#0b1220" stroke="url(#gradA)" stroke-width="4"/>
  <g transform="translate(22,30)">{_svg_symbol_for_motif(motif, primary)}</g>
  <text x="150" y="92" font-family="Inter, Arial, sans-serif" font-size="40" fill="#ffffff" font-weight="800">{safe_name}</text>
  <rect x="150" y="104" width="220" height="6" rx="3" fill="url(#gradB)"/>
</svg>""".strip()


def render_brand_report_html(
    brand_name: str,
    slogan: str,
    domain: str | None,
    domain_available: bool | None,
    structured: dict,
    project_title: str = "Brand Book",
    idea_text: str | None = None,
    domain_checks: dict[str, bool | None] | None = None,   # <-- NOUVEAU
) -> str:
    def esc(x): return html.escape(str(x or ""))
    structured = structured or {}
    avail_txt = "disponible" if domain_available is True else "pris" if domain_available is False else "non vérifié"

    # --- Normalisation des champs structurés ---
    m = structured.get("mission") or ""
    v = structured.get("vision") or ""
    vals = structured.get("values") or []
    if isinstance(vals, str):
        vals = [vals]

    pal_in = structured.get("color_palette") or []
    norm_pal = []
    for idx, c in enumerate(pal_in):
        if isinstance(c, dict):
            name = c.get("name") or f"Couleur {idx+1}"
            hx = c.get("hex") or "#4F46E5"
            use = c.get("usage") or "Usage principal"
        else:
            hx = str(c)
            name = f"Couleur {idx+1}"
            use = "Usage principal"
        norm_pal.append({"name": name, "hex": hx, "usage": use})
    pal = norm_pal

    typo_in = structured.get("typography") or {}
    primary = typo_in.get("primary") if isinstance(typo_in, dict) else None
    secondary = typo_in.get("secondary") if isinstance(typo_in, dict) else None
    typo = {
        "primary": {"font": (primary or {}).get("font", "Inter"), "usage": (primary or {}).get("usage", "Titres")},
        "secondary": {"font": (secondary or {}).get("font", "Inter"), "usage": (secondary or {}).get("usage", "Corps")},
    }

    logo_in = structured.get("logo_guidelines") or {}
    raw_logo_set = logo_in.get("logo_set") or []
    if not isinstance(raw_logo_set, list):
        raw_logo_set = []
    logo_set = []
    for item in raw_logo_set:
        if isinstance(item, dict):
            logo_set.append(item)
        elif isinstance(item, str):
            logo_set.append({"name": item, "rationale": "Proposition inspirée du contexte.", "sketch_svg": None})
    logo = {
        "concept": logo_in.get("concept", ""),
        "variations": logo_in.get("variations") or [],
        "clear_space": logo_in.get("clear_space", ""),
        "min_size": logo_in.get("min_size", ""),
        "dos": logo_in.get("dos") or [],
        "donts": logo_in.get("donts") or [],
        "logo_set": logo_set,
    }

    story_in = structured.get("storytelling") or {}
    story = {
        "origins": story_in.get("origins", ""),
        "values_engagement": story_in.get("values_engagement", ""),
        "proof_points": story_in.get("proof_points") or [],
    }

    cons_in = structured.get("consistency") or {}
    cons = {
        "social": cons_in.get("social", ""),
        "emails": cons_in.get("emails", ""),
        "documents": cons_in.get("documents", ""),
    }

    # --- Propositions de logos : 3 rendus pros et différents ---
    initials = _initials(brand_name)
    primary_hex, secondary_hex, accent_hex = _pick_palette_colors(pal)
    motif = _infer_motif(idea_text or project_title or brand_name)

    rendered_logos = []

    # 1) SVG fournis par l'IA -> priorité
    provided = [
        c
        for c in logo_set
        if isinstance(c, dict) and isinstance(c.get("sketch_svg"), str) and "<svg" in c["sketch_svg"]
    ]
    for c in provided[:3]:
        name = c.get("name") or "Concept"
        rationale = c.get("rationale") or "Croquis IA."
        rendered_logos.append(
            f"""
          <div class="card" style="padding:16px">
            <div class="h3">{esc(name)}</div>
            <div class="muted" style="margin-bottom:8px">{esc(rationale)}</div>
            <div class="logo">{c["sketch_svg"]}</div>
          </div>
        """
        )

    # 2) Complète pour atteindre exactement 3 concepts
    while len(rendered_logos) < 3:
        idx = len(rendered_logos)
        if idx == 0:
            svg = _logo_concept_monogram(initials, primary_hex, secondary_hex)
            name, rationale = "Concept A — Monogramme", "Monogramme géométrique fort, mémorisable."
        elif idx == 1:
            svg = _logo_concept_emblem(motif, primary_hex, secondary_hex, accent_hex)
            name, rationale = "Concept B — Emblème", "Emblème symbolique lié au secteur, rendu premium."
        else:
            svg = _logo_concept_symbol_wordmark(motif, brand_name, primary_hex, secondary_hex)
            name, rationale = "Concept C — Symbole + wordmark", "Symbole moderniste + logotype équilibré."
        rendered_logos.append(
            f"""
          <div class="card" style="padding:16px">
            <div class="h3">{esc(name)}</div>
            <div class="muted" style="margin-bottom:8px">{esc(rationale)}</div>
            <div class="logo">{svg}</div>
          </div>
        """
        )

    # --- Domain availability (multi-TLD) : badges + liste ---
    def _badge(av):
        if av is True:
            return '<span class="badge ok">Disponible</span>'
        if av is False:
            return '<span class="badge ko">Pris</span>'
        return '<span class="badge na">Non vérifié</span>'

    domain_list_html = ""
    if domain_checks:
        items = []
        for dom, av in domain_checks.items():
            items.append(
                f"<div class='domrow'><span>{esc(dom)}</span>{_badge(av)}</div>"
            )
        domain_list_html = (
            "<div class='h2'>Disponibilité des domaines (suggestions)</div>"
            "<div class='card' style='background:#0b1220'>"
            "<div class='domain-grid'>" + "".join(items) + "</div>"
            "</div>"
        )

    # --- Helpers HTML pour listes & couleurs ---
    def color_item(c):
        name = esc(c.get("name"))
        hx = esc(c.get("hex"))
        use = esc(c.get("usage"))
        return f"""
          <div class="flex items-center gap-3 p-3 rounded bg-gray-800/50">
            <div class="w-10 h-10 rounded" style="background:{hx}"></div>
            <div class="text-sm">
              <div class="font-semibold">{name} — {hx}</div>
              <div class="text-gray-300">{use}</div>
            </div>
          </div>
        """

    def li(items):
        if not items:
            return "<p class='text-gray-300'>—</p>"
        if isinstance(items, str):
            items = [items]
        return "<ul class='list-disc pl-6 space-y-1'>" + "".join(f"<li>{esc(it)}</li>" for it in items) + "</ul>"

    # --- HTML final ---
    return f"""<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>{esc(project_title)}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap" rel="stylesheet">
<style>
  :root {{ color-scheme: dark; }}
  body {{ margin:0; background:#0f172a; color:#e5e7eb; font-family: Inter, system-ui, -apple-system, Segoe UI, Roboto, Ubuntu, Cantarell, Noto Sans, Helvetica Neue, Arial; }}
  .container {{ max-width: 980px; margin: 0 auto; padding: 24px; }}
  .card {{ background:#111827; border-radius:12px; padding:20px; box-shadow: 0 10px 25px rgba(0,0,0,.35); }}
  .h1 {{ font-size:28px; font-weight:700; margin:0 0 8px; }}
  .h2 {{ font-size:18px; font-weight:700; color:#818cf8; margin:22px 0 8px; }}
  .h3 {{ font-size:16px; font-weight:700; color:#e5e7eb; margin:0 0 4px; }}
  .muted {{ color:#9ca3af; font-size:12px; }}
  .grid {{ display:grid; gap:14px; }}
  .grid-2 {{ grid-template-columns: repeat(2,minmax(0,1fr)); }}
  .grid-3 {{ grid-template-columns: repeat(3,minmax(0,1fr)); }}
  .pill {{ display:inline-block; background:#1f2937; border-radius:999px; padding:4px 10px; font-size:12px; }}
  .row {{ display:flex; gap:12px; align-items:center; flex-wrap:wrap; }}
  .logo svg {{ width: 180px; height: 180px; display:block; }}

  /* Domain availability list */
  .domain-grid {{ display:grid; gap:8px; }}
  .domrow {{ display:flex; justify-content:space-between; align-items:center;
             padding:6px 10px; background:#0f172a; border:1px solid #1f2937; border-radius:8px; }}
  .badge {{ border-radius:999px; padding:2px 8px; font-size:12px; }}
  .badge.ok {{ background:#065f46; color:#ecfdf5; }}
  .badge.ko {{ background:#7f1d1d; color:#fee2e2; }}
  .badge.na {{ background:#374151; color:#e5e7eb; }}
</style>
</head>
<body>
  <div class="container">
    <div class="card">
      <div class="h1">{esc(project_title)}</div>
      <div class="muted">Brand Book — service clé en main</div>

      <div style="height:14px"></div>
      <div class="grid" style="gap:10px">
        <div class="row">
          <span class="pill">Nom</span><strong>{esc(brand_name)}</strong>
        </div>
        <div class="row">
          <span class="pill">Slogan</span><span>{esc(slogan)}</span>
        </div>
        <div class="row">
          <span class="pill">Domaine</span><span>{esc(domain or '—')} ({esc(avail_txt)})</span>
        </div>
      </div>

      {domain_list_html}

      {"<div class='h2'>Concept (verbatim)</div><p>"+esc(idea_text)+"</p>" if idea_text else ""}

      <div class="h2">Mission</div>
      <p>{esc(m)}</p>

      <div class="h2">Vision</div>
      <p>{esc(v)}</p>

      <div class="h2">Valeurs</div>
      {li(vals)}

      <div class="h2">Propositions de logos</div>
      <div class="grid grid-3">
        {''.join(rendered_logos)}
      </div>

      <div class="h2">Charte graphique — Couleurs</div>
      <div class="grid grid-3">
        {''.join(color_item(c) for c in pal)}
      </div>

      <div class="h2">Charte graphique — Typographies</div>
      <div class="grid grid-2">
        <div class="card" style="background:#0b1220">
          <div class="h3">Primaire</div>
          <div class="muted">{esc(typo['primary']['font'])}</div>
          <div>{esc(typo['primary']['usage'])}</div>
        </div>
        <div class="card" style="background:#0b1220">
          <div class="h3">Secondaire</div>
          <div class="muted">{esc(typo['secondary']['font'])}</div>
          <div>{esc(typo['secondary']['usage'])}</div>
        </div>
      </div>

      <div class="h2">Logo — Guidelines</div>
      <p><strong>Concept</strong> — {esc(logo.get('concept',''))}</p>
      <p><strong>Variations</strong></p>
      {li(logo.get('variations', []))}
      <p><strong>Espaces de sécurité</strong><br>{esc(logo.get('clear_space',''))}</p>
      <p><strong>Taille minimale</strong><br>{esc(logo.get('min_size',''))}</p>
      <div class="grid grid-2">
        <div>
          <div class="h3">À faire</div>
          {li(logo.get('dos', []))}
        </div>
        <div>
          <div class="h3">À éviter</div>
          {li(logo.get('donts', []))}
        </div>
      </div>

      <div class="h2">Storytelling</div>
      <div class="h3">Origines</div>
      <p>{esc(story.get('origins',''))}</p>
      <div class="h3">Valeurs & engagement</div>
      <p>{esc(story.get('values_engagement',''))}</p>
      <div class="h3">Preuves / Cas</div>
      {li(story.get('proof_points', []))}

      <div class="h2">Cohérence multi-supports</div>
      <div class="h3">Réseaux sociaux</div>
      <p>{esc(cons.get('social',''))}</p>
      <div class="h3">Emails & newsletters</div>
      <p>{esc(cons.get('emails',''))}</p>
      <div class="h3">Documents marketing</div>
      <p>{esc(cons.get('documents',''))}</p>
    </div>
  </div>
</body>
</html>
"""

# ─────────────────────────────────────────────────────────────────────────────
# SVG helpers (barres, lignes multi-séries, mini-funnel)
# ─────────────────────────────────────────────────────────────────────────────

def _svg_bar_chart(title: str, pairs: list[tuple[str, float]]) -> str:
    if not pairs:
        return ""
    w, h, pad = 640, 240, 40
    maxv = max(v for _, v in pairs) or 1
    bw = (w - pad*2) / max(1, len(pairs))
    bars = []
    for i, (label, val) in enumerate(pairs):
        x = pad + i * bw
        bh = (h - pad*2) * (val / maxv)
        y = h - pad - bh
        bars.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{bw*0.7:.1f}" height="{bh:.1f}" rx="6" fill="#8b93ff"/>'
                    f'<text x="{x + bw*0.35:.1f}" y="{h - pad + 14}" text-anchor="middle" font-size="10" fill="#cbd5e1">{html.escape(label[:10])}</text>')
    return f'<svg viewBox="0 0 {w} {h}" role="img" aria-label="{html.escape(title)}"><text x="{pad}" y="18" fill="#e5e7eb" font-size="14">{html.escape(title)}</text>' + "".join(bars) + '</svg>'

def _svg_line_chart_multi(title: str, series: dict[str, list[float]], labels: list[str]) -> str:
    w, h, pad = 640, 260, 40
    # normalise la longueur
    L = max((len(v) for v in series.values()), default=0)
    if L == 0: return ""
    xs = [pad + i * ( (w - pad*2) / max(1, L-1) ) for i in range(L)]
    maxy = max((max(v) for v in series.values() if v), default=1) or 1
    colors = ["#8b93ff", "#22d3ee", "#f59e0b"]
    paths, legends = [], []
    for (name, vals), col in zip(series.items(), colors):
        pts = []
        for i, yv in enumerate(vals):
            y = h - pad - ( (h - pad*2) * (yv / maxy) )
            pts.append(f"{xs[i]:.1f},{y:.1f}")
        paths.append(f'<polyline fill="none" stroke="{col}" stroke-width="2.5" points="{" ".join(pts)}"/>')
        legends.append(f'<rect x="{pad + len(legends)*140}" y="{h-22}" width="12" height="12" rx="2" fill="{col}"/><text x="{pad + len(legends)*140 + 18}" y="{h-12}" font-size="12" fill="#cbd5e1">{html.escape(name)}</text>')
    # ticks X
    xticks = "".join(f'<text x="{xs[i]:.1f}" y="{h - pad + 14}" text-anchor="middle" font-size="10" fill="#cbd5e1">{html.escape(labels[i])}</text>' for i in range(L))
    return f'<svg viewBox="0 0 {w} {h}" role="img" aria-label="{html.escape(title)}"><text x="{pad}" y="18" fill="#e5e7eb" font-size="14">{html.escape(title)}</text>{"".join(paths)}{xticks}{"".join(legends)}</svg>'

def _svg_funnel(label: str, counts: dict[str, float]) -> str:
    # construit 6 étapes si dispo
    steps = [("Impressions","impressions"),("Clics","clicks"),("Leads","leads"),("MQL","mqls"),("SQL","sqls"),("Ventes","sales")]
    base = max(counts.get(k,0) for _, k in steps) or 1
    w, h, pad = 340, 220, 12
    y = pad + 10
    rows = []
    for name, key in steps:
        v = counts.get(key, 0)
        width = 300 * (v / base)
        rows.append(f'<rect x="{(w - width)/2:.1f}" y="{y:.1f}" width="{width:.1f}" height="24" rx="6" fill="#1f2937" stroke="#334155"/><text x="{w/2:.1f}" y="{y+16:.1f}" text-anchor="middle" font-size="12" fill="#e5e7eb">{html.escape(name)}: {int(v)}</text>')
        y += 30
    return f'<svg viewBox="0 0 {w} {h}" role="img" aria-label="Funnel {html.escape(label)}"><text x="12" y="16" fill="#e5e7eb" font-size="14">Funnel — {html.escape(label)}</text>{"".join(rows)}</svg>'

# ── Helper SVG ligne + axe Y pour le CA ──────────────────────────────────────
def _svg_line_with_y_axis(title: str, labels: list[str], values: list[float], y_label: str = "CA prévisionnel (€)") -> str:
    if not labels or not values:
        return ""
    import math, html as _html
    w, h = 720, 320
    pad_left, pad_right, pad_top, pad_bottom = 64, 24, 28, 44

    n = len(values)
    vmax = max(1.0, max(values))
    # échelle "ronde"
    step = max(1000, int(round(vmax / 5 / 1000.0)) * 1000)
    ymax = int(math.ceil(vmax / step)) * step

    xs = [pad_left + i * ((w - pad_left - pad_right) / max(1, n - 1)) for i in range(n)]
    def y_of(v: float) -> float:
        return h - pad_bottom - ((h - pad_top - pad_bottom) * (v / ymax))

    pts = " ".join(f"{xs[i]:.1f},{y_of(values[i]):.1f}" for i in range(n))

    # grilles + ticks Y
    yticks = []
    k = 0
    while k <= ymax:
        y = y_of(k)
        yticks.append(
            f'<line x1="{pad_left-6}" y1="{y:.1f}" x2="{w-pad_right}" y2="{y:.1f}" stroke="#1f2937" />'
            f'<text x="{pad_left-10}" y="{y+4:.1f}" text-anchor="end" font-size="11" fill="#cbd5e1">{k:,}</text>'
        )
        k += step

    # ticks X (mois)
    xt = "".join(
        f'<text x="{xs[i]:.1f}" y="{h-18}" text-anchor="middle" font-size="11" fill="#cbd5e1">{_html.escape(labels[i])}</text>'
        for i in range(n)
    )

    return f'''
<svg viewBox="0 0 {w} {h}" role="img" aria-label="{_html.escape(title)}">
  <rect x="0" y="0" width="{w}" height="{h}" fill="none"/>
  <text x="{pad_left}" y="{pad_top-8}" font-size="14" fill="#e5e7eb">{_html.escape(title)}</text>
  <text x="{pad_left-40}" y="{pad_top}" font-size="12" fill="#cbd5e1" transform="rotate(-90 {pad_left-40},{pad_top})">{_html.escape(y_label)}</text>
  {"".join(yticks)}
  <polyline fill="none" stroke="#8b93ff" stroke-width="2.5" points="{pts}" />
  {xt}
</svg>'''.strip()

def render_acquisition_report_html(acq: dict, project_title: str, idea_text: str | None = None) -> str:
    def esc(x): return html.escape(str(x or ""))
    obj = acq.get("objectives", {})
    icp = acq.get("icp", "")
    funnel = acq.get("funnel", {})
    mix = acq.get("channel_mix", [])
    kpis = acq.get("kpis", [])
    agenda = acq.get("agenda", [])
    assumptions = acq.get("assumptions", {})
    mb = acq.get("monthly_budget", 0)
    scenarios = acq.get("forecast_scenarios") or {}
    labels = [r["month"] for r in next(iter(scenarios.values()), [])] or [f"M{i}" for i in range(1,7)]
    annexes = acq.get("annexes") or {}

    # Graphiques (SVG inline, compatibles PDF)
    budget_pairs = [(m["name"], round(m.get("budget_share",0)*mb, 2)) for m in mix]
    chart_budget = _svg_bar_chart("Répartition du budget / mois (€)", budget_pairs)
    series_leads = {name: [row["leads"] for row in rows] for name, rows in scenarios.items()}
    chart_leads = _svg_line_chart_multi("Leads par mois — 3 trajectoires", series_leads, labels)
    base_rows = scenarios.get("Vitesse de croisière") or []
    funnel_html = _svg_funnel("M6 (indicatif)", base_rows[-1] if base_rows else {})

    # Styles screen = styles PDF (on imprime en media=screen côté Playwright)
    styles = """
    <style>
      :root { color-scheme: dark; }
      @page { size: A4; margin: 16mm 12mm; }
      body { margin:0; background:#0f172a; color:#e5e7eb; font-family: Inter, system-ui, -apple-system, Segoe UI, Roboto, Arial; }
      .wrap { max-width: 1000px; margin: 0 auto; padding: 24px; }
      .card { background:#111827; border-radius:14px; padding:18px; box-shadow:0 10px 28px rgba(0,0,0,.35); margin-bottom:14px; }
      h1 { font-size:28px; margin:0 0 8px; font-weight:800 }
      h2 { font-size:18px; margin:16px 0 8px; color:#8b93ff }
      h3 { font-size:14px; margin:10px 0 6px; color:#e5e7eb }
      .muted { color:#9ca3af; font-size:12px }
      .grid { display:grid; gap:14px }
      .grid-2 { grid-template-columns:repeat(2,minmax(0,1fr)) }
      .grid-3 { grid-template-columns:repeat(3,minmax(0,1fr)) }
      .pill { display:inline-block; background:#1f2937; padding:4px 10px; border-radius:999px; font-size:12px }
      .kpi { background:#0b1220; padding:10px 12px; border-radius:10px; border:1px solid #1f2937 }
      .toc a { color:#e5e7eb; text-decoration:none }
      .toc li { margin:4px 0 }
      .pagebreak { page-break-before: always; }
      ul { margin:8px 0 0 18px }
      table { width:100%; border-collapse:separate; border-spacing:0 6px }
      td { vertical-align:top }
    </style>
    """

    # Sommaire (liens ancrés)
    toc = """
      <div class="card">
        <h2>Sommaire</h2>
        <ul class="toc">
          <li><a href="#exec">1. Synthèse exécutive</a></li>
          <li><a href="#mix">2. Mix de canaux & budget</a></li>
          <li><a href="#funnel">3. Parcours & projection 6 mois</a></li>
          <li><a href="#agenda">4. Agenda 12 semaines</a></li>
          <li><a href="#kpis">5. Indicateurs clés</a></li>
          <li><a href="#methodo">6. Méthodologie & hypothèses</a></li>
          <li><a href="#annexes">7. Annexes — Plans détaillés (Ads / SEO / Social)</a></li>
          <li><a href="#glossaire">8. Glossaire</a></li>
        </ul>
      </div>
    """

    # Glossaire simple
    glossaire = """
      <div class="card" id="glossaire">
        <h2>Glossaire</h2>
        <ul>
          <li><strong>CPC</strong> : coût par clic.</li>
          <li><strong>CTR</strong> : taux de clics (clics / impressions).</li>
          <li><strong>Landing page</strong> : page d’atterrissage conçue pour convertir.</li>
          <li><strong>MQL / SQL</strong> : lead marketing qualifié / lead commercial qualifié.</li>
          <li><strong>Close rate</strong> : taux de transformation opportunité → vente.</li>
          <li><strong>ROAS</strong> : chiffre d’affaires / dépenses publicitaires.</li>
        </ul>
      </div>
    """

    # HTML final (multi-pages)
    return f"""<!doctype html>
<html lang="fr"><head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>{esc(project_title)}</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;800&display=swap" rel="stylesheet">
{styles}
</head>
<body>

<div class="wrap">
  <!-- Page de garde -->
  <div class="card">
    <h1>Stratégie d’acquisition — {esc(project_title)}</h1>
    <div class="muted">Livret agence • Export PDF identique au HTML</div>
    {f'<p class="muted" style="margin-top:6px"><span class="pill">Concept</span> {esc(idea_text)}</p>' if idea_text else ''}
  </div>

  {toc}

  <div class="pagebreak"></div>

  <!-- 1. Synthèse -->
  <div class="card" id="exec">
    <h2>1. Synthèse exécutive</h2>
    <p><strong>Cap principal :</strong> {esc(obj.get('north_star',''))}</p>
    <ul>{"".join(f"<li>{esc(x)}</li>" for x in obj.get('targets',[]))}</ul>
    <div class="grid grid-2" style="margin-top:8px">
      <div class="kpi"><strong>Client idéal</strong><br>{esc(icp)}</div>
      <div class="kpi"><strong>Budget mensuel</strong><br>{esc(mb)} €</div>
    </div>
  </div>

  <!-- 2. Mix -->
  <div class="card" id="mix">
    <h2>2. Mix de canaux & budget</h2>
    <div style="margin-top:10px">{chart_budget}</div>
    <table style="margin-top:12px"><tbody>
      {"".join(
        f'<tr>'
        f'<td class="kpi" style="width:20%"><strong>{esc(m["name"])}</strong><br/><span class="muted">{round(m.get("budget_share",0)*100)}% du budget</span></td>'
        f'<td class="kpi" style="width:25%">{esc(m.get("goal",""))}</td>'
        f'<td class="kpi" style="width:55%"><div><strong>Ce que tu fais concrètement :</strong><ul>{"".join(f"<li>{esc(s)}</li>" for s in m.get("beginner_steps",[]))}</ul></div>'
        f'<div style="margin-top:6px" class="muted">KPIs : {esc(", ".join(m.get("kpis",[])))}</div></td>'
        f'</tr>' for m in mix
      )}
    </tbody></table>
  </div>

  <!-- 3. Funnel & projection -->
  <div class="card" id="funnel">
    <h2>3. Parcours & projection 6 mois</h2>
    <div class="grid grid-2">
      <div>
        <h3>Parcours</h3>
        <p><strong>Se faire connaître</strong></p><ul>{"".join(f"<li>{esc(x)}</li>" for x in funnel.get("awareness",[]))}</ul>
        <p><strong>S’intéresser</strong></p><ul>{"".join(f"<li>{esc(x)}</li>" for x in funnel.get("consideration",[]))}</ul>
        <p><strong>Passer à l’action</strong></p><ul>{"".join(f"<li>{esc(x)}</li>" for x in funnel.get("conversion",[]))}</ul>
        <p><strong>Fidéliser</strong></p><ul>{"".join(f"<li>{esc(x)}</li>" for x in funnel.get("retention",[]))}</ul>
      </div>
      <div>
        <h3>Projection</h3>
        <div>{chart_leads}</div>
        <div style="margin-top:10px">{funnel_html}</div>
        <p class="muted" style="margin-top:8px">Trajectoires : <em>Départ prudent</em>, <em>Vitesse de croisière</em>, <em>Accélération</em>.</p>
      </div>
    </div>
  </div>

  <div class="pagebreak"></div>

  <!-- 4. Agenda -->
  <div class="card" id="agenda">
    <h2>4. Agenda 12 semaines (tous niveaux)</h2>
    <div class="grid grid-2">
      {"".join(f'<div class="kpi"><strong>S{a.get("week")}</strong> — {esc(a.get("theme",""))} • {esc(a.get("time",""))} • {esc(a.get("owner",""))}<ul>{"".join(f"<li>{esc(t)}</li>" for t in a.get("tasks",[]))}</ul></div>' for a in agenda)}
    </div>
  </div>

  <!-- 5. KPIs -->
  <div class="card" id="kpis">
    <h2>5. Indicateurs clés</h2>
    <p>{esc(", ".join(kpis))}</p>
  </div>

  <!-- 6. Méthodo -->
  <div class="card" id="methodo">
    <h2>6. Méthodologie & hypothèses</h2>
    <div class="grid grid-3">
      <div class="kpi">CPC: {assumptions.get('cpc','?')} €</div>
      <div class="kpi">CTR: {round(assumptions.get('ctr',0)*100,1)}%</div>
      <div class="kpi">Conv. page: {round(assumptions.get('lp_cvr',0)*100,1)}%</div>
      <div class="kpi">MQL: {round(assumptions.get('mql_rate',0)*100,1)}%</div>
      <div class="kpi">SQL: {round(assumptions.get('sql_rate',0)*100,1)}%</div>
      <div class="kpi">Closing: {round(assumptions.get('close_rate',0)*100,1)}%</div>
    </div>
    <p class="muted" style="margin-top:8px">Ces valeurs sont des médianes sectorielles. Ajuste après 2–3 semaines avec tes données réelles.</p>
  </div>

  <div class="pagebreak"></div>

  <!-- 7. Annexes -->
  <div class="card" id="annexes">
    <h2>7. Annexes — Plans détaillés</h2>
    {"".join(
      f'<div class="kpi" style="margin-bottom:8px"><h3>{esc(title)}</h3><div style="white-space:pre-wrap">{esc(text)}</div></div>'
      for title, text in [
        ("Ads (Search / Social)", annexes.get("ads_strategy")),
        ("SEO (structure & contenu)", annexes.get("seo_plan")),
        ("Réseaux sociaux (orga & créas)", annexes.get("social_plan")),
      ] if text
    ) or '<p class="muted">—</p>'}
  </div>

  {glossaire}

  <div class="card muted">Conseil : garde ce livret comme base. Mets à jour la projection avec tes metrics (CPC, CTR, conv.) chaque mois.</div>
</div>
</body></html>"""

def _get_legal_block(bp: dict) -> dict:
    # accepte les deux emplacements: narrative.legal (nouveau) ou top-level legal (ancien)
    legal = (bp.get("narrative") or {}).get("legal") or bp.get("legal") or {}
    # normalisation + defaults « lisibles » pour éviter une section vide
    return {
        "form":       str(legal.get("form") or "SAS (à confirmer)"),
        "rationale":  str(legal.get("rationale") or "Justification du choix (investisseurs, gouvernance, régime social)."),
        "cap_table":  list(legal.get("cap_table") or ["Répartition initiale à préciser"]),
        "governance": list(legal.get("governance") or ["Pacte d’associés (préemption, leaver…)", "Pouvoirs & organes"]),
        "tax_social": list(legal.get("tax_social") or ["IS/TVA", "Régime social du dirigeant"]),
    }

def render_business_plan_html(bp: dict, project_title: str, idea_text: str | None = None) -> str:
    def esc(x):
        try:
            import html as _html
            return _html.escape(str(x if x is not None else ""))
        except Exception:
            return str(x)

    styles = """
    <style>
      :root { color-scheme: dark; }
      @page { size: A4; margin: 14mm 12mm; }
      body { margin:0; background:#0f172a; color:#e5e7eb; font-family: Inter, system-ui, -apple-system, Segoe UI, Roboto, Arial; }
      .wrap { max-width: 1000px; margin: 0 auto; padding: 24px; }
      .card { background:#111827; border-radius:14px; padding:18px; box-shadow:0 10px 28px rgba(0,0,0,.35); margin-bottom:14px; }
      h1 { font-size:28px; margin:0 0 8px; font-weight:800 }
      h2 { font-size:18px; margin:16px 0 8px; color:#8b93ff }
      h3 { font-size:14px; margin:10px 0 6px; color:#e5e7eb }
      .muted { color:#9ca3af; font-size:12px }
      .grid { display:grid; gap:14px }
      .grid-2 { grid-template-columns:repeat(2,minmax(0,1fr)) }
      .grid-3 { grid-template-columns:repeat(3,minmax(0,1fr)) }
      .kpi { background:#0b1220; padding:10px 12px; border-radius:10px; border:1px solid #1f2937 }
      table { width:100%; border-collapse:separate; border-spacing:0 6px }
      th, td { padding:6px 10px; }
      th { text-align:left; color:#cbd5e1; border-bottom:1px solid #1f2937 }
      td { background:#0b1220; border:1px solid #1f2937; }
      .pagebreak { page-break-before: always; }
      ul { margin:8px 0 0 18px }
      .toc a { color:#e5e7eb; text-decoration:none }
    </style>
    """


    meta = bp.get("meta", {})
    nar  = bp.get("narrative", {})
    ass  = bp.get("assumptions", {})
    inv  = bp.get("investments", {})
    fin  = bp.get("financing", {})
    pnl  = bp.get("pnl_3y", {})
    cash = bp.get("cash_12m", {})
    bre  = bp.get("breakeven", {})
    s36  = bp.get("series_36m", {})
    glossary = bp.get("glossary", {})
    annexes  = bp.get("annexes", {})

    # --- HOTFIX: normalise les blobs narratifs pour éviter AttributeError quand GPT renvoie une string ---
    # Sécurise nar au cas où ce serait une simple chaîne
    if not isinstance(nar, dict):
        nar = {"executive_summary": str(nar or "")}

    def _as_list(x):
        if isinstance(x, list):
            return x
        if isinstance(x, str) and x.strip():
            return [x.strip()]
        return []

    market = nar.get("market") or {}
    if not isinstance(market, dict):
        market = {
            "size_drivers": str(market or ""),
            "segments": [],
            "competition": [],
            "regulation": [],
        }

    gtm = nar.get("go_to_market") or {}
    if not isinstance(gtm, dict):
        gtm = {
            "segmentation": [],
            "positioning": str(gtm or ""),
            "mix": [],
            "sales_process": [],
        }

    ops = nar.get("operations") or {}
    if not isinstance(ops, dict):
        ops = {
            "organization": str(ops or ""),
            "people": [],
            "resources": [],
            "roadmap": [],
        }

    # Funding & risks (obj/list robustes)
    fund = nar.get("funding") or {}
    if not isinstance(fund, dict):
        fund = {"ask": str(fund or ""), "use_of_funds": [], "milestones": []}
    risks = nar.get("risks") or []
    if isinstance(risks, str):
        risks = [risks]

    proj_detail = nar.get("project_detail")
    proj_text = None
    if isinstance(proj_detail, dict):
        pass
    else:
        proj_detail = None
        proj_text = str(nar.get("project") or "")

    # si tu as déplacé 'legal' et 'glossary' dans bp["legal"]/bp["glossary"], on les récupère prudemment
    legal = bp.get("legal") or nar.get("legal") or {}
    if not isinstance(legal, dict):
        legal = {
            "form": str(legal or ""),
            "rationale": "",
            "cap_table": [],
            "governance": [],
            "tax_social": [],
        }

    glossary = bp.get("glossary") or nar.get("glossary") or {}
    if not isinstance(glossary, dict):
        glossary = {}
    # --- /HOTFIX ---

    legal_block = _get_legal_block(bp)

    # ▼▼▼ Fallbacks sectoriels pour éviter les "—" quand GPT renvoie des listes vides
    sector_cat = (meta.get("sector_category") or "").lower()

    def _pick(cat, key):
        defaults = {
            "saas_b2b": {
                "segments": [
                    "PME françaises (10–200 salariés) — décideurs: DG/COO/Head of Ops",
                    "ETI ciblées — directions métiers avec budget outillage"
                ],
                "competition": [
                    "SaaS US établis (HubSpot, Monday…) — riche mais coûteux",
                    "Outils internes (Excel/scripts) — faible scalabilité",
                    "Intégrateurs locaux — sur-mesure onéreux"
                ],
                "regulation": [
                    "RGPD/CNIL (DPA, registre traitements, minimisation)",
                    "Hébergement UE, chiffrement au repos/en transit",
                    "Clauses contractuelles: SLA, DPA, réversibilité"
                ],
                "mix": [
                    "Produit: plans Starter/Pro/Entreprise, SSO & SLA",
                    "Prix: abonnement mensuel/annuel, remises 10–20% à l’année",
                    "Distribution: site + démos, partenaires intégrateurs",
                    "Communication: SEO technique + contenu, SEA B2B, webinars, LinkedIn"
                ],
                "sales_process": [
                    "Lead → qualification (BANT/ICP) → démo → essai 14j → closing → onboarding",
                    "KPI: CAC, taux de conv., cycle de vente, churn, LTV"
                ],
                "people": [
                    "CEO/COO (direction & partenariats)",
                    "Sales (SDR + AE) — chasse/farming",
                    "Marketing (content/paid/ops)",
                    "Customer Success & Support",
                    "Tech/Produit (selon externalisation)"
                ],
                "resources": [
                    "CRM (HubSpot/Pipedrive), facturation (Stripe)",
                    "Analytics (Matomo/GA4), emailing (Brevo)",
                    "Stack cloud (Scaleway/OVH), monitoring",
                    "Outils doc & projet (Notion/Jira)"
                ],
            },
            "ecommerce_b2c": {
                "segments": [
                    "18–35 ans urbains — achats en ligne, sensibles au prix",
                    "35–55 ans CSP+ — recherche qualité/rapidité/livraison"
                ],
                "competition": [
                    "Marketplaces (Amazon, Cdiscount) — choix/rapidité",
                    "Boutiques spécialisées — conseil de niche",
                    "DNVB concurrentes — image de marque forte"
                ],
                "regulation": [
                    "Droit conso (rétractation, garanties), TVA",
                    "RGPD (cookies, consentement)",
                    "Éco-contributions (emballages) selon produit"
                ],
                "mix": [
                    "Produit: gammes claires, bundles, éditions limitées",
                    "Prix: ancrage, codes promo maîtrisés, AOV",
                    "Distribution: site + marketplaces sélectionnées",
                    "Communication: SEO long tail, ads Meta/Google, influence"
                ],
                "sales_process": [
                    "Acquisition → ajout panier → checkout → relance abandons → fidélisation",
                    "KPI: CTR, CR, AOV, CAC, ROAS, réachat"
                ],
                "people": [
                    "CMO/e-commerce manager",
                    "Acquisition paid + CRM/e-mailing",
                    "Service client & logistique (3PL si besoin)"
                ],
                "resources": [
                    "CMS (Shopify/Woo), paiement (Stripe), anti-fraude",
                    "WMS/3PL, PIM si catalogue large",
                    "Outils CRO (A/B test), heatmaps"
                ],
            },
            "services_locaux": {
                "segments": [
                    "Particuliers zone de chalandise (rayon 20 km)",
                    "Professionnels locaux (restauration, commerces, TPE)"
                ],
                "competition": [
                    "Artisans locaux historiques",
                    "Plateformes d’intermédiation",
                    "Do-it-yourself selon service"
                ],
                "regulation": [
                    "Réglementations métier & assurances pro",
                    "Devis/facturation, TVA",
                    "Hygiène/sécurité le cas échéant"
                ],
                "mix": [
                    "Produit: forfaits clairs + options",
                    "Prix: grille transparente, pack récurrence",
                    "Distribution: référencement local, partenariats",
                    "Communication: Google Business, flyers, réseaux sociaux"
                ],
                "sales_process": [
                    "Demande → devis → intervention → satisfaction → récurrence/parrainage",
                    "KPI: taux d’acceptation devis, récurrence, NPS"
                ],
                "people": [
                    "Gérant(e), 1–2 techniciens/ouvriers selon charge",
                    "Assist. admin/commerciale (part-time)"
                ],
                "resources": [
                    "Véhicule/outil métier",
                    "Logiciel devis/facturation, agenda, CRM simple"
                ],
            },
        }
        # générique par défaut
        defaults["generic_b2b"] = defaults["saas_b2b"]
        return defaults.get(cat or "generic_b2b", {}).get(key, [])

    # Remplissage des trous
    market["segments"]    = market.get("segments")    or _pick(sector_cat, "segments")
    market["competition"] = market.get("competition") or _pick(sector_cat, "competition")
    market["regulation"]  = market.get("regulation")  or _pick(sector_cat, "regulation")

    strat = gtm  # alias déjà utilisé plus bas
    strat["mix"]           = strat.get("mix")           or _pick(sector_cat, "mix")
    strat["sales_process"] = strat.get("sales_process") or _pick(sector_cat, "sales_process")
    if not strat.get("positioning"):
        strat["positioning"] = "Promesse claire (valeur + preuve), différenciation par expérience & ROI."

    ops["people"]    = ops.get("people")    or _pick(sector_cat, "people")
    ops["resources"] = ops.get("resources") or _pick(sector_cat, "resources")
    # ▲▲▲ fin des fallbacks

    # Graphiques (CA avec axe Y demandé)
    rev_labels = [f"M{i}" for i in range(1, 13)]
    rev_values = [ (s36.get("revenue") or [0]*37)[i] for i in range(1,13) ]
    chart_rev  = _svg_line_with_y_axis("CA mensuel prévisionnel (M1–M12)", rev_labels, rev_values, y_label="CA prévisionnel (€)")

    # EBITDA : tu peux conserver ton helper multi-lignes existant si tu l'as,
    # sinon commente la ligne suivante.
    try:
        ebd_values = [ (s36.get("ebitda") or [0]*37)[i] for i in range(1,13) ]
        chart_ebd  = _svg_line_chart_multi("EBITDA mensuel (M1–M12)", {"EBITDA": ebd_values}, rev_labels)
    except Exception:
        chart_ebd = ""

    # Tableaux
    inv_rows = "".join(
        f"<tr><td>{esc(x['label'])}</td><td>{x['month']}</td><td>{x['life_years']} ans</td><td>{round(x['amount'],2)} €</td><td>{round(x['amort_month'],2)} €/mois</td></tr>"
        for x in inv.get("items", [])
    )
    pnl_row = lambda key: "".join(f"<td>{round(v,2)} €</td>" for v in pnl.get(key, [0,0,0]))

    loan_sched = fin.get("loan", {}).get("schedule") or []
    loan_rows = "".join(
        f"<tr><td>M{it['month']}</td><td>{it['payment']} €</td><td>{it['interest']} €</td><td>{it['principal']} €</td><td>{it['balance']} €</td></tr>"
        for it in loan_sched[:12]
    )

    # Sommaire avec Juridique + Glossaire (glossaire avant annexes)
    toc = """
          <div class="card">
            <h2>Sommaire</h2>
            <ul class="toc">
              <li><a href="#exec">1. Executive summary</a></li>
              <li><a href="#team">2. Équipe fondatrice</a></li>
              <li><a href="#project">3. Présentation du projet</a></li>
              <li><a href="#eco">4. Partie économique</a></li>
              <li><a href="#fin">5. Partie financière</a></li>
              <li><a href="#funding">6. Besoin de financement</a></li>
              <li><a href="#risks">7. Risques & parades</a></li>
              <li><a href="#legal">8. Partie juridique</a></li>
              <li><a href="#gloss">9. Glossaire</a></li>
              <li><a href="#annex">10. Annexes</a></li>
            </ul>
          </div>
        """


    def ul(items):
        if not items: return "<p class='muted'>—</p>"
        if isinstance(items, dict):
            return "<ul>" + "".join(f"<li><strong>{esc(k)}:</strong> {esc(v)}</li>" for k,v in items.items()) + "</ul>"
        if isinstance(items, str):
            items = [items]
        return "<ul>" + "".join(f"<li>{esc(x)}</li>" for x in items) + "</ul>"

    def dl(dct):
        if not isinstance(dct, dict) or not dct: return "<p class='muted'>—</p>"
        return "<ul>" + "".join(f"<li><strong>{esc(k)}</strong> — {esc(v)}</li>" for k,v in dct.items()) + "</ul>"

    bre_rev = bre.get("revenue") or bre.get("revenue_annual_needed")
    bre_hint = bre.get("month_hint") or (f"vers M{bre['month']}" if bre.get("month") else "non atteint sur 36 mois")
    bre_m_ca = bre.get("revenue_month")

    return f"""<!doctype html>
<html lang="fr"><head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>{esc(project_title)}</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;800&display=swap" rel="stylesheet">
{styles}
</head>
<body>
<div class="wrap">

  <div class="card">
    <h1>Business Plan — {esc(project_title)}</h1>
    <div class="muted">Version automatique — base solide à compléter</div>
    {f'<p class="muted" style="margin-top:6px">Concept: {esc(idea_text)}</p>' if idea_text else ''}
  </div>

  {toc}

  <div class="pagebreak"></div>

  <div class="card" id="exec">
    <h2>1. Executive summary</h2>
    <p>{esc(nar.get("executive_summary"))}</p>
    <div class="grid grid-3" style="margin-top:8px">
      <div class="kpi">Secteur: {esc(meta.get("sector"))} ({esc(meta.get("sector_category"))})</div>
      <div class="kpi">Objectifs 24 mois: {esc(", ".join((nar.get("objectives") or [])))}</div>
      <div class="kpi">Proposition de valeur: {esc((nar.get("value_prop") or ""))}</div>
    </div>
  </div>

  <div class="card" id="team">
    <h2>2. Équipe fondatrice</h2>
    <p>{esc(nar.get("team"))}</p>
  </div>

  <div class="card" id="project">
    <h2>3. Présentation du projet</h2>
    {(
      f"<h3>Problème & opportunité</h3><p>{esc((proj_detail or {}).get('problem',''))}</p>"
      f"<h3>Solution & différenciation</h3><p>{esc((proj_detail or {}).get('solution',''))}</p>"
      f"<h3>Clients cibles</h3>" + ul((proj_detail or {}).get('targets')) +
      f"<h3>Fonctionnalités clés</h3>" + ul((proj_detail or {}).get('product_features')) +
      f"<h3>Proposition de valeur</h3><p>{esc((proj_detail or {}).get('value_prop',''))}</p>" +
      f"<h3>Jalons</h3>" + ul((proj_detail or {}).get('milestones'))
    ) if proj_detail else f"<p>{esc(proj_text or '')}</p>"}
  </div>

  <div class="pagebreak"></div>

  <div class="card" id="eco">
    <h2>4. Partie économique</h2>

    <h3>Marché & environnement (France)</h3>
    <p><strong>Taille & moteurs de croissance :</strong> {esc(market.get("size_drivers",""))}</p>
    <p><strong>Segments de clientèle :</strong></p>{ul(market.get("segments"))}
    <p><strong>Concurrence & alternatives :</strong></p>{ul(market.get("competition"))}
    <p><strong>Réglementation / normes :</strong></p>{ul(market.get("regulation"))}

    <h3>Stratégie commerciale</h3>
    <p><strong>Segmentation & ciblage :</strong></p>{ul(gtm.get("segmentation"))}
    <p><strong>Positionnement :</strong> {esc(gtm.get("positioning",""))}</p>
    <p><strong>Mix marketing :</strong></p>{ul(gtm.get("mix"))}
    <p><strong>Processus de vente :</strong></p>{ul(gtm.get("sales_process"))}

    <h3>Organisation & moyens</h3>
    <p><strong>Organisation :</strong> {esc(ops.get("organization",""))}</p>
    <p><strong>Moyens humains :</strong></p>{ul(ops.get("people"))}
    <p><strong>Moyens matériels & logiciels :</strong></p>{ul(ops.get("resources"))}
    <p><strong>Feuille de route :</strong></p>{ul(ops.get("roadmap"))}

    <h3>Prévisions de CA (12 mois)</h3>
    <div style="margin-top:10px">{chart_rev}</div>
    {f'<div style="margin-top:10px">{chart_ebd}</div>' if chart_ebd else ''}
  </div>

  <div class="pagebreak"></div>

  <div class="card" id="fin">
    <h2>5. Partie financière</h2>

    <h3>Investissements & amortissements</h3>
    <table>
      <thead><tr><th>Élément</th><th>Mois</th><th>Durée</th><th>Montant</th><th>Dotation/mois</th></tr></thead>
      <tbody>{inv_rows or '<tr><td colspan="5">—</td></tr>'}</tbody>
    </table>

    <h3>Plan de financement initial</h3>
    <div class="grid grid-2">
      <div class="kpi"><strong>Besoins</strong>
        <ul>
          <li>Investissements: {inv.get("total")} €</li>
          <li>BFR (est.): {fin.get("initial_uses",{}).get("working_capital","0")} €</li>
          <li><strong>Total: {fin.get("initial_uses",{}).get("total","0")} €</strong></li>
        </ul>
      </div>
      <div class="kpi"><strong>Ressources</strong>
        <ul>
          <li>Fonds propres: {fin.get("initial_sources",{}).get("equity","0")} €</li>
          <li>Emprunt: {fin.get("initial_sources",{}).get("loan","0")} €</li>
          <li><strong>Total: {fin.get("initial_sources",{}).get("total","0")} €</strong></li>
        </ul>
      </div>
    </div>

    <h3>Compte de résultat prévisionnel (3 ans)</h3>
    <table>
      <thead><tr><th></th><th>Année 1</th><th>Année 2</th><th>Année 3</th></tr></thead>
      <tbody>
        <tr><td>Chiffre d'affaires</td>{pnl_row('revenue')}</tr>
        <tr><td>Coût des ventes</td>{pnl_row('cogs')}</tr>
        <tr><td>Marge brute</td>{pnl_row('gross')}</tr>
        <tr><td>Marketing</td>{pnl_row('marketing')}</tr>
        <tr><td>Charges fixes</td>{pnl_row('fixed')}</tr>
        <tr><td>EBITDA</td>{pnl_row('ebitda')}</tr>
        <tr><td>Amortissements</td>{pnl_row('depreciation')}</tr>
        <tr><td>EBIT</td>{pnl_row('ebit')}</tr>
        <tr><td>Intérêts</td>{pnl_row('interest')}</tr>
        <tr><td>Résultat avant impôt</td>{pnl_row('ebt')}</tr>
        <tr><td>IS (théorique)</td>{pnl_row('tax')}</tr>
        <tr><td>Résultat net</td>{pnl_row('net')}</tr>
      </tbody>
    </table>

    <div class="pagebreak"></div>

    <h3>Plan de trésorerie (12 mois)</h3>
    <table>
      <thead><tr><th>Mois</th><th>Encaissements</th><th>Décaissements</th><th>Trésorerie fin de mois</th></tr></thead>
      <tbody>
        {''.join(f"<tr><td>M{m['month']}</td><td>{m['in']} €</td><td>{m['out']} €</td><td>{m['end']} €</td></tr>" for m in cash.get("months",[]))}
      </tbody>
    </table>

    <h3>Échéancier d'emprunt (12 premiers mois)</h3>
    <table>
      <thead><tr><th>Mois</th><th>Échéance</th><th>Intérêts</th><th>Capital</th><th>Reste dû</th></tr></thead>
      <tbody>{loan_rows or '<tr><td colspan="5">—</td></tr>'}</tbody>
    </table>

    <h3>Plan de financement à 3 ans</h3>
    <div class="grid grid-3">
      <div class="kpi">Dette fin A1: {round(fin.get('three_year_view',{}).get('loan_outstanding_end_y1',0),2)} €</div>
      <div class="kpi">Dette fin A2: {round(fin.get('three_year_view',{}).get('loan_outstanding_end_y2',0),2)} €</div>
      <div class="kpi">Dette fin A3: {round(fin.get('three_year_view',{}).get('loan_outstanding_end_y3',0),2)} €</div>
    </div>

   <h3>Seuil de rentabilité</h3>
<p>
  CA annuel à atteindre : <strong>{bre_rev or "—"} €</strong> — indication : {esc(bre_hint)}
  {f"(mois charnière: M{bre.get('month')}, CA: {bre_m_ca} €)" if bre.get("month") else ""}.
</p>
  </div>

  <div class="pagebreak"></div>
  
  <div class="card" id="funding">
  <h2>6. Besoin de financement</h2>
  <p><strong>Demande (copy) :</strong> {esc(fund.get("ask",""))}</p>
  <p class="muted">Recommandation (runway + BFR) : <strong>{round((fund.get("recommended_ask_eur") or 0),2)} €</strong></p>

  <h3>Plan initial — Sources</h3>
  <ul>
    <li>Fonds propres : {((fund.get("initial_plan") or {}).get("sources") or {}).get("equity","—")} €</li>
    <li>Emprunt : {((fund.get("initial_plan") or {}).get("sources") or {}).get("loan","—")} €</li>
    <li><strong>Total</strong> : {((fund.get("initial_plan") or {}).get("sources") or {}).get("total","—")} €</li>
  </ul>

  <h3>Plan initial — Besoins</h3>
  <ul>
    <li>Investissements : {((fund.get("initial_plan") or {}).get("uses") or {}).get("investments","—")} €</li>
    <li>BFR : {((fund.get("initial_plan") or {}).get("uses") or {}).get("working_capital","—")} €</li>
    <li><strong>Total</strong> : {((fund.get("initial_plan") or {}).get("uses") or {}).get("total","—")} €</li>
  </ul>

  <h3>Utilisation des fonds</h3>{ul(fund.get("use_of_funds"))}
  <h3>Jalons associés</h3>{ul(fund.get("milestones"))}
</div>

  <div class="card" id="risks">
    <h2>7. Principaux risques & parades</h2>
    {ul(risks)}
  </div>

  <div class="card" id="legal">
  <h2>8. Partie juridique</h2>
  <p><strong>Forme retenue :</strong> {esc(legal_block['form'])}</p>
  <p><strong>Justification :</strong> {esc(legal_block['rationale'])}</p>
  <h3>Répartition du capital (cap table)</h3>{ul(legal_block['cap_table'])}
  <h3>Gouvernance & pouvoirs</h3>{ul(legal_block['governance'])}
  <h3>Régime fiscal & social</h3>{ul(legal_block['tax_social'])}
</div>

  <div class="card" id="gloss">
    <h2>9. Glossaire</h2>
    {dl(glossary)}
  </div>

  <div class="card" id="annex">
    <h2>10. Annexes</h2>
    {"".join(
      f'<div class="kpi" style="margin-bottom:8px"><h3>{esc(k)}</h3><div style="white-space:pre-wrap">{esc(v)}</div></div>'
      for k, v in (annexes or {}).items()
    ) or '<p class="muted">—</p>'}
  </div>

</div>
</body></html>"""


# --- PLAN HTML RENDERER ------------------------------------------------------
def render_action_plan_html(plan: dict, project_title: str) -> str:
    import html as _html
    def esc(x): return _html.escape(str(x or ""))

    weeks = plan.get("weeks")
    if not isinstance(weeks, list) or not weeks:
        weeks = []
        for i, line in enumerate(plan.get("plan") or [], start=1):
            weeks.append({"week": i, "theme": "", "goals": [], "kpis": [], "tasks": [{"title": str(line)}]})

    styles = """
    <style>
      :root { color-scheme: dark; }
      body { margin:0; background:#0f172a; color:#e5e7eb; font-family: Inter, system-ui, -apple-system, Segoe UI, Roboto, Arial; }
      .wrap { max-width:1000px; margin:0 auto; padding:24px; }
      .card { background:#111827; border:1px solid #1f2937; border-radius:14px; padding:18px; margin-bottom:14px; }
      h1 { font-size:26px; margin:0 0 10px; font-weight:800 }
      h2 { font-size:18px; margin:14px 0 8px; color:#8b93ff }
      h3 { font-size:16px; margin:10px 0 6px; }
      ul { margin:8px 0 0 18px }
      .badge { display:inline-block; background:#0b1220; border:1px solid #1f2937; padding:6px 10px; border-radius:999px; font-size:12px; color:#cbd5e1 }
    </style>
    """

    def _as_list(x):
        if isinstance(x, list): return x
        if x is None: return []
        return [x]

    def _task_li(t):
        if isinstance(t, str):  # compat
            return esc(t)
        d = t if isinstance(t, dict) else getattr(t, "dict")() if hasattr(t, "dict") else {}
        title = d.get("title")
        owner = d.get("owner")
        est   = d.get("estimate_h")
        due   = d.get("due_offset_days")
        desc  = d.get("desc")
        parts = [title or ""]
        if owner: parts.append(f"— {owner}")
        meta = []
        if est: meta.append(f"{est} h")
        if due is not None: meta.append(f"J+{due}")
        if meta: parts.append(f"({' • '.join(str(m) for m in meta)})")
        if desc: parts.append(f" — {desc}")
        return esc(" ".join(str(p) for p in parts if p))

    def ul(items, is_tasks=False):
        items = _as_list(items)
        if not items: return "<p class='badge'>—</p>"
        if is_tasks:
            return "<ul>" + "".join(f"<li>{_task_li(x)}</li>" for x in items) + "</ul>"
        return "<ul>" + "".join(f"<li>{esc(x)}</li>" for x in items) + "</ul>"

    blocks = []
    for w in weeks:
        d = w if isinstance(w, dict) else (w.dict() if hasattr(w, "dict") else {})
        title = d.get("title")
        if not title:
            wk = d.get("week")
            th = d.get("theme") or ""
            title = f"Semaine {wk}{': ' + th if th else ''}"
        blocks.append(f"""
          <div class="card">
            <h2>{esc(title)}</h2>
            <h3>Objectifs</h3>{ul(d.get('goals'))}
            <h3>Tâches</h3>{ul(d.get('tasks'), is_tasks=True)}
            <h3>KPIs</h3>{ul(d.get('kpis'))}
          </div>
        """)

    return f"""<!doctype html>
<html lang="fr"><head>
<meta charset="utf-8"/><meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>{esc(project_title)}</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;800&display=swap" rel="stylesheet">
{styles}
</head><body><div class="wrap">
  <div class="card"><h1>{esc(project_title)}</h1>
    <p class="badge">Plan d'action (export HTML · PDF · Agenda)</p>
  </div>
  {''.join(blocks)}
</div></body></html>"""

# ─────────────────────────────────────────────────────────────────────────────
# Export PDF identique au HTML via Chromium headless (Playwright)
# ─────────────────────────────────────────────────────────────────────────────

async def export_pdf_from_html(
    html_path: str,
    out_path: str | None = None,
    format_: str = "A4",
    margin_top: str = "16mm",
    margin_right: str = "12mm",
    margin_bottom: str = "16mm",
    margin_left: str = "12mm",
) -> str:
    from playwright.async_api import async_playwright
    in_path = Path(html_path).resolve()
    if out_path is None:
        out_path = str(in_path.with_suffix(".pdf"))
    out_file = Path(out_path).resolve()

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"]
        )
        context = await browser.new_context()
        page = await context.new_page()
        await page.goto(in_path.as_uri(), wait_until="networkidle")
        await page.emulate_media(media="screen")
        await page.pdf(
            path=str(out_file),
            format=format_,
            print_background=True,
            prefer_css_page_size=True,  # 👈 respecte @page du HTML
            margin={"top": margin_top, "right": margin_right, "bottom": margin_bottom, "left": margin_left},
        )
        await browser.close()
    return str(out_file)