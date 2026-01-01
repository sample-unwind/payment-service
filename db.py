"""
Database Configuration and Session Management

Provides SQLAlchemy engine, session management, and database utilities.
Implements multitenancy via PostgreSQL RLS (Row-Level Security).

RLS Implementation:
- Each request MUST set `app.tenant_id` session variable before queries
- PostgreSQL RLS policies filter data based on this variable
- This provides database-level tenant isolation (defense in depth)

GLOBAL RULE: tenant_id MUST ALWAYS be set before any database operation.
Default tenant ID: 00000000-0000-0000-0000-000000000001
"""

import logging
import os
from collections.abc import Generator
from contextlib import contextmanager
from uuid import UUID

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from models import Base

# Set up logging
logger = logging.getLogger(__name__)

# Default tenant ID for development and single-tenant production
DEFAULT_TENANT_ID = "00000000-0000-0000-0000-000000000001"

# Database URL from environment variable
DATABASE_URL = os.getenv("DATABASE_URL")

# Allow running without database for health checks during startup
_engine = None
_SessionLocal = None


def _get_engine():
    """Get or create the database engine."""
    global _engine
    if _engine is None:
        if not DATABASE_URL:
            raise RuntimeError(
                "DATABASE_URL environment variable is required. "
                "Example: postgresql://user:password@localhost:5432/payment_db"
            )
        _engine = create_engine(
            DATABASE_URL,
            pool_pre_ping=True,
            pool_size=5,
            max_overflow=10,
            echo=os.getenv("SQL_DEBUG", "false").lower() == "true",
        )
    return _engine


def _get_session_local():
    """Get or create the session factory."""
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(
            autocommit=False,
            autoflush=False,
            bind=_get_engine(),
            expire_on_commit=False,
        )
    return _SessionLocal


def get_db() -> Generator[Session, None, None]:
    """
    Dependency for FastAPI to get database session.

    Yields:
        Session: SQLAlchemy database session
    """
    SessionLocal = _get_session_local()
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def get_db_context() -> Generator[Session, None, None]:
    """
    Context manager for database session.

    Usage:
        with get_db_context() as db:
            db.query(PaymentModel).all()
    """
    SessionLocal = _get_session_local()
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


@contextmanager
def get_db_context_with_tenant(
    tenant_id: str | UUID | None = None,
) -> Generator[Session, None, None]:
    """
    Context manager for database session with tenant_id set for RLS.

    GLOBAL RULE: This should be used for all database operations.
    If tenant_id is None, uses DEFAULT_TENANT_ID.

    Usage:
        with get_db_context_with_tenant(tenant_id) as db:
            db.query(PaymentModel).all()
    """
    SessionLocal = _get_session_local()
    db = SessionLocal()
    try:
        # GLOBAL RULE: Always set tenant_id
        effective_tenant_id = tenant_id or DEFAULT_TENANT_ID
        set_tenant_id(db, effective_tenant_id)
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def set_tenant_id(session: Session, tenant_id: str | UUID) -> None:
    """
    Set the current tenant ID for RLS (Row-Level Security).

    This sets a PostgreSQL session variable that RLS policies use
    to filter data by tenant. MUST be called before any queries
    in a multi-tenant context.

    GLOBAL RULE: This MUST be called before any database operation.
    Without it, RLS policies will block all access.

    For non-PostgreSQL databases (e.g., SQLite in tests), this is a no-op
    since those databases don't support RLS.

    Args:
        session: SQLAlchemy session
        tenant_id: UUID string or UUID object of the tenant

    Raises:
        ValueError: If tenant_id is invalid
    """
    if tenant_id is None:
        logger.warning("Attempted to set None tenant_id - using default")
        tenant_id = DEFAULT_TENANT_ID

    # Convert UUID to string if needed
    tenant_id_str = str(tenant_id)

    # Validate UUID format to prevent SQL injection
    try:
        UUID(tenant_id_str)
    except (ValueError, TypeError) as e:
        logger.error(f"Invalid tenant_id format: {tenant_id_str}")
        raise ValueError(f"Invalid tenant_id format: {tenant_id_str}") from e

    # Only set RLS variable for PostgreSQL
    try:
        session.execute(text(f"SET app.tenant_id = '{tenant_id_str}'"))
        logger.debug(f"RLS tenant_id set to: {tenant_id_str}")
    except Exception as e:
        # Non-PostgreSQL databases will fail - that's OK for testing
        logger.debug(f"Could not set RLS tenant_id (non-PostgreSQL?): {e}")


def init_db() -> None:
    """
    Initialize database tables.

    Creates all tables defined in models if they don't exist.
    """
    if not DATABASE_URL:
        logger.warning(
            "DATABASE_URL not set - skipping database initialization. "
            "Tables must be created manually or via init.sql."
        )
        return

    try:
        logger.info("Creating database tables...")
        engine = _get_engine()
        Base.metadata.create_all(bind=engine)
        logger.info("Database tables created successfully")
    except Exception as e:
        logger.error(f"Failed to create database tables: {e}")
        logger.warning(
            "Continuing without table creation - "
            "tables may need to be created manually"
        )


def check_db_connection() -> bool:
    """
    Check if database connection is healthy.

    Returns:
        bool: True if connection is healthy, False otherwise
    """
    if not DATABASE_URL:
        logger.warning("DATABASE_URL not set - database check skipped")
        return False

    try:
        with get_db_context() as db:
            db.execute(text("SELECT 1"))
        return True
    except Exception as e:
        logger.error(f"Database connection check failed: {e}")
        return False
