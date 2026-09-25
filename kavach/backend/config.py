"""config.py — Central configuration for KAVACH.

All paths and service endpoints are defined here. No model names are hardcoded
in code; all model references are loaded dynamically from models.json.
"""

import os
from pathlib import Path
from typing import Optional, Tuple


# Paths
BACKEND_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BACKEND_DIR.parent

MODELS_JSON_PATH = BACKEND_DIR / "models.json"
KNOWLEDGE_DIR = PROJECT_ROOT / "knowledge"
FAISS_INDEX_DIR = KNOWLEDGE_DIR / "faiss_index"
OUTPUTS_DIR = PROJECT_ROOT / "outputs"
AUDIT_LOG_PATH = OUTPUTS_DIR / "audit_log.jsonl"

# Ensure base runtime directories exist
FAISS_INDEX_DIR.mkdir(parents=True, exist_ok=True)
OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)


def get_user_vault_dirs(user_id: str = None) -> tuple[Path, Path]:
    """Returns (uploads_dir, faiss_index_dir) partitioned by user_id."""
    key = str(user_id).strip() if user_id else "default"
    user_root = KNOWLEDGE_DIR / "users" / key
    uploads_dir = user_root / "uploads"
    faiss_dir = user_root / "faiss_index"
    uploads_dir.mkdir(parents=True, exist_ok=True)
    faiss_dir.mkdir(parents=True, exist_ok=True)
    return uploads_dir, faiss_dir


def get_user_audit_log_path(user_id: str = None) -> Path:
    """Returns the user's isolated audit_log.jsonl path."""
    if not user_id:
        return AUDIT_LOG_PATH
    key = str(user_id).strip()
    user_out = OUTPUTS_DIR / "users" / key
    user_out.mkdir(parents=True, exist_ok=True)
    return user_out / "audit_log.jsonl"


# Local Ollama endpoint (strictly offline/local)
OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")


def get_user_sources_dir(user_id: str = None) -> Path:
    """Returns the user's directory of normalized full-document texts persisted at ingestion."""
    key = str(user_id).strip() if user_id else "default"
    sources_dir = KNOWLEDGE_DIR / "users" / key / "sources"
    sources_dir.mkdir(parents=True, exist_ok=True)
    return sources_dir


# RAG evaluation layer (single master toggle; everything else has safe defaults)
ENABLE_EVALUATION = os.environ.get("ENABLE_EVALUATION", "false").strip().lower() in {"1", "true", "yes", "on"}
# Comma-separated bearer keys for an authenticated on-prem model gateway. Empty = keyless local Ollama.
EVALUATION_API_KEYS = [k.strip() for k in os.environ.get("EVALUATION_API_KEYS", "").split(",") if k.strip()]
EVALUATION_KEY_COOLDOWN_SECONDS = float(os.environ.get("EVALUATION_KEY_COOLDOWN_SECONDS", "30"))
EVALUATION_MAX_RETRIES = int(os.environ.get("EVALUATION_MAX_RETRIES", "3"))
EVALUATION_NUM_CTX = int(os.environ.get("EVALUATION_NUM_CTX", "16384"))
EVALUATION_MAX_SOURCE_CHARS = int(os.environ.get("EVALUATION_MAX_SOURCE_CHARS", "48000"))

