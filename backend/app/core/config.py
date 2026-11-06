"""Configuration management for Renewal Relay using Pydantic Settings.

Ensures safe defaults, secure credential isolation, and strict policy boundaries.
"""

from typing import List
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables and .env file."""

    # Application
    APP_NAME: str = "Renewal Relay Backend"
    APP_VERSION: str = "0.1.0"
    ENVIRONMENT: str = "development"
    DEBUG: bool = True
    LOG_LEVEL: str = "INFO"

    # Server Bindings
    HOST: str = "127.0.0.1"
    PORT: int = 8000

    # CORS Settings (Restricted to local development origins; no wildcards with credentials)
    CORS_ORIGINS: List[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]

    # Database
    DATABASE_URL: str = "sqlite:///./renewal_relay.db"

    # PayPal Configuration (Strictly Sandbox for development/testing)
    PAYPAL_MODE: str = "sandbox"
    PAYPAL_CLIENT_ID: str = Field(default="", description="PayPal REST Client ID")
    PAYPAL_CLIENT_SECRET: str = Field(default="", description="PayPal REST Client Secret")
    PAYPAL_WEBHOOK_ID: str = Field(default="", description="PayPal Webhook ID")

    # Governance & Architectural Boundaries
    # AI cannot independently authorize payment execution; policy checks must be deterministic
    ENFORCE_DETERMINISTIC_POLICY: bool = True
    ALLOW_AI_AUTONOMOUS_PAYMENT: bool = False

    @field_validator("PAYPAL_MODE")
    @classmethod
    def validate_paypal_mode(cls, v: str) -> str:
        mode = v.lower()
        if mode not in ("sandbox", "live"):
            raise ValueError("PAYPAL_MODE must be either 'sandbox' or 'live'")
        return mode

    @field_validator("CORS_ORIGINS")
    @classmethod
    def validate_cors_origins(cls, v: List[str]) -> List[str]:
        # Ensure no wildcard is allowed in origins list
        for origin in v:
            if origin == "*":
                raise ValueError("Wildcard '*' CORS origin is not permitted when credentials are supported.")
        return v

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=True,
    )

    def sanitized_dict(self) -> dict:
        """Return configuration dictionary with sensitive credentials masked."""
        data = self.model_dump()
        masked_keys = {"PAYPAL_CLIENT_SECRET", "PAYPAL_CLIENT_ID", "PAYPAL_WEBHOOK_ID"}
        for key in masked_keys:
            if data.get(key):
                data[key] = f"***REDACTED (len={len(str(data[key]))})***"
            else:
                data[key] = "[NOT CONFIGURED]"
        return data


settings = Settings()
