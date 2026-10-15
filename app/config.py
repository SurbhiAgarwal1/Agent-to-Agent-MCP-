from functools import lru_cache
from typing import List
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


OLD_HARDCODED_KEYS = {
    "emergency-blood-secret-key-3c9f28a1",
    "production-emergency-blood-key-928f01a3",
}

OBVIOUS_PLACEHOLDERS = {
    "changeme",
    "secret",
    "your-secret-key",
}


class Settings(BaseSettings):
    """Application configuration settings loaded from environment or defaults."""
    app_name: str = "Blood Donation Matching System"
    environment: str = "development"
    debug: bool = True
    host: str = "127.0.0.1"
    port: int = 8000
    database_url: str = "sqlite:///./blood_donation.db"
    
    jwt_secret_key: str
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000,http://localhost:5173,http://127.0.0.1:5173,http://localhost:8000,http://127.0.0.1:8000"
    # Development bootstrap credential for creating the first ADMIN account.
    # Keep this empty in production; public ADMIN self-registration is then disabled.
    admin_signup_key: str = ""
    
    llm_provider: str = "mock"
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"

    @field_validator("jwt_secret_key")
    @classmethod
    def validate_jwt_secret_key(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError(
                "JWT_SECRET_KEY is required and cannot be empty. "
                "Generate a strong secret key using: python -c \"import secrets; print(secrets.token_urlsafe(48))\""
            )
        v_clean = v.strip()
        if len(v_clean) < 32:
            raise ValueError(
                "JWT_SECRET_KEY must be at least 32 characters long. "
                "Generate one using: python -c \"import secrets; print(secrets.token_urlsafe(48))\""
            )
        if v_clean.lower() in OLD_HARDCODED_KEYS or v_clean.lower() in OBVIOUS_PLACEHOLDERS:
            raise ValueError(
                f"JWT_SECRET_KEY '{v_clean}' is insecure and rejected. "
                "Generate a strong random secret key using: python -c \"import secrets; print(secrets.token_urlsafe(48))\""
            )
        return v_clean

    @field_validator("cors_origins")
    @classmethod
    def validate_cors_origins(cls, v: str) -> str:
        origins = [o.strip() for o in v.split(",") if o.strip()]
        if "*" in origins or v.strip() == "*":
            raise ValueError("CORS_ORIGINS cannot contain wildcard '*'. Explicit allowed origins are required.")
        return v

    @property
    def cors_origin_list(self) -> List[str]:
        """Expose CORS origins as a list of cleaned URLs."""
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    """Return cached application settings."""
    return Settings()
