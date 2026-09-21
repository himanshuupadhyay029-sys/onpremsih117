import sys
from pathlib import Path
root_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root_dir))

from backend.engine import ollama, registry

print("Embedding model configured:", registry.get_model("embedding"))

try:
    models = ollama.list_models()
    print("Ollama available models:", models)
except Exception as e:
    print("Ollama list_models error:", e)

try:
    from backend.tools.search import search
    res = search("Search KAVACH_CONTEXT (1).md for platform description")
    print("Search result:", res)
except Exception as e:
    import traceback
    print("Search tool EXCEPTION:")
    traceback.print_exc()
