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


# ──────────────────────────────────────────────────────────────────────────
# Cloud deployment flags
# Default to local/off — only activated when env vars are set on Render
# ──────────────────────────────────────────────────────────────────────────
LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "ollama")  # "ollama" | "huggingface"
CLOUD_DEPLOYMENT = os.environ.get("CLOUD_DEPLOYMENT", "false").lower() == "true"
ENABLE_DOCKER_SANDBOX = os.environ.get("ENABLE_DOCKER_SANDBOX", "true").lower() == "true"

# ──────────────────────────────────────────────────────────────────────────
# Hugging Face token pools — 3 tokens per role, for rotation on 429/503
# Pattern: HF_{ROLE}_API_KEY_{SLOT}  where SLOT = PRIMARY | FALLBACK_1 | FALLBACK_2
# ──────────────────────────────────────────────────────────────────────────
def _load_hf_keys(role: str) -> list[str]:
    """Returns non-empty tokens for this role in [primary, fb1, fb2] order."""
    return [
        v for s in ["PRIMARY", "FALLBACK_1", "FALLBACK_2"]
        if (v := os.environ.get(f"HF_{role.upper()}_API_KEY_{s}", "").strip())
    ]

HF_KEYS: dict[str, list[str]] = {
    "reasoning": _load_hf_keys("REASONING"),
    "code":      _load_hf_keys("CODE"),
    "vision":    _load_hf_keys("VISION"),
    "embedding": _load_hf_keys("EMBEDDING"),
    "rerank":    _load_hf_keys("RERANK"),   # dedicated pool — 3 separate accounts
}

# ──────────────────────────────────────────────────────────────────────────
# Hugging Face model IDs (HF Hub format — NOT Ollama tags)
# Override via env var without code changes
# ──────────────────────────────────────────────────────────────────────────
HF_MODELS: dict[str, str] = {
    "reasoning": os.environ.get("HF_MODEL_REASONING", "Qwen/Qwen2.5-7B-Instruct"),
    "code":      os.environ.get("HF_MODEL_CODE",      "ibm-granite/granite-3.3-8b-instruct"),
    "vision":    os.environ.get("HF_MODEL_VISION",    "Qwen/Qwen2-VL-7B-Instruct"),
    "embedding": os.environ.get("HF_MODEL_EMBEDDING", "nomic-ai/nomic-embed-text-v1.5"),
    "rerank":    os.environ.get("HF_MODEL_RERANK",    "Qwen/Qwen2.5-7B-Instruct"),
}


