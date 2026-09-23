"""session.py — PostgreSQL database engine and session factory for KAVACH."""

import os
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

raw_db_url = os.environ.get("DATABASE_URL", "").strip().strip("\"'")
if raw_db_url.startswith("DATABASE_URL="):
    raw_db_url = raw_db_url.split("DATABASE_URL=", 1)[1].strip().strip("\"'")

if not raw_db_url:
    raw_db_url = "postgresql://kavach:kavach_secret@127.0.0.1:5434/kavach_db"
elif raw_db_url.startswith("postgres://"):
    raw_db_url = raw_db_url.replace("postgres://", "postgresql://", 1)

DATABASE_URL = raw_db_url

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
