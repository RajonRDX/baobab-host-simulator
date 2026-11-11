# backend/app/config.py
from typing import List
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):

    # Application
    APP_NAME: str = "RAJON Private Host Simulator"
    APP_ENV: str = "production"

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
    HSM_MODE: str = "SOFT_HSM_REMOTE"
    HSM_REMOTE_URL: str = "https://thales-10k-soft-hsm.onrender.com/api/host/command"
    HSM_HEADER_LENGTH: int = 4

    # =====================================================
    # LOGGING
    # =====================================================
    LOG_RAW_DATA: bool = True

    # =====================================================
    # CORS
    # =====================================================
    CORS_ORIGINS: str = (
        "https://rajon-test-payment-solution.netlify.app,"
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
