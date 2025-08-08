# backend/services/pdf_service.py
from io import BytesIO
from datetime import datetime
from typing import List, Any, Dict

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, ListFlowable, ListItem, Table, TableStyle
)
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

# (Optionnel) essaie d'enregistrer une police UTF-8 confortable si dispo
def _try_register_fonts():
    try:
        pdfmetrics.registerFont(TTFont("DejaVuSans", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"))
        pdfmetrics.registerFont(TTFont("DejaVuSans-Bold", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"))
        return "DejaVuSans", "DejaVuSans-Bold"
    except Exception:
        # fallback sur Helvetica
        return "Helvetica", "Helvetica-Bold"

FONT_REGULAR, FONT_BOLD = _try_register_fonts()

styles = getSampleStyleSheet()
styles.add(ParagraphStyle(name="H1", fontName=FONT_BOLD, fontSize=18, spaceAfter=10))
styles.add(ParagraphStyle(name="H2", fontName=FONT_BOLD, fontSize=14, spaceAfter=6, textColor=colors.HexColor("#4F46E5")))
styles.add(ParagraphStyle(name="Body", fontName=FONT_REGULAR, fontSize=11, leading=14))
styles.add(ParagraphStyle(name="Meta", fontName=FONT_REGULAR, fontSize=9, textColor=colors.grey))

def _p(text: str) -> Paragraph:
    # échappe minimalement
    text = (text or "").replace("\n", "<br/>")
    return Paragraph(text, styles["Body"])

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
    t = Table(rows, colWidths=[4*cm, 11*cm])
    t.setStyle(TableStyle([
        ("BOX", (0,0), (-1,-1), 0.25, colors.grey),
        ("INNERGRID", (0,0), (-1,-1), 0.25, colors.lightgrey),
        ("VALIGN", (0,0), (-1,-1), "TOP"),
        ("BACKGROUND", (0,0), (-1,0), colors.whitesmoke),
        ("LEFTPADDING", (0,0), (-1,-1), 6),
        ("RIGHTPADDING", (0,0), (-1,-1), 6),
        ("TOPPADDING", (0,0), (-1,-1), 4),
        ("BOTTOMPADDING", (0,0), (-1,-1), 4),
    ]))
    return t

def _story_for_offer(title: str, j: Dict[str, Any]) -> List[Any]:
    offer   = j.get("offer", "")
    persona = j.get("persona", "")
    pains   = j.get("pain_points", [])
    return [
        Paragraph(title, styles["H1"]),
        Paragraph(f"Exporté le {datetime.now().strftime('%d/%m/%Y %H:%M')}", styles["Meta"]),
        Spacer(1, 10),
        _section("Offre"),
        _p(offer),
        Spacer(1, 6),
        _section("Persona"),
        _p(persona),
        Spacer(1, 6),
        _section("Pain points"),
        _bullets(pains),
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
    ads = j.get("ads_strategy") or j.get("ads")
    seo = j.get("seo_plan")     or j.get("seo")
    soc = j.get("social_plan")  or j.get("social")

    story = [
        Paragraph(title, styles["H1"]),
        Paragraph(f"Exporté le {datetime.now().strftime('%d/%m/%Y %H:%M')}", styles["Meta"]),
        Spacer(1, 10),
    ]
    story += [_section("Ads"), _p(_as_text(ads)), Spacer(1, 6)]
    story += [_section("SEO"), _p(_as_text(seo)), Spacer(1, 6)]
    story += [_section("Réseaux sociaux"), _p(_as_text(soc))]
    return story

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
    story = []

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
        # fallback générique
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
        leftMargin=2*cm, rightMargin=2*cm,
        topMargin=2*cm, bottomMargin=2*cm,
        title=title
    )
    doc.build(story)
    return buf.getvalue()