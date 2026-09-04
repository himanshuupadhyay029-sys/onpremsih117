"""session.py — PostgreSQL database engine and session factory for KAVACH."""

import os
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://kavach:kavach_secret@127.0.0.1:5433/kavach_db",
)

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    """FastAPI dependency yielding an active database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
