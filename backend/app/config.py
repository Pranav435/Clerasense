"""
Clerasense Backend – Configuration Loader
Loads all secrets and settings from .env via environment variables.
No secret may be hard-coded anywhere in the codebase.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env from project root
_env_path = Path(__file__).resolve().parent.parent.parent / ".env"
load_dotenv(dotenv_path=_env_path)


class Config:
    """Base configuration – values sourced exclusively from environment."""

    # --- Secrets ---
    OPENAI_API_KEY: str = os.environ.get("OPENAI_API_KEY", "")
    DATABASE_URL: str = os.environ.get("DATABASE_URL", "")
    FLASK_SECRET_KEY: str = os.environ.get("FLASK_SECRET_KEY", "")
    JWT_SECRET: str = os.environ.get("JWT_SECRET", "")

    # --- AI / Embedding ---
    EMBEDDING_MODEL_NAME: str = os.environ.get("EMBEDDING_MODEL_NAME", "text-embedding-3-small")

    # --- App ---
    APP_ENV: str = os.environ.get("APP_ENV", "development")
    DEBUG: bool = APP_ENV == "development"

    # --- Rate limiting ---
    RATE_LIMIT_DEFAULT: str = "60/minute"

    # --- Validation ---
    @classmethod
    def validate(cls) -> None:
        """Raise on missing critical environment variables."""
        required = ["OPENAI_API_KEY", "DATABASE_URL", "FLASK_SECRET_KEY", "JWT_SECRET"]
        missing = [k for k in required if not getattr(cls, k)]
        if missing:
            raise EnvironmentError(
                f"Missing required environment variables: {', '.join(missing)}. "
                "Ensure a .env file exists with all required values."
            )
