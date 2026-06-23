from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_BACKEND_ROOT = Path(__file__).resolve().parent.parent


def resolve_sqlite_database_url(url: str) -> str:
    """Resolve relative sqlite paths under backend/ and ensure the folder exists."""
    if not url.startswith("sqlite"):
        return url
    if url.startswith("sqlite:////"):
        return url
    path_part = url.removeprefix("sqlite:///")
    if path_part.startswith("./"):
        path_part = path_part[2:]
    db_path = (_BACKEND_ROOT / path_part).resolve()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{db_path.as_posix()}"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    APP_NAME: str = "Facebook Posting"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False

    # Local SQLite — all app data lives in backend/data/
    DATABASE_URL: str = "sqlite:///./data/facebook_posting.db"
    API_PORT: int = 8002

    SECRET_KEY: str = "change-this-secret-key-in-production-use-long-random-string"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24

    CORS_ORIGINS: str = "http://localhost:5174,http://127.0.0.1:5174"

    # Admin login — set in .env
    ADMIN_EMAIL: str = ""
    ADMIN_PASSWORD: str = ""

    # SMTP — configured in backend .env only (NOT in dashboard UI)
    SMTP_HOST: str = "smtp.gmail.com"
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM_EMAIL: str = ""
    SMTP_FROM_NAME: str = "Facebook Posting"
    SMTP_USE_TLS: bool = True

    PLAYWRIGHT_TIMEOUT: int = 60000
    # False = visible Chromium on Start (required for manual Facebook login)
    PLAYWRIGHT_HEADLESS: bool | None = False

    # Facebook — manual login in browser; reminder email after 5 min if not logged in
    # Posting app: stay on Marketplace after login — skip /vehicles, filters, listing scrape
    STOP_AFTER_MARKETPLACE: bool = True
    # Chromium + Facebook UI language (Italian user)
    BROWSER_LOCALE: str = "it-IT"
    BROWSER_TIMEZONE: str = "Europe/Rome"
    FACEBOOK_ORIGIN: str = "https://it-it.facebook.com"
    FACEBOOK_SESSION_FILE: str = "data/facebook_session.json"
    FACEBOOK_PROFILE_DIR: str = "data/facebook_chrome_profile"

    @property
    def admin_email(self) -> str:
        return self.ADMIN_EMAIL.strip()

    @property
    def admin_password(self) -> str:
        return self.ADMIN_PASSWORD

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]

    def smtp_config_dict(self) -> dict:
        return {
            "smtp_host": self.SMTP_HOST,
            "smtp_port": str(self.SMTP_PORT),
            "smtp_user": self.SMTP_USER,
            "smtp_password": self.SMTP_PASSWORD,
            "smtp_from_email": self.SMTP_FROM_EMAIL or self.SMTP_USER,
            "smtp_from_name": self.SMTP_FROM_NAME,
            "smtp_use_tls": "true" if self.SMTP_USE_TLS else "false",
        }


@lru_cache
def get_settings() -> Settings:
    return Settings()
