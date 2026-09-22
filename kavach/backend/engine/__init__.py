from backend.engine import prompts, registry
from backend import config

# Dispatch: route all LLM calls to HF (cloud) or Ollama (local)
if config.LLM_PROVIDER == "huggingface":
    from backend.engine import hf_client as active_llm
else:
    from backend.engine import ollama as active_llm

# Keep ollama importable for code that explicitly needs it (on-prem path)
from backend.engine import ollama

__all__ = ["active_llm", "ollama", "prompts", "registry"]
