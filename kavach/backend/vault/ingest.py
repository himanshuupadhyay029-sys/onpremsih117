"""ingest.py — Knowledge Vault ingestion: chunk -> embed -> FAISS.

Handles clean text-extractable documents (.txt, .md, .pdf with text layers)
as well as image-based documents (.png, .jpg, .jpeg, .tiff, .bmp, and scanned PDFs)
via OCR preprocessing (Phase 7 extension).

Text extraction flow:
- .txt / .md: direct UTF-8 file read.
- .pdf with text layer: fast pypdf extraction (skips OCR).
- Scanned .pdf / raw images: runs through backend/tools/ocr.py to extract text.
- Extracted text is then chunked and embedded via nomic-embed-text into FAISS.
"""

import json
from pathlib import Path
import threading
from typing import Dict, List, Union

import faiss
import numpy as np

from backend import config
from backend.audit.logbook import log_event
from backend.engine import ollama, registry

_lock = threading.Lock()

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".tiff", ".bmp"}
SUPPORTED_EXTENSIONS = {".txt", ".md", ".pdf"} | IMAGE_EXTENSIONS

INDEX_PATH = config.FAISS_INDEX_DIR / "index.faiss"
METADATA_PATH = config.FAISS_INDEX_DIR / "metadata.json"

CHUNK_SIZE = 500
CHUNK_OVERLAP = 50


def _extract_text(file_path: Path) -> str:
    suffix = file_path.suffix.lower()
    if suffix in (".txt", ".md"):
        return file_path.read_text(encoding="utf-8", errors="ignore")
    if suffix == ".pdf":
        from pypdf import PdfReader

        try:
            reader = PdfReader(str(file_path))
            pdf_text = "\n".join((page.extract_text() or "") for page in reader.pages)
            if len(pdf_text.strip()) > 30:
                return pdf_text
        except Exception:
            pass

        # Image-only or scanned PDF: run OCR
        from backend.tools.ocr import extract_text as ocr_extract_text
        res = ocr_extract_text(file_path)
        return res.get("text", "")

    if suffix in IMAGE_EXTENSIONS:
        from backend.tools.ocr import extract_text as ocr_extract_text
        res = ocr_extract_text(file_path)
        return res.get("text", "")

    raise ValueError(f"Unsupported file type: {suffix} (supported: {sorted(SUPPORTED_EXTENSIONS)})")


def _chunk_text(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> List[str]:
    """Word-boundary chunking: builds ~chunk_size-char chunks by whole words,
    carrying the last ~overlap chars of words forward into the next chunk so
    sentences spanning a boundary aren't cut off with no context."""
    words = text.split()
    if not words:
        return []

    chunks: List[str] = []
    current: List[str] = []
    current_len = 0

    for word in words:
        current.append(word)
        current_len += len(word) + 1
        if current_len >= chunk_size:
            chunks.append(" ".join(current))
            overlap_words: List[str] = []
            overlap_len = 0
            for w in reversed(current):
                overlap_len += len(w) + 1
                overlap_words.insert(0, w)
                if overlap_len >= overlap:
                    break
            current = overlap_words
            current_len = overlap_len
            current_len = overlap_len

    if current:
        chunks.append(" ".join(current))

    return chunks


def _load_index_and_metadata():
    if INDEX_PATH.exists() and METADATA_PATH.exists():
        index = faiss.read_index(str(INDEX_PATH))
        with open(METADATA_PATH, "r", encoding="utf-8") as f:
            metadata = json.load(f)
        return index, metadata
    return None, []


def _save_index_and_metadata(index, metadata: List[Dict]) -> None:
    config.FAISS_INDEX_DIR.mkdir(parents=True, exist_ok=True)
    faiss.write_index(index, str(INDEX_PATH))
    with open(METADATA_PATH, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)


def ingest_document(file_path: Union[str, Path]) -> Dict:
    """Chunks, embeds, and adds one document's vectors to the persisted vault index."""
    file_path = Path(file_path)
    if file_path.suffix.lower() not in SUPPORTED_EXTENSIONS:
        raise ValueError(
            f"Unsupported file type: {file_path.suffix} (supported: {sorted(SUPPORTED_EXTENSIONS)})"
        )

    text = _extract_text(file_path)
    chunks = _chunk_text(text)

    if not chunks:
        log_event(
            event_type="ingest",
            actor="vault",
            summary=f"Ingested '{file_path.name}': 0 chunks (no extractable text)",
            metadata={"source_filename": file_path.name, "chunk_count": 0},
            external_calls=0,
        )
        return {"source_filename": file_path.name, "chunk_count": 0}

    embed_model = registry.get_model("embedding")
    vectors = [ollama.embed(embed_model, chunk) for chunk in chunks]
    dim = len(vectors[0])

    with _lock:
        index, metadata = _load_index_and_metadata()
        if index is None:
            index = faiss.IndexFlatL2(dim)
        elif index.d != dim:
            raise ValueError(
                f"Embedding dimension mismatch: existing index is {index.d}-dim, "
                f"new vectors are {dim}-dim. Was the embedding model changed?"
            )

        vectors_np = np.array(vectors, dtype="float32")
        index.add(vectors_np)

        for i, chunk in enumerate(chunks):
            metadata.append(
                {
                    "source_filename": file_path.name,
                    "chunk_text": chunk,
                    "chunk_index": i,
                }
            )

        _save_index_and_metadata(index, metadata)

    log_event(
        event_type="ingest",
        actor="vault",
        summary=f"Ingested '{file_path.name}': {len(chunks)} chunks added to vault",
        metadata={"source_filename": file_path.name, "chunk_count": len(chunks)},
        external_calls=0,
    )

    return {"source_filename": file_path.name, "chunk_count": len(chunks)}


def ingest_directory(dir_path: Union[str, Path]) -> List[Dict]:
    """Ingests every supported file directly inside a folder (non-recursive)."""
    dir_path = Path(dir_path)
    results = []
    for file_path in sorted(dir_path.iterdir()):
        if file_path.is_file() and file_path.suffix.lower() in SUPPORTED_EXTENSIONS:
            results.append(ingest_document(file_path))
    return results
