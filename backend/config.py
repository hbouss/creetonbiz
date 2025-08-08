import os
from dotenv import load_dotenv

load_dotenv()  # Charge les variables depuis .env

class Settings:
    # Clé API OpenAI
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY")
    # URL de la base de données
    DATABASE_URL: str = os.getenv("DATABASE_URL")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 1 jour
    # Stripe
    STRIPE_SECRET_KEY: str = os.getenv("STRIPE_SECRET_KEY", "")
    STRIPE_SUCCESS_URL: str = os.getenv("STRIPE_SUCCESS_URL",
                                        "http://localhost:5173/checkout/success?session_id={CHECKOUT_SESSION_ID}")
    STRIPE_CANCEL_URL: str = os.getenv("STRIPE_CANCEL_URL", "http://localhost:5173/checkout/cancel")
    STRIPE_WEBHOOK_SECRET: str = os.getenv("STRIPE_WEBHOOK_SECRET", "")
    STRIPE_PRICE_ID_INFINITY: str = os.getenv("STRIPE_PRICE_ID_INFINITY")
    STRIPE_PRICE_ID_STARTNOW_ONE_TIME: str = os.getenv("STRIPE_PRICE_ID_STARTNOW_ONE_TIME")
    # JWT pour l'authentification
    JWT_SECRET_KEY: str = os.getenv("JWT_SECRET_KEY")
    # Algorithme de signature JWT (par défaut HS256)
    JWT_ALGORITHM: str = os.getenv("JWT_ALGORITHM", "HS256")

    # Frontend
    FRONTEND_BASE_URL: str = os.getenv("FRONTEND_BASE_URL", "http://localhost:5173")

# Instance globale des settings
settings = Settings()