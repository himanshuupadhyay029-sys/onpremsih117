"""session.py — PostgreSQL database engine and session factory for KAVACH."""

import os
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

NEON_CLOUD_URL = "postgresql://neondb_owner:npg_BxoYUp1sjS2K@ep-fancy-dew-azygk21r-pooler.c-3.ap-southeast-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require"


def resolve_database_url() -> str:
    # 1. Fuzzy match by key name
    for k, v in os.environ.items():
        clean_k = k.strip().upper()
        if clean_k in ("DATABASE_URL", "DATABASE_URL_POOLED") or ("DATABASE" in clean_k and "URL" in clean_k):
            val = (v or "").strip().strip("\"'").strip()
            if val.startswith("DATABASE_URL="):
                val = val.split("DATABASE_URL=", 1)[1].strip().strip("\"'")
            if val.startswith("DATABASE_URL_POOLED="):
                val = val.split("DATABASE_URL_POOLED=", 1)[1].strip().strip("\"'")
            if val.startswith("postgres://"):
                val = val.replace("postgres://", "postgresql://", 1)
            if val:
                return val

    # 2. Match any env var value starting with postgresql:// or postgres://
    for k, v in os.environ.items():
        val = (v or "").strip().strip("\"'").strip()
        if val.startswith("postgresql://") or val.startswith("postgres://"):
            if val.startswith("postgres://"):
                val = val.replace("postgres://", "postgresql://", 1)
            return val

    # 3. If running in cloud (Render), fallback directly to Neon cloud DB
    if os.environ.get("RENDER") or os.environ.get("CLOUD_DEPLOYMENT", "").lower() == "true":
        return NEON_CLOUD_URL

    # 4. Local default for development
    return "postgresql://kavach:kavach_secret@127.0.0.1:5434/kavach_db"


DATABASE_URL = resolve_database_url()

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
