from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from printing_queue.config.settings import settings

engine = create_engine(settings.DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


def get_db():
    """Dependency de FastAPI para obtener una sesión de BD.

    Yields:
        Session: Sesión SQLAlchemy.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

