import os
from dotenv import load_dotenv

load_dotenv()  # Charge les variables depuis .env

class Settings:
    # Clé API OpenAI
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY")
    # URL de la base de données
    DATABASE_URL: str = os.getenv("DATABASE_URL")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 1 jour
    # JWT pour l'authentification
    JWT_SECRET_KEY: str = os.getenv("JWT_SECRET_KEY")
    # Algorithme de signature JWT (par défaut HS256)
    JWT_ALGORITHM: str = os.getenv("JWT_ALGORITHM", "HS256")

# Instance globale des settings
settings = Settings()