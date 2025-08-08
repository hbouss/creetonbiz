# backend/services/openai_service.py
import json
import logging
import re
from textwrap import dedent

import openai
from backend.config import settings

openai.api_key = settings.OPENAI_API_KEY
log = logging.getLogger(__name__)

_ALLOWED_KEYS = {"idee", "persona", "nom", "slogan", "potential_rating"}
_FENCES = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE | re.MULTILINE)

def _clean_fences(s: str) -> str:
    s = (s or "").strip()
    s = _FENCES.sub("", s)
    s = re.sub(r",\s*([}\]])", r"\1", s)  # virgules traînantes
    s = s.replace("“", '"').replace("”", '"').replace("’", "'")
    return s.strip()

def _to_float_0_10(value) -> float:
    try:
        x = float(value)
    except Exception:
        return 0.0
    x = max(0.0, min(10.0, x))
    return float(f"{x:.1f}")

def generate_business_idea(profil: dict) -> str:
    """
    Génère une idée business (JSON strict) avec focus :
      - Idée
      - Marché (segmentation + ordre de grandeur)
      - Projection (12–24 mois)
    Clés JSON inchangées pour compatibilité : idee, persona, nom, slogan, potential_rating.
    Retourne une chaîne JSON valide (aucun texte hors JSON).
    """
    secteur = (profil.get("secteur") or "").strip()
    objectif = (profil.get("objectif") or "").strip()
    competences = profil.get("competences") or []
    competences_str = ", ".join(competences) if isinstance(competences, list) else str(competences)

    system_msg = dedent("""\
        Tu es un conseiller startup. Ta mission : proposer UNE idée claire et désirable
        avec un angle marché et une projection simple. Pas de digressions.

        RÈGLES STRICTES
        - Réponds en français.
        - Retourne UNIQUEMENT un objet JSON valide, sans texte autour.
        - Clés EXACTES : "idee", "persona", "nom", "slogan", "potential_rating".
        - "potential_rating" : nombre décimal entre 0 et 10 (ex: 7.8).
        - Pas de détails de monétisation, de coûts ou de pricing. Reste sur idée + marché + projection.

        STYLE & CONTENU (concis, orienté croissance)
        - "idee" (≈ 90–140 mots) structuré en 3 mini-sections (dans le même paragraphe, séparées par des marqueurs) :
          • Concept — ce que fait l’idée et pourquoi elle donne envie.
          • Marché — segment(s) visés + ordre de grandeur (qualitatif, pas de chiffres inventés précis).
          • Projection — où être en 12–24 mois (jalons réalistes : adoption, couverture, traction attendue).
        - "persona" : 1–2 lignes max (rôle + contexte d’usage).
        - "nom" : court, mémorisable.
        - "slogan" : bénéfice clair (6–10 mots).
        - Ton : crédible, énergisant, sans buzzwords vides.
    """)

    user_msg = dedent(f"""\
        Profil utilisateur
        - Secteur : {secteur or "non précisé"}
        - Objectif : {objectif or "non précisé"}
        - Compétences : {competences_str or "non précisées"}

        Format de sortie attendu (JSON uniquement) :
        {{
          "idee": "Concept — ... Marché — ... Projection — ...",
          "persona": "…",
          "nom": "…",
          "slogan": "…",
          "potential_rating": 0.0
        }}
    """)

    # Jusqu’à 3 tentatives pour garantir un JSON propre
    for attempt in range(1, 3 + 1):
        try:
            resp = openai.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": system_msg},
                    {"role": "user", "content": user_msg},
                ],
                temperature=0.6,         # créatif mais fiable
                top_p=0.9,
                presence_penalty=0.1,
                frequency_penalty=0.1,
                max_tokens=620,
                response_format={"type": "json_object"},  # force JSON
            )
            raw = resp.choices[0].message.content or ""
            cleaned = _clean_fences(raw)

            data = json.loads(cleaned)  # peut lever si invalide

            # Filtrage + garde-fous
            out = {k: data.get(k) for k in _ALLOWED_KEYS}
            out["idee"] = (out.get("idee") or "").strip()
            out["persona"] = (out.get("persona") or "").strip()
            out["nom"] = (out.get("nom") or "").strip()
            out["slogan"] = (out.get("slogan") or "").strip()
            out["potential_rating"] = _to_float_0_10(out.get("potential_rating"))

            if not all(out.get(k) for k in ["idee", "persona", "nom", "slogan"]):
                raise ValueError("Champs texte manquants ou vides.")

            # Petites vérifs de forme sur 'idee' pour s'assurer que les 3 marqueurs existent
            if not any(marker in out["idee"] for marker in ["Concept —", "Concept -", "Concept —"]):
                out["idee"] = "Concept — " + out["idee"]
            if "Marché" not in out["idee"]:
                out["idee"] += " Marché — Segment visé et ordre de grandeur qualitatif. "
            if "Projection" not in out["idee"]:
                out["idee"] += " Projection — Jalons réalistes à 12–24 mois."

            return json.dumps(out, ensure_ascii=False)

        except Exception as e:
            log.warning("[generate_business_idea] tentative %s échouée: %s", attempt, e)
            if attempt == 3:
                fallback = {
                    "idee": (
                        "Concept — Idée en cours de génération. "
                        "Marché — Segment principal à confirmer, potentiel qualitatif prometteur. "
                        "Projection — Objectif : premières preuves d’adoption sous 12 mois."
                    ),
                    "persona": "Utilisateur cible à préciser (rôle + contexte).",
                    "nom": "Idée à valider",
                    "slogan": "Clair, utile, concret.",
                    "potential_rating": 0.0,
                }
                return json.dumps(fallback, ensure_ascii=False)
            continue