"""Configuration management for Renewal Relay using Pydantic Settings.

Ensures safe defaults, secure credential isolation, strict sandbox enforcement, and policy boundaries.
"""

from typing import List
from urllib.parse import urlsplit
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def validate_sandbox_url(url: str) -> str:
    """Strictly validate that the PayPal base URL matches the official sandbox endpoint.

    Rejects non-HTTPS schemes, embedded credentials, non-sandbox hostnames,
    unexpected/malformed ports, non-empty paths, queries, and fragments.
    """
    try:
        parsed = urlsplit(url)
    except Exception as exc:
        raise ValueError(f"Malformed PayPal base URL: {exc}") from exc

    if parsed.scheme != "https":
        raise ValueError(f"PayPal base URL must use HTTPS scheme; got: '{parsed.scheme}'")

    if parsed.username or parsed.password:
        raise ValueError("Embedded credentials in PayPal base URL are strictly prohibited.")

    if parsed.hostname != "api-m.sandbox.paypal.com":
        raise ValueError(
            f"PayPal base URL host must be exactly 'api-m.sandbox.paypal.com'; got: '{parsed.hostname}'. "
            "Live endpoints and alternate hosts are strictly prohibited."
        )

    try:
        port = parsed.port
    except ValueError as exc:
        raise ValueError(f"Malformed port in PayPal base URL: {exc}") from exc

    if port is not None and port != 443:
        raise ValueError(f"Unexpected port in PayPal base URL: {port}. Only standard HTTPS (443) is permitted.")

    if parsed.path not in ("", "/"):
        raise ValueError(f"PayPal base URL must not contain a path component; got: '{parsed.path}'")

    if parsed.query or parsed.fragment:
        raise ValueError("PayPal base URL must not contain query parameters or fragments.")

    return f"https://{parsed.hostname}"


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
    PAYPAL_BASE_URL: str = "https://api-m.sandbox.paypal.com"
    PAYPAL_CLIENT_ID: str = Field(default="", description="PayPal REST Client ID")
    PAYPAL_CLIENT_SECRET: str = Field(default="", description="PayPal REST Client Secret")
    PAYPAL_WEBHOOK_ID: str = Field(default="", description="PayPal Webhook ID")

    # PayPal Client Resilience & Token Settings
    PAYPAL_TOKEN_SAFETY_MARGIN_SECONDS: int = 120
    PAYPAL_TIMEOUT_SECONDS: float = 15.0
    PAYPAL_MAX_RETRIES: int = 3
    PAYPAL_MAX_RETRY_AFTER_SECONDS: float = 10.0
    PAYPAL_BACKOFF_FACTOR: float = 0.5

    # Governance & Architectural Boundaries
    # AI cannot independently authorize payment execution; policy checks must be deterministic
    ENFORCE_DETERMINISTIC_POLICY: bool = True
    ALLOW_AI_AUTONOMOUS_PAYMENT: bool = False

    @field_validator("PAYPAL_MODE")
    @classmethod
    def validate_paypal_mode(cls, v: str) -> str:
        mode = v.strip().lower()
        if mode != "sandbox":
            raise ValueError(f"PAYPAL_MODE must be 'sandbox'; got '{v}'. Live mode is strictly prohibited.")
        return mode

    @field_validator("PAYPAL_BASE_URL")
    @classmethod
    def validate_paypal_base_url(cls, v: str) -> str:
        return validate_sandbox_url(v)

    @field_validator("PAYPAL_TOKEN_SAFETY_MARGIN_SECONDS")
    @classmethod
    def validate_safety_margin(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("PAYPAL_TOKEN_SAFETY_MARGIN_SECONDS must be strictly positive (> 0).")
        return v

    @field_validator("PAYPAL_TIMEOUT_SECONDS")
    @classmethod
    def validate_timeout(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("PAYPAL_TIMEOUT_SECONDS must be strictly positive (> 0).")
        return v

    @field_validator("PAYPAL_MAX_RETRIES")
    @classmethod
    def validate_max_retries(cls, v: int) -> int:
        if v < 0:
            raise ValueError("PAYPAL_MAX_RETRIES must be non-negative (>= 0).")
        return v

    @field_validator("PAYPAL_MAX_RETRY_AFTER_SECONDS")
    @classmethod
    def validate_max_retry_after(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("PAYPAL_MAX_RETRY_AFTER_SECONDS must be strictly positive (> 0).")
        return v

    @field_validator("PAYPAL_BACKOFF_FACTOR")
    @classmethod
    def validate_backoff_factor(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("PAYPAL_BACKOFF_FACTOR must be strictly positive (> 0).")
        return v

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
