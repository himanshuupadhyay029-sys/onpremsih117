"""ground_truth.py — Authoritative reference answer generated from the FULL source document.

The generator receives only the user query and the complete normalized source text.
It never sees the generated answer, retrieved/reranked/packed chunks or citations, so
retrieval misses and answer hallucinations cannot leak into the reference.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List, Optional

from backend import config
from backend.evaluation.schemas import GroundTruthResult
from backend.vault.source_store import load_source_text, save_source_text

# Documents ingested before full-text persistence existed can be re-extracted from the
# stored upload without any model call; image sources would need the vision model.
_REEXTRACTABLE_SUFFIXES = {".txt", ".md", ".pdf", ".docx"}

GROUND_TRUTH_SYSTEM_PROMPT = """You write authoritative reference answers used to evaluate a document question-answering system.
You rely ONLY on the source document provided. You never use outside knowledge and never infer facts the source does not state."""

GROUND_TRUTH_PROMPT = """SOURCE DOCUMENT (complete and authoritative):
<<<
{source}
>>>

QUESTION:
{query}

Write the ideal answer to the QUESTION using ONLY the SOURCE DOCUMENT.
- Identify every fact in the source that is needed to answer the question fully, including exact numbers, names, durations, conditions and steps.
- State those facts directly in concise answer prose (plain sentences, no headings, no citations, no commentary about this task).
- Do not add anything the source does not state.
- If the source does not contain some requested information, say so explicitly in one sentence (e.g. "The source does not specify ...").

IDEAL ANSWER:"""


class SourceUnavailableError(RuntimeError):
    pass


@dataclass
class AuthoritativeSource:
    text: str
    filenames: List[str]
    truncated: bool = False


def _load_one(filename: str, user_id: Optional[str]) -> Optional[str]:
    text = load_source_text(filename, user_id=user_id)
    if text is not None:
        return text
    if Path(filename).suffix.lower() not in _REEXTRACTABLE_SUFFIXES:
        return None
    uploads_dir, _ = config.get_user_vault_dirs(user_id)
    upload_path = uploads_dir / Path(filename).name
    if not upload_path.exists():
        return None
    from backend.vault.ingest import _extract_text

    extracted = _extract_text(upload_path)
    if not extracted.strip():
        return None
    save_source_text(filename, extracted, user_id=user_id)
    return load_source_text(filename, user_id=user_id)


def load_authoritative_source(
    filenames: List[str],
    user_id: Optional[str] = None,
    max_chars: Optional[int] = None,
) -> AuthoritativeSource:
    """Loads the complete normalized text of the documents in the query's resolved source scope."""
    if not filenames:
        raise SourceUnavailableError("No source document is associated with this answer.")
    limit = max_chars if max_chars is not None else config.EVALUATION_MAX_SOURCE_CHARS

    texts: List[str] = []
    missing: List[str] = []
    for name in filenames:
        text = _load_one(name, user_id)
        if text is None or not text.strip():
            missing.append(name)
        else:
            texts.append(text)
    if missing:
        raise SourceUnavailableError(
            f"Full source text is not available for: {', '.join(missing)}. Re-ingest the document to enable evaluation."
        )

    if len(texts) == 1:
        combined = texts[0]
    else:
        combined = "\n\n".join(f"=== Document: {name} ===\n{text}" for name, text in zip(filenames, texts))

    truncated = len(combined) > limit
    if truncated:
        combined = combined[:limit]
    return AuthoritativeSource(text=combined, filenames=list(filenames), truncated=truncated)


def generate_ground_truth(llm, query: str, full_source_document: str) -> GroundTruthResult:
    """Generates the reference answer from the query and the full source only."""
    if not full_source_document or not full_source_document.strip():
        return GroundTruthResult(ground_truth="", status="failed", error="Source document content is unavailable.")
    prompt = GROUND_TRUTH_PROMPT.format(source=full_source_document, query=query.strip())
    try:
        ground_truth = llm.generate(prompt, GROUND_TRUTH_SYSTEM_PROMPT).strip()
    except Exception as exc:
        return GroundTruthResult(ground_truth="", status="failed", error=f"Ground truth generation failed: {exc}")
    if not ground_truth:
        return GroundTruthResult(ground_truth="", status="failed", error="Ground truth model returned an empty answer.")
    return GroundTruthResult(ground_truth=ground_truth, status="ok")


def build_ground_truth(
    llm,
    query: str,
    source_filenames: List[str],
    user_id: Optional[str] = None,
    source_loader: Callable[..., AuthoritativeSource] = load_authoritative_source,
) -> GroundTruthResult:
    try:
        source = source_loader(source_filenames, user_id=user_id)
    except Exception as exc:
        return GroundTruthResult(ground_truth="", status="failed", error=str(exc))
    result = generate_ground_truth(llm, query, source.text)
    result.source_truncated = source.truncated
    return result
