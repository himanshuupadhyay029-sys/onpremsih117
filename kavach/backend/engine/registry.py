"""registry.py — Model registry with runtime hot-swapping."""

import json
import threading
from typing import Dict

from backend import config

_lock = threading.Lock()


def load_registry() -> Dict[str, str]:
    """Loads current model specialist mapping from models.json."""
    if not config.MODELS_JSON_PATH.exists():
        raise FileNotFoundError(f"models.json not found at {config.MODELS_JSON_PATH}")
    with _lock:
        with open(config.MODELS_JSON_PATH, "r", encoding="utf-8") as f:
            return json.load(f)


def get_model(role: str) -> str:
    """Returns the model tag assigned to a specific task role."""
    reg = load_registry()
    if role not in reg:
        raise KeyError(f"Role '{role}' not found in model registry. Available roles: {list(reg.keys())}")
    return reg[role]


def set_model(role: str, tag: str) -> Dict[str, str]:
    """Hot-swaps the model tag assigned to a role and persists to models.json safely."""
    with _lock:
        if config.MODELS_JSON_PATH.exists():
            with open(config.MODELS_JSON_PATH, "r", encoding="utf-8") as f:
                reg = json.load(f)
        else:
            reg = {}

        reg[role] = tag

        # Safe atomic write
        tmp_path = config.MODELS_JSON_PATH.with_suffix(".tmp")
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(reg, f, indent=2)
        tmp_path.replace(config.MODELS_JSON_PATH)

        return reg
