"""source_store.py — Persists the full normalized text of every ingested document.

Chunks and parent sections in metadata.json are retrieval units; they are not a
faithful copy of the whole document. The evaluation layer needs the complete
authoritative source, so ingestion stores the normalized extracted text here,
partitioned per user exactly like the FAISS/BM25 stores.
"""

from pathlib import Path
from typing import Optional

from backend import config


def normalize_text(text: str) -> str:
    return (text or "").replace("\r\n", "\n").replace("\r", "\n").strip()


def _source_path(filename: str, user_id: Optional[str] = None) -> Path:
    safe_name = Path(filename).name
    return config.get_user_sources_dir(user_id) / f"{safe_name}.txt"


def save_source_text(filename: str, text: str, user_id: Optional[str] = None) -> Path:
    path = _source_path(filename, user_id)
    tmp_path = path.with_name(path.name + ".partial")
    tmp_path.write_text(normalize_text(text), encoding="utf-8")
    tmp_path.replace(path)
    return path


def load_source_text(filename: str, user_id: Optional[str] = None) -> Optional[str]:
    path = _source_path(filename, user_id)
    if not path.exists():
        return None
    return path.read_text(encoding="utf-8")


def delete_source_text(filename: str, user_id: Optional[str] = None) -> None:
    path = _source_path(filename, user_id)
    if path.exists():
        path.unlink()
