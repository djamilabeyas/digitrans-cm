from functools import lru_cache
from typing import List
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # Application
    ENVIRONMENT: str = "prod"
    SECRET_KEY: str                        # injecté depuis Azure Key Vault via CSI driver
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    ALGORITHM: str = "RS256"              # RSA asymétrique – plus sûr que HMAC en multi-service

    # Base de données PostgreSQL
    DB_HOST: str
    DB_PORT: int = 5432
    DB_NAME: str = "crm_db"
    DB_USER: str
    DB_PASSWORD: str
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 20
    DB_POOL_TIMEOUT: int = 30

    # Redis – cache & offline sync queue
    REDIS_HOST: str
    REDIS_PORT: int = 6380               # port SSL Azure Redis
    REDIS_PASSWORD: str
    REDIS_SSL: bool = True
    REDIS_OFFLINE_QUEUE_TTL: int = 86400  # 24h – durée max file offline

    # Sécurité
    CORS_ORIGINS: List[str] = [
        "https://savoirmanger.agrocam.cm",
        "http://localhost:5173",
        "http://localhost:3000",
        "null",           # fichiers ouverts depuis le disque (file://)
    ]
    ALLOWED_HOSTS: List[str] = ["*.agrocam.cm", "localhost"]
    RATE_LIMIT_PER_MINUTE: int = 100
    MAX_REQUEST_SIZE_MB: int = 10

    # Azure Key Vault
    AZURE_KEY_VAULT_URL: str = ""
    AZURE_CLIENT_ID: str = ""

    # Monitoring
    APPLICATION_INSIGHTS_CONNECTION_STRING: str = ""
    LOG_LEVEL: str = "INFO"

    @property
    def database_url(self) -> str:
        ssl = "require" if self.ENVIRONMENT == "prod" else "disable"
        return (
            f"postgresql+asyncpg://{self.DB_USER}:{self.DB_PASSWORD}"
            f"@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
            f"?ssl={ssl}"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
