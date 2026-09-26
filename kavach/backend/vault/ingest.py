"""ingest.py — Knowledge Vault two-tier hierarchical ingestion:
Parent Sections + Child Chunks -> Dense FAISS + Sparse BM25.

Two-Tier Hierarchy:
- Parent Nodes (1,000–2,000 chars): Complete topical sections or markdown headers.
- Child Chunks (300–500 chars): Granular search units enriched with breadcrumbs.
Dual Indexing:
- Dense vector embeddings via nomic-embed-text into FAISS.
- Sparse inverted index via BM25 Okapi for precise keyword/symbol retrieval.
"""

import json
from pathlib import Path
import re
import threading
from typing import Dict, List, Optional, Tuple, Union


import faiss
import numpy as np

from backend import config
from backend.audit.logbook import log_event
from backend.engine import ollama, registry
from backend.vault.bm25 import BM25Index

_lock = threading.Lock()

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".tiff", ".bmp", ".webp"}
SUPPORTED_EXTENSIONS = {".txt", ".md", ".pdf", ".docx"} | IMAGE_EXTENSIONS

INDEX_PATH = config.FAISS_INDEX_DIR / "index.faiss"
METADATA_PATH = config.FAISS_INDEX_DIR / "metadata.json"
BM25_PATH = config.FAISS_INDEX_DIR / "bm25.json"

CHILD_CHUNK_SIZE = 450
CHILD_CHUNK_OVERLAP = 50
PARENT_MAX_SIZE = 2000


def get_user_paths(user_id: Optional[str] = None):
    """Returns (uploads_dir, faiss_dir, index_path, metadata_path, bm25_path) for user."""
    uploads_dir, faiss_dir = config.get_user_vault_dirs(user_id)
    index_path = faiss_dir / "index.faiss"
    metadata_path = faiss_dir / "metadata.json"
    bm25_path = faiss_dir / "bm25.json"
    return uploads_dir, faiss_dir, index_path, metadata_path, bm25_path



def _extract_text(file_path: Path) -> str:
    suffix = file_path.suffix.lower()
    if suffix in (".txt", ".md"):
        return file_path.read_text(encoding="utf-8", errors="ignore")

    if suffix == ".docx":
        try:
            import docx
            doc = docx.Document(str(file_path))
            return "\n\n".join(p.text for p in doc.paragraphs if p.text.strip())
        except Exception:
            return ""
    if suffix == ".pdf":
        try:
            import pdfplumber
            with pdfplumber.open(str(file_path)) as pdf:
                pages_text = []
                for p in pdf.pages:
                    t = p.extract_text() or ""
                    if t.strip():
                        pages_text.append(t)
                if pages_text:
                    return "\n\n".join(pages_text)
        except Exception:
            pass

        try:
            from pypdf import PdfReader
            reader = PdfReader(str(file_path))
            pdf_text = "\n\n".join((page.extract_text() or "") for page in reader.pages)
            if len(pdf_text.strip()) > 30:
                return pdf_text
        except Exception:
            pass

        # Image-only or scanned PDF fallback: run OCR
        try:
            from backend.tools.ocr import extract_text as ocr_extract_text
            res = ocr_extract_text(file_path)
            extracted = res.get("text", "").strip()
            if extracted:
                return extracted
        except Exception:
            pass
        return ""

    if suffix in IMAGE_EXTENSIONS:
        # Try Tesseract OCR first
        try:
            from backend.tools.ocr import extract_text as ocr_extract_text
            res = ocr_extract_text(file_path)
            extracted = res.get("text", "").strip()
            if extracted:
                return extracted
        except Exception:
            pass

        # Fallback to local vision specialist model if OCR returns empty or fails
        try:
            vision_model = registry.get_model("vision")
            desc = ollama.vision(
                vision_model,
                "Transcribe and summarize all visible text, labels, numbers, dimensions, and diagram content in this image for searchable knowledge indexing.",
                file_path,
            )
            if desc and desc.strip():
                return desc.strip()
        except Exception:
            pass

        return ""

    raise ValueError(f"Unsupported file type: {suffix} (supported: {sorted(SUPPORTED_EXTENSIONS)})")


def _split_into_parent_sections(text: str, filename: str) -> List[Tuple[str, str]]:
    """Splits full document text into topical Parent Sections with descriptive breadcrumbs.

    Returns a list of (breadcrumb, section_text) tuples.
    """
    clean_text = text.replace("\r\n", "\n")
    lines = clean_text.split("\n")

    sections: List[Tuple[str, str]] = []
    current_heading = Path(filename).stem
    current_lines: List[str] = []

    for line in lines:
        header_match = re.match(r"^(#{1,4})\s+(.+)$", line.strip())
        if header_match:
            # If we already accumulated lines, save previous section
            if current_lines:
                sec_text = "\n".join(current_lines).strip()
                if sec_text:
                    sections.append((current_heading, sec_text))
                current_lines = []
            heading_text = header_match.group(2).strip()
            current_heading = f"{Path(filename).stem} > {heading_text}"
            current_lines.append(line)
        else:
            current_lines.append(line)

    if current_lines:
        sec_text = "\n".join(current_lines).strip()
        if sec_text:
            sections.append((current_heading, sec_text))

    # If document had no markdown headers, split by paragraphs / large blocks
    if not sections:
        paragraphs = clean_text.split("\n\n")
        curr_p: List[str] = []
        curr_len = 0
        sec_idx = 1
        for p in paragraphs:
            p_strip = p.strip()
            if not p_strip:
                continue
            curr_p.append(p_strip)
            curr_len += len(p_strip)
            if curr_len >= PARENT_MAX_SIZE:
                sections.append((f"{Path(filename).stem} > Section {sec_idx}", "\n\n".join(curr_p)))
                curr_p = []
                curr_len = 0
                sec_idx += 1
        if curr_p:
            sections.append((f"{Path(filename).stem} > Section {sec_idx}", "\n\n".join(curr_p)))

    if not sections and clean_text.strip():
        sections.append((Path(filename).stem, clean_text.strip()))

    return sections


def _chunk_parent_section(
    section_text: str,
    breadcrumb: str,
    chunk_size: int = CHILD_CHUNK_SIZE,
    overlap: int = CHILD_CHUNK_OVERLAP,
) -> List[str]:
    """Generates granular Child Chunks from a Parent Section."""
    words = section_text.split()
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

    if current:
        chunks.append(" ".join(current))

    return chunks


def _load_all_indices(user_id: Optional[str] = None):
    """Loads FAISS dense index, metadata list, and BM25 sparse index for a user."""
    _, faiss_dir, index_path, metadata_path, bm25_path = get_user_paths(user_id)
    index = None
    metadata: List[Dict] = []
    bm25 = None

    if index_path.exists() and metadata_path.exists():
        try:
            raw_bytes = index_path.read_bytes()
            if raw_bytes:
                index = faiss.deserialize_index(np.frombuffer(raw_bytes, dtype=np.uint8))
                with open(metadata_path, "r", encoding="utf-8") as f:
                    metadata = json.load(f)
        except Exception:
            index = None
            metadata = []

    if bm25_path.exists():
        bm25 = BM25Index.load(bm25_path)

    return index, metadata, bm25


def _save_all_indices(index, metadata: List[Dict], bm25: BM25Index, user_id: Optional[str] = None) -> None:
    """Serializes FAISS, BM25, and metadata for a user."""
    _, faiss_dir, index_path, metadata_path, bm25_path = get_user_paths(user_id)
    faiss_dir.mkdir(parents=True, exist_ok=True)
    if index is not None:
        raw_array = faiss.serialize_index(index)
        index_path.write_bytes(raw_array.tobytes())
    with open(metadata_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)
    bm25.save(bm25_path)


def ingest_document(
    file_path: Union[str, Path],
    user_id: Optional[str] = None,
    department: str = "general",
    classification_level: str = "internal",
) -> Dict:
    """Ingests a single document into Two-Tier Hierarchical FAISS + BM25 indices for a user.
    
    Also records metadata (department, classification_level) in the documents table.
    """
    file_path = Path(file_path)
    if file_path.suffix.lower() not in SUPPORTED_EXTENSIONS:
        raise ValueError(
            f"Unsupported file type: {file_path.suffix} (supported: {sorted(SUPPORTED_EXTENSIONS)})"
        )

    text = _extract_text(file_path)
    if not text.strip():
        log_event(
            event_type="ingest",
            actor="vault",
            summary=f"Ingested '{file_path.name}': 0 chunks (no extractable text)",
            metadata={"source_filename": file_path.name, "chunk_count": 0},
            external_calls=0,
            user_id=user_id,
        )
        return {"source_filename": file_path.name, "chunk_count": 0}

    # 1. Two-Tier Hierarchical Decomposition
    parent_sections = _split_into_parent_sections(text, file_path.name)
    all_new_child_entries: List[Dict] = []
    child_texts_to_embed: List[str] = []

    doc_slug = re.sub(r"[^a-zA-Z0-9]+", "_", file_path.stem).lower()[:20]

    global_c_idx = 0
    for p_idx, (breadcrumb, p_text) in enumerate(parent_sections):
        parent_id = f"{doc_slug}_p{p_idx}"
        child_chunks = _chunk_parent_section(p_text, breadcrumb)

        for c_text in child_chunks:
            chunk_id = f"{doc_slug}_c{global_c_idx}"
            all_new_child_entries.append(
                {
                    "chunk_id": chunk_id,
                    "parent_id": parent_id,
                    "parent_text": p_text,
                    "chunk_text": c_text,
                    "breadcrumb": breadcrumb,
                    "source_filename": file_path.name,
                    "chunk_index": global_c_idx,
                }
            )
            child_texts_to_embed.append(c_text)
            global_c_idx += 1

    if not child_texts_to_embed:
        return {"source_filename": file_path.name, "chunk_count": 0}

    # 2. Compute Dense Vector Embeddings
    embed_model = registry.get_model("embedding")
    try:
        vectors = ollama.embed_batch(embed_model, child_texts_to_embed)
    except Exception:
        vectors = [ollama.embed(embed_model, chunk) for chunk in child_texts_to_embed]

    if not vectors or not vectors[0]:
        raise ValueError(
            f"Could not generate vector embeddings with model '{embed_model}'. "
            "Please ensure the embedding model is running in Ollama (`ollama pull nomic-embed-text:latest`)."
        )
    dim = len(vectors[0])

    with _lock:
        index, metadata, _ = _load_all_indices(user_id=user_id)

        if index is None:
            index = faiss.IndexFlatL2(dim)
        elif index.d != dim:
            raise ValueError(
                f"Embedding dimension mismatch: existing index is {index.d}-dim, "
                f"new vectors are {dim}-dim."
            )

        vectors_np = np.array(vectors, dtype="float32")
        index.add(vectors_np)
        metadata.extend(all_new_child_entries)

        # 3. Build Sparse BM25 Inverted Index across all vault chunks
        all_corpus_texts = [entry.get("chunk_text", "") for entry in metadata]
        bm25 = BM25Index().build(all_corpus_texts)

        _save_all_indices(index, metadata, bm25, user_id=user_id)

    log_event(
        event_type="document_ingested",
        actor="vault",
        summary=f"Hierarchically ingested '{file_path.name}': {len(parent_sections)} parents, {len(all_new_child_entries)} child chunks (dept={department}, class={classification_level})",
        metadata={
            "source_filename": file_path.name,
            "parent_count": len(parent_sections),
            "child_chunk_count": len(all_new_child_entries),
            "department": department,
            "classification_level": classification_level,
        },
        external_calls=0,
        user_id=user_id,
    )

    # Record metadata in documents table for RBAC-scoped retrieval
    try:
        from backend.db.session import SessionLocal
        from backend.db.models import Document
        import uuid as _uuid
        db = SessionLocal()
        try:
            existing = db.query(Document).filter(
                Document.owner_user_id == _uuid.UUID(str(user_id)) if user_id else Document.owner_user_id.is_(None),
                Document.filename == file_path.name,
            ).first()
            if existing:
                existing.department = department
                existing.classification_level = classification_level
            else:
                doc_meta = Document(
                    owner_user_id=_uuid.UUID(str(user_id)) if user_id else _uuid.uuid4(),
                    filename=file_path.name,
                    department=department,
                    classification_level=classification_level,
                )
                db.add(doc_meta)
            db.commit()
        finally:
            db.close()
    except Exception as exc:
        print(f"[Warning] Failed to record document metadata in DB: {exc}", flush=True)

    return {
        "source_filename": file_path.name,
        "parent_count": len(parent_sections),
        "chunk_count": len(all_new_child_entries),
    }


def delete_document(filename: str, user_id: Optional[str] = None) -> Dict:
    """Removes all chunks, vectors, and BM25 index entries for a given document filename,
    and removes the file from disk if present for a user.
    """
    uploads_dir, _, index_path, metadata_path, bm25_path = get_user_paths(user_id)

    with _lock:
        index, metadata, _ = _load_all_indices(user_id=user_id)
        if not metadata:
            return {"success": False, "message": "No documents in index", "deleted_chunks": 0}

        remaining_meta = []
        remaining_indices = []
        deleted_count = 0
        for i, entry in enumerate(metadata):
            if entry.get("source_filename") == filename:
                deleted_count += 1
            else:
                remaining_indices.append(i)
                remaining_meta.append(entry)

        if deleted_count == 0:
            return {"success": False, "message": f"Document '{filename}' not found in index", "deleted_chunks": 0}

        if not remaining_meta:
            if index_path.exists():
                index_path.unlink()
            if metadata_path.exists():
                metadata_path.unlink()
            if bm25_path.exists():
                bm25_path.unlink()
        else:
            child_texts = [entry.get("chunk_text", "") for entry in remaining_meta]

            if index is not None and index.ntotal == len(metadata) and remaining_indices:
                # FAST: Reconstruct vectors directly from the existing FAISS index in memory (<1ms)
                remaining_vectors = np.array([index.reconstruct(int(i)) for i in remaining_indices], dtype="float32")
                dim = index.d
                new_index = faiss.IndexFlatL2(dim)
                new_index.add(remaining_vectors)
            else:
                # Fallback only if index was missing or desynchronized
                embed_model = registry.get_model("embedding")
                try:
                    vectors = ollama.embed_batch(embed_model, child_texts)
                except Exception:
                    vectors = [ollama.embed(embed_model, chunk) for chunk in child_texts]

                dim = len(vectors[0])
                new_index = faiss.IndexFlatL2(dim)
                vectors_np = np.array(vectors, dtype="float32")
                new_index.add(vectors_np)

            new_bm25 = BM25Index().build(child_texts)

            for i, entry in enumerate(remaining_meta):
                entry["chunk_index"] = i

            _save_all_indices(new_index, remaining_meta, new_bm25, user_id=user_id)

        # Delete physical file from user uploads if present
        upload_file = uploads_dir / filename
        if upload_file.exists():
            try:
                upload_file.unlink()
            except Exception:
                pass

        log_event(
            event_type="delete",
            actor="vault",
            summary=f"Deleted document '{filename}' ({deleted_count} chunks removed)",
            metadata={"source_filename": filename, "deleted_chunks": deleted_count},
            external_calls=0,
            user_id=user_id,
        )

        return {
            "success": True,
            "filename": filename,
            "deleted_chunks": deleted_count,
            "remaining_documents": len({e.get("source_filename") for e in remaining_meta}),
        }


def ingest_directory(dir_path: Union[str, Path], user_id: Optional[str] = None) -> List[Dict]:
    """Ingests every supported file directly inside a folder (non-recursive)."""
    dir_path = Path(dir_path)
    results = []
    for file_path in sorted(dir_path.iterdir()):
        if file_path.is_file() and file_path.suffix.lower() in SUPPORTED_EXTENSIONS:
            results.append(ingest_document(file_path, user_id=user_id))
    return results

