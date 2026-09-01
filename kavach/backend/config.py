"""config.py — Central configuration for KAVACH.

All paths and service endpoints are defined here. No model names are hardcoded
in code; all model references are loaded dynamically from models.json.
"""

import os
from pathlib import Path

# Paths
BACKEND_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BACKEND_DIR.parent

MODELS_JSON_PATH = BACKEND_DIR / "models.json"
FAISS_INDEX_DIR = PROJECT_ROOT / "knowledge" / "faiss_index"
OUTPUTS_DIR = PROJECT_ROOT / "outputs"
AUDIT_LOG_PATH = OUTPUTS_DIR / "audit_log.jsonl"

# Ensure runtime directories exist
FAISS_INDEX_DIR.mkdir(parents=True, exist_ok=True)
OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)

# Local Ollama endpoint (strictly offline/local)
OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
