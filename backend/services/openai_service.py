# backend/services/openai_service.py
import openai
from backend.config import settings

openai.api_key = settings.OPENAI_API_KEY

def generate_business_idea(profil: dict) -> str:
    """
    Appelle l'API OpenAI pour générer une idée de business à partir d'un profil.
    Retourne une chaîne JSON ou texte brut.
    """
    prompt = (
            "⚠️ Réponds **uniquement** par un **objet JSON valide** "
            "contenant exactement ces quatre clés :\n"
            '  - "idee"\n'
            '  - "persona"\n'
            '  - "nom"\n'
            '  - "slogan"\n'
            "Sans aucun texte explicatif avant ou après.\n\n"
            f"Profil utilisateur : {profil}"
    )
    response = openai.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7,
        max_tokens=500,
    )
    # On récupère le contenu du chat
    content = response.choices[0].message.content
    print("⏰ [DEBUG] Réponse OpenAI brute :", content)
    return content