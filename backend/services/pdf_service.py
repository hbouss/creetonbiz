# backend/services/pdf_service.py
from io import BytesIO
from datetime import datetime
from typing import List, Any, Dict
import os

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, ListFlowable, ListItem, Table, TableStyle
)
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont


# Police UTF-8 si dispo
def _try_register_fonts():
    try:
        pdfmetrics.registerFont(TTFont("DejaVuSans", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"))
        pdfmetrics.registerFont(TTFont("DejaVuSans-Bold", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"))
        return "DejaVuSans", "DejaVuSans-Bold"
    except Exception:
        return "Helvetica", "Helvetica-Bold"


FONT_REGULAR, FONT_BOLD = _try_register_fonts()

styles = getSampleStyleSheet()
styles.add(ParagraphStyle(name="H1", fontName=FONT_BOLD, fontSize=18, spaceAfter=10))
styles.add(ParagraphStyle(name="H2", fontName=FONT_BOLD, fontSize=14, spaceAfter=6, textColor=colors.HexColor("#4F46E5")))
styles.add(ParagraphStyle(name="Body", fontName=FONT_REGULAR, fontSize=11, leading=14))
styles.add(ParagraphStyle(name="Meta", fontName=FONT_REGULAR, fontSize=9, textColor=colors.grey))


def _p(text: str) -> Paragraph:
    return Paragraph((text or "").replace("\n", "<br/>"), styles["Body"])


def _section(title: str) -> Paragraph:
    return Paragraph(title, styles["H2"])


def _bullets(items: Any) -> ListFlowable:
    if isinstance(items, str):
        items = [items]
    if not isinstance(items, list):
        items = [str(items)]
    flow = [ListItem(_p(str(x)), leftIndent=8) for x in items if x]
    return ListFlowable(flow, bulletType="bullet", start="•", leftIndent=12)


def _kv_table(data: Dict[str, Any]) -> Table:
    rows = [[Paragraph(f"<b>{k}</b>", styles["Body"]), _p(str(v))] for k, v in data.items()]
    t = Table(rows, colWidths=[4 * cm, 11 * cm])
    t.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.25, colors.grey),
        ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.lightgrey),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BACKGROUND", (0, 0), (-1, 0), colors.whitesmoke),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    return t


def _pct_from_label(label: str, mapping: Dict[str, int], default: int = 50) -> int:
    if not isinstance(label, str):
        return default
    return mapping.get(label.strip().lower(), default)


def _progress_bar(pct: int, width_cm: float = 10.0, height_cm: float = 0.5):
    pct = max(0, min(100, int(pct)))
    filled = pct / 100.0
    colWidths = [filled * width_cm * cm, (1 - filled) * width_cm * cm]
    t = Table([["", ""]], colWidths=colWidths, rowHeights=[height_cm * cm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, 0), colors.HexColor("#10B981")),
        ("BACKGROUND", (1, 0), (1, 0), colors.HexColor("#1F2937")),
        ("BOX", (0, 0), (-1, -1), 0.25, colors.HexColor("#374151")),
    ]))
    return t


def _story_for_offer(title: str, j: Dict[str, Any]) -> List[Any]:
    persona = j.get("persona", "")
    pains = j.get("pain_points", [])
    structured = j.get("structured_offer")

    if isinstance(structured, dict):
        mo = structured.get("market_overview", {}) or {}
        dm = structured.get("demand_analysis", {}) or {}
        ca = structured.get("competitor_analysis", {}) or {}
        er = structured.get("environment_regulation", {}) or {}
        syn = structured.get("synthesis", "") or ""

        state_pct = _pct_from_label(mo.get("current_state", ""),
                                    {"régression": 25, "regression": 25, "stagnation": 50, "progression": 80}, 50)
        trend_pct = _pct_from_label(dm.get("customer_count_trend", ""),
                                    {"en baisse": 33, "stable": 50, "en hausse": 85}, 50)
        budget_pct = _pct_from_label(dm.get("budget", ""),
                                     {"faible": 30, "moyen": 60, "élevé": 90, "eleve": 90}, 50)
        pace_pct = _pct_from_label(er.get("tech_evolution_pace", ""),
                                   {"lent": 33, "modéré": 66, "modere": 66, "rapide": 100}, 50)

        story: List[Any] = [
            Paragraph(title, styles["H1"]),
            Paragraph(f"Exporté le {datetime.now().strftime('%d/%m/%Y %H:%M')}", styles["Meta"]),
            Spacer(1, 10),
            _section("Synthèse exécutive"),
            _p(syn or "—"),
            Spacer(1, 8),
            _section("Indicateurs clés"),
            Paragraph("État du marché", styles["Body"]), _progress_bar(state_pct), Spacer(1, 4),
            Paragraph("Évolution du nombre de clients", styles["Body"]), _progress_bar(trend_pct), Spacer(1, 4),
            Paragraph("Budget client moyen", styles["Body"]), _progress_bar(budget_pct), Spacer(1, 4),
            Paragraph("Rythme d'innovation", styles["Body"]), _progress_bar(pace_pct), Spacer(1, 10),
            _section("Persona"),
            _p(persona or "—"),
            Spacer(1, 8),
            _section("Pain points"),
            _bullets(pains),
            Spacer(1, 10),

            _section("Étude du marché"),
            Paragraph("<b>Volume</b>", styles["Body"]), _p(mo.get("volume", "—")), Spacer(1, 4),
            Paragraph("<b>Situation actuelle</b>", styles["Body"]), _p(mo.get("current_state", "—")), Spacer(1, 4),
            Paragraph("<b>Tendances</b>", styles["Body"]), _bullets(mo.get("trends", [])), Spacer(1, 4),
            Paragraph("<b>Produits / Services</b>", styles["Body"]), _bullets(mo.get("products_services", [])), Spacer(1, 4),
            Paragraph("<b>Principaux acteurs</b>", styles["Body"]), _bullets(mo.get("main_players", [])),
            Spacer(1, 10),

            _section("Étude de la demande"),
            Paragraph("<b>Segments</b>", styles["Body"]), _bullets(dm.get("segments", [])), Spacer(1, 4),
            Paragraph("<b>Localisations</b>", styles["Body"]), _bullets(dm.get("locations", [])), Spacer(1, 4),
            Paragraph("<b>Comportements</b>", styles["Body"]), _bullets(dm.get("behaviors", [])), Spacer(1, 4),
            Paragraph("<b>Critères de choix</b>", styles["Body"]), _bullets(dm.get("choice_criteria", [])), Spacer(1, 10),

            _section("Analyse de l'offre (concurrence)"),
            Paragraph("<b>Concurrents directs</b>", styles["Body"]),
        ]

        directs = ca.get("direct", [])
        if isinstance(directs, list) and directs and isinstance(directs[0], dict):
            lines = []
            for c in directs:
                lines.append(
                    f"{c.get('name','—')} — Positionnement: {c.get('positioning','—')}. "
                    f"Forces: {c.get('strengths','—')}. Faiblesses: {c.get('weaknesses','—')}."
                )
            story += [_bullets(lines)]
        else:
            story += [_bullets(directs)]
        story += [
            Spacer(1, 4),
            Paragraph("<b>Concurrents indirects</b>", styles["Body"]), _bullets(ca.get("indirect", [])), Spacer(1, 4),
            Paragraph("<b>Points de différenciation</b>", styles["Body"]), _bullets(ca.get("differentiation_points", [])), Spacer(1, 4),
            Paragraph("<b>Facteurs de succès</b>", styles["Body"]), _bullets(ca.get("success_factors", [])), Spacer(1, 4),
            Paragraph("<b>Échecs & leçons</b>", styles["Body"]), _bullets(ca.get("failures_lessons", [])),
            Spacer(1, 10),

            _section("Environnement & réglementation"),
            Paragraph("<b>Innovations</b>", styles["Body"]), _bullets(er.get("innovations", [])), Spacer(1, 4),
            Paragraph("<b>Cadre réglementaire</b>", styles["Body"]), _bullets(er.get("regulatory_framework", [])), Spacer(1, 4),
            Paragraph("<b>Associations / acteurs</b>", styles["Body"]), _bullets(er.get("associations", [])), Spacer(1, 4),
            Paragraph("<b>Barrières à l'entrée</b>", styles["Body"]), _bullets(er.get("entry_barriers", [])),
        ]
        return story

    # Ancien format
    offer_text = j.get("offer", "")
    return [
        Paragraph(title, styles["H1"]),
        Paragraph(f"Exporté le {datetime.now().strftime('%d/%m/%Y %H:%M')}", styles["Meta"]),
        Spacer(1, 10),
        _section("Offre"), _p(offer_text or "—"), Spacer(1, 6),
        _section("Persona"), _p(persona or "—"), Spacer(1, 6),
        _section("Pain points"), _bullets(pains),
    ]


def _story_for_model(title: str, j: Dict[str, Any]) -> List[Any]:
    return [
        Paragraph(title, styles["H1"]),
        Paragraph(f"Exporté le {datetime.now().strftime('%d/%m/%Y %H:%M')}", styles["Meta"]),
        Spacer(1, 10),
        _section("Business Model recommandé"),
        _p(j.get("model", "")),
    ]


def _story_for_brand(title: str, j: Dict[str, Any]) -> List[Any]:
    domain_avail = j.get("domain_available")
    avail_txt = "disponible" if domain_avail is True else "pris" if domain_avail is False else "non vérifié"
    data = {
        "Nom de marque": j.get("brand_name", ""),
        "Slogan": j.get("slogan", ""),
        "Nom de domaine": j.get("domain", ""),
        "Disponibilité": avail_txt,
    }
    return [
        Paragraph(title, styles["H1"]),
        Paragraph(f"Exporté le {datetime.now().strftime('%d/%m/%Y %H:%M')}", styles["Meta"]),
        Spacer(1, 10),
        _kv_table(data),
    ]


def _story_for_marketing(title: str, j: Dict[str, Any]) -> List[Any]:
    """Rendu enrichi si pas de pdf_path Playwright."""
    acq = j.get("acquisition_structured")
    if isinstance(acq, dict) and acq:
        obj = acq.get("objectives", {}) or {}
        icp = acq.get("icp", "—")
        mb = acq.get("monthly_budget", 0)
        mix = acq.get("channel_mix", []) or []
        fun = acq.get("funnel", {}) or {}
        agenda = acq.get("agenda", []) or []
        kpis = acq.get("kpis", []) or []
        ass = acq.get("assumptions", {}) or {}
        scen = acq.get("forecast_scenarios", {}) or {}
        base = scen.get("Vitesse de croisière") or next(iter(scen.values()), [])

        story: List[Any] = [
            Paragraph(title, styles["H1"]),
            Paragraph(f"Exporté le {datetime.now().strftime('%d/%m/%Y %H:%M')}", styles["Meta"]),
            Spacer(1, 10),

            _section("1. Synthèse exécutive"),
            _p(f"<b>Cap principal :</b> {obj.get('north_star','—')}"),
            _bullets(obj.get("targets", [])),
            Spacer(1, 6),
            _kv_table({"Client idéal": icp, "Budget mensuel": f"{mb} €"}),
            Spacer(1, 10),

            _section("2. Mix de canaux & budget"),
            _bullets([f"{m.get('name','—')} — {int(round((m.get('budget_share',0)*100)))}% • {m.get('goal','')}" for m in mix]),
            Spacer(1, 4),
            _p("<b>Étapes concrètes (débutant) :</b>"),
            _bullets([f"{m.get('name','—')}: " + '; '.join(m.get('beginner_steps', [])[:5]) for m in mix]),
            Spacer(1, 10),

            _section("3. Parcours & projection (6 mois)"),
            _p("<b>Parcours</b>"),
            _p("<i>Découverte</i>"), _bullets(fun.get("awareness", [])),
            _p("<i>Intérêt</i>"), _bullets(fun.get("consideration", [])),
            _p("<i>Action</i>"), _bullets(fun.get("conversion", [])),
            _p("<i>Fidélisation</i>"), _bullets(fun.get("retention", [])),
        ]

        if isinstance(base, list) and base:
            rows = [["Mois", "Leads", "Ventes", "Dépenses (€)"]]
            for r in base:
                rows.append([r.get("month", ""), str(r.get("leads", "")), str(r.get("sales", "")), str(r.get("spend", ""))])
            t = Table(rows, colWidths=[2.2 * cm, 3 * cm, 3 * cm, 4 * cm])
            t.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.whitesmoke),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.lightgrey),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ]))
            story += [Spacer(1, 6), t]

        story += [
            Spacer(1, 10),
            _section("4. Agenda 12 semaines"),
            _bullets([f"S{a.get('week')}: {a.get('theme','')} • {a.get('time','')} • {a.get('owner','')}" for a in agenda]),
            Spacer(1, 10),

            _section("5. KPIs"),
            _bullets(kpis),
            Spacer(1, 10),

            _section("6. Hypothèses (médianes sectorielles)"),
            _kv_table({
                "CPC (€)": ass.get("cpc", "—"),
                "CTR": f"{round(ass.get('ctr', 0) * 100, 1)}%",
                "Conv. landing": f"{round(ass.get('lp_cvr', 0) * 100, 1)}%",
                "MQL": f"{round(ass.get('mql_rate', 0) * 100, 1)}%",
                "SQL": f"{round(ass.get('sql_rate', 0) * 100, 1)}%",
                "Closing": f"{round(ass.get('close_rate', 0) * 100, 1)}%",
            }),
        ]

        annex = j.get("annexes", {}) or {}
        if any(annex.values()):
            story += [Spacer(1, 10), _section("7. Annexes — Plans détaillés")]
            for k, label in [("ads_strategy", "Ads"), ("seo_plan", "SEO"), ("social_plan", "Réseaux sociaux")]:
                if annex.get(k):
                    story += [Paragraph(f"<b>{label}</b>", styles["Body"]), _p(_as_text(annex[k])), Spacer(1, 6)]

        return story

    # Très ancien format
    ads = j.get("ads_strategy") or j.get("ads")
    seo = j.get("seo_plan") or j.get("seo")
    soc = j.get("social_plan") or j.get("social")
    return [
        Paragraph(title, styles["H1"]),
        Paragraph(f"Exporté le {datetime.now().strftime('%d/%m/%Y %H:%M')}", styles["Meta"]),
        Spacer(1, 10),
        _section("Ads"), _p(_as_text(ads)), Spacer(1, 6),
        _section("SEO"), _p(_as_text(seo)), Spacer(1, 6),
        _section("Réseaux sociaux"), _p(_as_text(soc)),
    ]


def _story_for_plan(title: str, j: Dict[str, Any]) -> List[Any]:
    plan = j.get("plan") or []
    story = [
        Paragraph(title, styles["H1"]),
        Paragraph(f"Exporté le {datetime.now().strftime('%d/%m/%Y %H:%M')}", styles["Meta"]),
        Spacer(1, 10),
    ]
    if isinstance(plan, list):
        for idx, week in enumerate(plan, start=1):
            if isinstance(week, str):
                story += [_section(f"Semaine {idx}"), _bullets([week]), Spacer(1, 4)]
            elif isinstance(week, dict):
                wk = week.get("semaine", idx)
                tasks = week.get("tâches") or week.get("tasks") or []
                story += [_section(f"Semaine {wk}"), _bullets(tasks), Spacer(1, 4)]
    else:
        story += [_p(_as_text(plan))]
    return story


def _as_text(block: Any) -> str:
    if block is None:
        return "—"
    if isinstance(block, str):
        return block
    if isinstance(block, list):
        return "\n".join(f"• {x}" for x in block)
    if isinstance(block, dict):
        return "\n".join(f"• {k}: {v}" for k, v in block.items())
    return str(block)


def make_pdf_from_deliverable(d) -> bytes:
    """
    d: instance de backend.models.Deliverable
    Retourne les bytes PDF.
    """
    title = d.title or d.kind.capitalize()
    j = d.json_content or {}

    # 1) Si on a déjà un PDF Playwright, on le renvoie tel quel
    try:
        pdf_path = j.get("pdf_path") if isinstance(j, dict) else None
    except Exception:
        pdf_path = None
    if isinstance(pdf_path, str) and os.path.exists(pdf_path):
        with open(pdf_path, "rb") as f:
            return f.read()

    # 2) Sinon : fallback ReportLab (anciens livrables)
    story: List[Any] = []
    if d.kind == "offer":
        story = _story_for_offer(title, j)
    elif d.kind == "model":
        story = _story_for_model(title, j)
    elif d.kind == "brand":
        story = _story_for_brand(title, j)
    elif d.kind == "marketing":
        story = _story_for_marketing(title, j)
    elif d.kind == "plan":
        story = _story_for_plan(title, j)
    else:
        story = [
            Paragraph(title, styles["H1"]),
            Paragraph(f"Exporté le {datetime.now().strftime('%d/%m/%Y %H:%M')}", styles["Meta"]),
            Spacer(1, 10),
            _section("Données"),
            _p(_as_text(j)),
        ]

    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=2 * cm, rightMargin=2 * cm,
        topMargin=2 * cm, bottomMargin=2 * cm,
        title=title
    )
    doc.build(story)
    return buf.getvalue()