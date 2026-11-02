import os
from typing import List
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    APP_NAME: str = "BAOBAB Private Host Simulator"
    APP_ENV: str = "development"
    SECRET_KEY: str = "dev-secret-key-do-not-use-in-prod-9876543210abcdef"
    ADMIN_USERNAME: str = "admin"
    ADMIN_PASSWORD: str = "AdminPassword123!"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 720

    DATABASE_URL: str = "sqlite:///./baobab_host.db"

    HSM_MODE: str = "SOFT_HSM_LOCAL"  # SOFT_HSM_LOCAL | SOFT_HSM_REMOTE | MOCK_SIMULATED
    HSM_REMOTE_URL: str = "http://127.0.0.1:8888/api/hsm_api"
    HSM_HEADER_LENGTH: int = 4
# [PATCH step00_02:config_log_raw_data]
    LOG_RAW_DATA: bool = True

    CORS_ORIGINS: str = "http://localhost:5173,http://127.0.0.1:5173,http://localhost:3000"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def cors_origin_list(self) -> List[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]


settings = Settings()
