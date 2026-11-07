"""Renewal Relay - FastAPI Application Entry Point.

Architectural Guarantees:
- PayPal remains the external payment authority.
- Zero storage of raw card or banking credentials.
- Secrets isolated to backend environment.
- Deterministic policy enforcement for all recovery actions.
- CORS restricted strictly to local frontend development origins.
- Shared, managed httpx.AsyncClient lifecycle tied to application lifespan.
"""

from contextlib import asynccontextmanager
import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
import httpx

from app.core.config import settings
from app.core.logging import setup_logging
from app.core.database import init_db
from app.core.paypal import PayPalAuthManager, PayPalRESTClient
from app.api.v1.api import api_router

# Initialize structured logging with sensitive data redaction
setup_logging()
logger = logging.getLogger("renewal_relay.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan context manager for startup and shutdown events."""
    logger.info("Initializing %s v%s in %s mode...", settings.APP_NAME, settings.APP_VERSION, settings.ENVIRONMENT)

    # 1. Initialize SQLite database schema (preserved)
    init_db()
    logger.info("Database connectivity ready at %s", settings.DATABASE_URL)

    # 2. Initialize application-managed PayPal HTTP client and REST services
    app.state.paypal_http_client = httpx.AsyncClient(
        base_url=settings.PAYPAL_BASE_URL,
        timeout=httpx.Timeout(settings.PAYPAL_TIMEOUT_SECONDS),
        http2=False,
    )
    app.state.paypal_auth_manager = PayPalAuthManager(settings=settings)
    app.state.paypal_client = PayPalRESTClient(
        client=app.state.paypal_http_client,
        auth_manager=app.state.paypal_auth_manager,
        settings=settings,
    )
    logger.info("Initialized managed PayPal REST client bound to %s", settings.PAYPAL_BASE_URL)

    try:
        yield
    finally:
        # 3. Cleanly close managed HTTP connection pool on shutdown, even on unhandled exceptions
        if hasattr(app.state, "paypal_http_client") and app.state.paypal_http_client is not None:
            logger.info("Closing managed PayPal HTTP client...")
            await app.state.paypal_http_client.aclose()
        logger.info("Shutting down %s...", settings.APP_NAME)


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="AI-powered PayPal subscription renewal recovery and merchant intelligence platform (Foundation).",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# Configure CORS strictly for designated local frontend origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "Accept"],
)

# Mount API routers
app.include_router(api_router, prefix="/api/v1")


@app.get("/", include_in_schema=False)
def root():
    """Redirect root path to interactive documentation."""
    return RedirectResponse(url="/docs")


@app.get("/health", include_in_schema=False)
def health_redirect():
    """Redirect legacy root /health path to canonical /api/v1/health."""
    return RedirectResponse(url="/api/v1/health")
