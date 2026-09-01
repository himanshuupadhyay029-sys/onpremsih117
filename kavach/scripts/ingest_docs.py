"""ingest_docs.py — CLI helper to bulk-load a folder of SOPs into the Knowledge Vault.

Usage:
    python scripts/ingest_docs.py <folder_path>
"""

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backend.vault.ingest import ingest_directory


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python scripts/ingest_docs.py <folder_path>")
        sys.exit(1)

    folder = Path(sys.argv[1])
    if not folder.is_dir():
        print(f"Not a directory: {folder}")
        sys.exit(1)

    print(f"Ingesting documents from: {folder}")
    results = ingest_directory(folder)

    if not results:
        print("No supported documents found (.pdf, .txt, .md).")
        return

    total_chunks = sum(r["chunk_count"] for r in results)
    print(f"\nIngested {len(results)} document(s), {total_chunks} chunk(s) total:")
    for r in results:
        print(f"  - {r['source_filename']}: {r['chunk_count']} chunks")


if __name__ == "__main__":
    main()
