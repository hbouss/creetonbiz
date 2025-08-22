# backend/config.py
import os
from dotenv import load_dotenv

load_dotenv()  # utile en local; en prod Railway lit les env automatiquement

class Settings:
    # OpenAI
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")

    # Base de données
    DATABASE_URL: str = os.getenv("DATABASE_URL", "")

    # Auth/JWT
    JWT_SECRET_KEY: str = os.getenv("JWT_SECRET_KEY", "")
    JWT_ALGORITHM: str = os.getenv("JWT_ALGORITHM", "HS256")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", 60*24))

    # Stripe
    STRIPE_SECRET_KEY: str = os.getenv("STRIPE_SECRET_KEY", "")
    STRIPE_WEBHOOK_SECRET: str = os.getenv("STRIPE_WEBHOOK_SECRET", "")
    STRIPE_SUCCESS_URL: str = os.getenv(
        "STRIPE_SUCCESS_URL",
        "http://localhost:5173/checkout/success?session_id={CHECKOUT_SESSION_ID}"
    )
    STRIPE_CANCEL_URL: str = os.getenv(
        "STRIPE_CANCEL_URL",
        "http://localhost:5173/checkout/cancel"
    )
    STRIPE_PRICE_ID_INFINITY: str = os.getenv("STRIPE_PRICE_ID_INFINITY", "")
    STRIPE_PRICE_ID_STARTNOW_ONE_TIME: str = os.getenv("STRIPE_PRICE_ID_STARTNOW_ONE_TIME", "")

    # Frontend
    FRONTEND_BASE_URL: str = os.getenv("FRONTEND_BASE_URL", "http://localhost:5173")

    # (optionnel, si tu publies les landings en statique)
    PUBLIC_WEB_ROOT: str = os.getenv("PUBLIC_WEB_ROOT", "")
    PUBLIC_BASE_URL: str = os.getenv("PUBLIC_BASE_URL", "")

settings = Settings()