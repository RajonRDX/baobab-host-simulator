# backend/app/config.py
from typing import List
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):

    # Application
    APP_NAME: str = "BAOBAB Private Host Simulator"
    APP_ENV: str = "development"

    # Security
    SECRET_KEY: str = "dev-secret-key-do-not-use-in-prod-9876543210abcdef"
    ADMIN_USERNAME: str = "admin"
    ADMIN_PASSWORD: str = "AdminPassword123!"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 720
    ENFORCE_SECURE_DEFAULTS: bool = False

    # Database
    DATABASE_URL: str = "sqlite:///./baobab_host.db"

    # =====================================================
    # HSM CONFIGURATION
    # =====================================================

    # OPTION 1: LOCAL SOFT HSM
    # HSM_MODE: str = "SOFT_HSM_LOCAL"
    # HSM_REMOTE_URL: str = "http://127.0.0.1:8001/api/host/command"

    # OPTION 2: REMOTE SOFT HSM (CURRENTLY ACTIVE)
    HSM_MODE: str = "SOFT_HSM_REMOTE"
    HSM_REMOTE_URL: str = "https://thales-10k-soft-hsm.onrender.com/api/host/command"

    # HSM communication settings
    HSM_HEADER_LENGTH: int = 4

    # =====================================================
    # LOGGING
    # =====================================================
    LOG_RAW_DATA: bool = False

    # =====================================================
    # CORS (set CORS_ORIGINS in Render env to your Netlify URL)
    # =====================================================
    CORS_ORIGINS: str = (
        "http://localhost:5173,"
        "http://127.0.0.1:5173,"
        "http://localhost:3000"
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    @property
    def cors_origin_list(self) -> List[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]


settings = Settings()
