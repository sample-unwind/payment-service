"""
Database Configuration and Session Management

Provides SQLAlchemy engine, session management, and database utilities.
"""

import logging
import os
from collections.abc import Generator
from contextlib import contextmanager

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from models import Base

# Set up logging
logger = logging.getLogger(__name__)

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
