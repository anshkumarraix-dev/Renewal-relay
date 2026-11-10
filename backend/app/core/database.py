"""Database connectivity, engine configuration, and session management.

Supports both SQLite (local development and automated tests) and
PostgreSQL / Supabase (production deployment on Railway / Supabase).
"""

import time
import logging
from typing import Generator, Tuple, Optional
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, declarative_base, Session
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import settings

logger = logging.getLogger(__name__)

# Normalize PostgreSQL URL if provided in Heroku / Supabase 'postgres://' format
raw_db_url = settings.DATABASE_URL
if raw_db_url.startswith("postgres://"):
    database_url = raw_db_url.replace("postgres://", "postgresql://", 1)
else:
    database_url = raw_db_url

# Configure engine arguments based on database dialect
connect_args = {}
engine_kwargs = {
    "pool_pre_ping": True,
    "echo": False,
}

if database_url.startswith("sqlite"):
    connect_args["check_same_thread"] = False
    engine_kwargs["connect_args"] = connect_args
else:
    # PostgreSQL / Supabase pooler settings
    engine_kwargs["pool_size"] = 10
    engine_kwargs["max_overflow"] = 20

engine = create_engine(
    database_url,
    **engine_kwargs,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db() -> Generator[Session, None, None]:
    """Dependency that provides a transactional SQLAlchemy database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def check_database_health(session: Optional[Session] = None) -> Tuple[bool, float, Optional[str]]:
    """Execute a real connectivity check against the database using SQLAlchemy.

    Returns:
        Tuple of (is_connected, latency_ms, error_detail)
    """
    start_time = time.perf_counter()
    own_session = False

    if session is None:
        session = SessionLocal()
        own_session = True

    try:
        result = session.execute(text("SELECT 1")).scalar()
        latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
        if result == 1:
            return True, latency_ms, None
        return False, latency_ms, "Unexpected database query response"
    except SQLAlchemyError as exc:
        latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
        logger.error("Database health check failed: %s", str(exc))
        return False, latency_ms, f"Database error: {exc.__class__.__name__}"
    except Exception as exc:
        latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
        logger.error("Unexpected error during database check: %s", str(exc))
        return False, latency_ms, f"Unexpected error: {str(exc)}"
    finally:
        if own_session:
            session.close()


def init_db() -> None:
    """Initialize all registered database tables."""
    try:
        # Import all models to ensure they are registered with Base.metadata
        import app.models  # noqa: F401
        Base.metadata.create_all(bind=engine)
        logger.info("Database initialized successfully at %s", database_url)
    except Exception as exc:
        logger.error("Failed to initialize database: %s", str(exc))
        raise
