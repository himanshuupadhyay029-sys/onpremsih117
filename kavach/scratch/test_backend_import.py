import sys
from pathlib import Path

root_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root_dir))

print("Python version:", sys.version)

import backend.main
print("Backend main loaded successfully!")

from backend.vault.retrieve import retrieve
print("Retrieve module loaded successfully!")

from backend.vault.ingest import ingest_document
print("Ingest module loaded successfully!")

from backend.tools.search import search
print("Search tool loaded successfully!")

from backend.brain.agent import run_agent
print("Agent module loaded successfully!")

print("\nALL IMPORTS SUCCEEDED WITHOUT ERRORS!")
