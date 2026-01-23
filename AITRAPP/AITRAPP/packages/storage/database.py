"""Database connection and session management"""
from contextlib import contextmanager
from typing import Generator

import structlog
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, declarative_base, sessionmaker

from packages.core.config import settings

logger = structlog.get_logger(__name__)

# Create declarative base for models
Base = declarative_base()

# Create engine
engine = create_engine(
    settings.database_url,
    pool_size=settings.database_pool_size,
    max_overflow=settings.database_max_overflow,
    echo=settings.debug
)

# Create session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db() -> None:
    """Initialize database (create tables)"""
    logger.info("Initializing database")
    Base.metadata.create_all(bind=engine)
    logger.info("Database initialized")


def get_db() -> Generator[Session, None, None]:
    """Get database session (for FastAPI dependency injection)"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def get_db_session() -> Generator[Session, None, None]:
    """Get database session (context manager)"""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error("Database session error", error=str(e))
        raise
    finally:
        db.close()


def order_exists(client_order_id: str, status_in: tuple = None) -> bool:
    """Check if an order with given client_order_id exists (for idempotency)"""
    from packages.storage.models import Order, OrderStatusEnum

    db = SessionLocal()
    try:
        query = db.query(Order).filter_by(client_order_id=client_order_id)
        if status_in:
            status_enums = [OrderStatusEnum(s) for s in status_in]
            query = query.filter(Order.status.in_(status_enums))
        return query.first() is not None
    finally:
        db.close()

