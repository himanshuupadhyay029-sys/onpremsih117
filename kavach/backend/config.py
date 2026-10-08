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

try:
    from dotenv import load_dotenv
    load_dotenv(PROJECT_ROOT / ".env")
except ImportError:
    pass

AUTO_LOGIN_SUPERADMIN = os.environ.get("AUTO_LOGIN_SUPERADMIN", "true").strip().lower() not in ("false", "0", "no")

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
# On Windows, using 127.0.0.1 avoids the 2-3s IPv6 ::1 lookup timeout caused by 'localhost'
_raw_ollama_url = os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
if "localhost" in _raw_ollama_url:
    _raw_ollama_url = _raw_ollama_url.replace("localhost", "127.0.0.1")
OLLAMA_BASE_URL = _raw_ollama_url


# ──────────────────────────────────────────────────────────────────────────
# Cloud deployment flags
# Default to local/off — only activated when env vars are set on Render
# ──────────────────────────────────────────────────────────────────────────
LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "ollama")  # "ollama" | "huggingface"
CLOUD_DEPLOYMENT = os.environ.get("CLOUD_DEPLOYMENT", "false").lower() == "true"
ENABLE_DOCKER_SANDBOX = os.environ.get("ENABLE_DOCKER_SANDBOX", "false").lower() == "true"

# ──────────────────────────────────────────────────────────────────────────
# Hugging Face token pools — robust auto-discovery for all token naming formats
# ──────────────────────────────────────────────────────────────────────────
def _load_hf_keys(role: str) -> list[str]:
    """Returns deduplicated non-empty tokens for this role from any standard or custom env var."""
    keys: list[str] = []
    role_u = role.upper()

    # 1. Role-specific slotted keys (e.g. HF_REASONING_API_KEY_PRIMARY, FALLBACK_1..10)
    for s in ["PRIMARY", "FALLBACK_1", "FALLBACK_2", "FALLBACK_3", "FALLBACK_4", "FALLBACK_5", "1", "2", "3", "4", "5"]:
        for prefix in [f"HF_{role_u}_API_KEY", f"HF_{role_u}_KEY", f"HF_{role_u}_TOKEN"]:
            if (v := os.environ.get(f"{prefix}_{s}", "").strip()) and v not in keys:
                keys.append(v)
            if (v := os.environ.get(f"{prefix}{s}", "").strip()) and v not in keys:
                keys.append(v)

    # 2. Role-specific direct key
    for k_name in [f"HF_{role_u}_API_KEY", f"HF_{role_u}_KEY", f"HF_{role_u}_TOKEN"]:
        if (v := os.environ.get(k_name, "").strip()) and v not in keys:
            keys.append(v)

    # 3. Generic numbered tokens (HF_TOKEN_1 .. HF_TOKEN_25, HF_API_KEY_1 .. HF_API_KEY_25)
    for i in range(1, 26):
        for pattern in [f"HF_TOKEN_{i}", f"HF_API_KEY_{i}", f"HF_KEY_{i}", f"HUGGINGFACE_TOKEN_{i}", f"HF_TOKEN{i}"]:
            if (v := os.environ.get(pattern, "").strip()) and v not in keys:
                keys.append(v)

    # 4. Generic single tokens
    for k_name in ["HF_TOKEN", "HUGGINGFACE_TOKEN", "HF_API_KEY", "HUGGING_FACE_HUB_TOKEN", "HF_AUTH_TOKEN", "HF_API_TOKEN"]:
        if (v := os.environ.get(k_name, "").strip()) and v not in keys:
            keys.append(v)

    # 5. Delimited token lists
    for k_name in ["HF_TOKENS", "HF_API_KEYS", "HUGGINGFACE_TOKENS"]:
        if raw := os.environ.get(k_name, "").strip():
            for item in raw.replace(";", ",").replace("\n", ",").split(","):
                if (clean := item.strip()) and clean not in keys:
                    keys.append(clean)

    return keys

HF_KEYS: dict[str, list[str]] = {
    "reasoning": _load_hf_keys("REASONING"),
    "code":      _load_hf_keys("CODE"),
    "vision":    _load_hf_keys("VISION"),
    "embedding": _load_hf_keys("EMBEDDING"),
    "rerank":    _load_hf_keys("RERANK"),
}

# ──────────────────────────────────────────────────────────────────────────
# Hugging Face model IDs (HF Hub format — validated for HF Serverless Router)
# ──────────────────────────────────────────────────────────────────────────
HF_MODELS: dict[str, str] = {
    "reasoning": os.environ.get("HF_MODEL_REASONING", "meta-llama/Llama-3.2-3B-Instruct"),
    "code":      os.environ.get("HF_MODEL_CODE",      "ibm-granite/granite-3.3-8b-instruct"),
    "vision":    os.environ.get("HF_MODEL_VISION",    "Qwen/Qwen2-VL-7B-Instruct"),
    "embedding": os.environ.get("HF_MODEL_EMBEDDING", "nomic-ai/nomic-embed-text-v1.5"),
    "rerank":    os.environ.get("HF_MODEL_RERANK",    "meta-llama/Llama-3.2-3B-Instruct"),
}


