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
    """Returns the model tag assigned to a specific task role, with smart fallback."""
    reg = load_registry()
    if role not in reg:
        raise KeyError(f"Role '{role}' not found in model registry. Available roles: {list(reg.keys())}")
    
    target_tag = reg[role]
    from backend.engine import ollama
    try:
        installed = ollama.list_models()
    except Exception:
        return target_tag

    if target_tag in installed:
        return target_tag
        
    if not installed:
        return target_tag

    # Smart fallback heuristics
    if role == "reasoning":
        instructs = [m for m in installed if "instruct" in m.lower() or "chat" in m.lower()]
        return instructs[0] if instructs else installed[0]
    elif role == "code":
        coders = [m for m in installed if "code" in m.lower() or "coder" in m.lower()]
        if coders: return coders[0]
        instructs = [m for m in installed if "instruct" in m.lower() or "chat" in m.lower()]
        return instructs[0] if instructs else installed[0]
    elif role == "embedding":
        embeds = [m for m in installed if "embed" in m.lower()]
        return embeds[0] if embeds else installed[0]
    elif role == "vision":
        visions = [m for m in installed if "vl" in m.lower() or "vision" in m.lower() or "moondream" in m.lower() or "llava" in m.lower()]
        return visions[0] if visions else installed[0]

    return installed[0]


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
