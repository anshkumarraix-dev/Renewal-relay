"""Renewal Relay - FastAPI Application Entry Point.

Architectural Guarantees:
- PayPal remains the external payment authority.
- Zero storage of raw card or banking credentials.
- Secrets isolated to backend environment.
- Deterministic policy enforcement for all recovery actions.
- CORS restricted strictly to local frontend development origins.
"""

from contextlib import asynccontextmanager
import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse

from app.core.config import settings
from app.core.logging import setup_logging
from app.core.database import init_db
from app.api.v1.api import api_router

# Initialize structured logging with sensitive data redaction
setup_logging()
logger = logging.getLogger("renewal_relay.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan context manager for startup and shutdown events."""
    logger.info("Initializing %s v%s in %s mode...", settings.APP_NAME, settings.APP_VERSION, settings.ENVIRONMENT)
    # Initialize SQLite database schema
    init_db()
    logger.info("Database connectivity ready at %s", settings.DATABASE_URL)
    yield
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
