"""rerank.py — Resilient Neural & Hybrid Cross-Scorer for KAVACH Knowledge Vault.

Evaluates joint [Query, Chunk] token interactions and filters out low-relevance
candidates. Supports local sentence-transformers CrossEncoder with automatic
ultra-fast zero-dependency fallback to cross-token semantic scoring for air-gapped
deployments.
"""

import logging
import math
import re
import threading
from typing import Dict, List, Optional, Set

from backend import config

logger = logging.getLogger("kavach.rerank")

_model = None
_model_lock = threading.Lock()
_load_attempted = False
DEFAULT_RERANK_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"
DEFAULT_THRESHOLD = 0.25


def _sigmoid(x: float) -> float:
    try:
        return 1.0 / (1.0 + math.exp(-float(x)))
    except OverflowError:
        return 0.0 if x < 0 else 1.0


def preload_reranker(model_name: Optional[str] = None) -> bool:
    """Pre-caches and loads the Cross-Encoder model into local memory/storage on startup."""
    global _model, _load_attempted
    target = model_name or DEFAULT_RERANK_MODEL

    # 1. Check for bundled offline model folder inside project
    local_dir = config.PROJECT_ROOT / "models" / "reranker"
    if local_dir.exists() and any(local_dir.iterdir()):
        target = str(local_dir)

    try:
        from sentence_transformers import CrossEncoder
        logger.info(f"Loading Cross-Encoder '{target}'...")
        loaded = CrossEncoder(target)
        with _model_lock:
            _model = loaded
            _load_attempted = True
        logger.info(f"Cross-Encoder '{target}' loaded and ready.")
        return True
    except Exception as exc:
        logger.info(f"Cross-Encoder initialization note ({exc}); using native fast cross-scorer.")
        return False


def _get_cross_encoder():
    global _model, _load_attempted
    if _model is not None or _load_attempted:
        return _model

    with _model_lock:
        if _model is None and not _load_attempted:
            preload_reranker()
    return _model


def _fast_cross_score(query: str, text: str) -> float:
    """Computes a normalized cross-relevance score based on exact token matches,

    phrase overlap, and sequence density. Zero dependencies, executes in < 0.1ms.
    """
    q_tokens = [w for w in re.findall(r"[a-z0-9]+", query.lower()) if len(w) > 1]
    if not q_tokens:
        return 0.5

    t_lower = text.lower()
    t_words = set(re.findall(r"[a-z0-9]+", t_lower))

    matched_tokens = [w for w in q_tokens if w in t_words]
    token_recall = len(matched_tokens) / len(q_tokens)

    # Bigram / sequence overlap boost
    bigram_matches = 0
    total_bigrams = max(1, len(q_tokens) - 1)
    for i in range(len(q_tokens) - 1):
        bigram = f"{q_tokens[i]} {q_tokens[i+1]}"
        if bigram in t_lower:
            bigram_matches += 1
    bigram_score = bigram_matches / total_bigrams

    # Combined normalized relevance score
    combined = 0.7 * token_recall + 0.3 * bigram_score
    return round(combined, 4)


def rerank(
    query: str,
    candidates: List[Dict],
    threshold: float = DEFAULT_THRESHOLD,
    top_k: int = 5,
) -> List[Dict]:
    """Scores candidate passages against query using neural cross-encoder or fast cross-scorer.

    Returns the top_k candidates sorted by relevance score.
    """
    if not candidates:
        return []

    model = _get_cross_encoder()

    if model is not None:
        try:
            pairs = []
            for c in candidates:
                text = (c.get("parent_text") or c.get("chunk_text") or "").strip()
                breadcrumb = c.get("breadcrumb") or ""
                if breadcrumb and not text.startswith(breadcrumb):
                    text = f"[{breadcrumb}]\n{text}"
                pairs.append([query, text])

            raw_scores = model.predict(pairs)
            scored = []
            for rank, score in enumerate(raw_scores):
                norm_score = _sigmoid(score)
                cand = dict(candidates[rank])
                cand["rerank_score"] = round(float(norm_score), 4)
                cand["score"] = cand["rerank_score"]
                if norm_score >= threshold:
                    scored.append(cand)

            scored.sort(key=lambda x: x["rerank_score"], reverse=True)
            return scored[:top_k] if scored else candidates[:top_k]
        except Exception as exc:
            logger.warning(f"Neural reranker scoring error ({exc}). Using fast cross-scorer.")

    # Native fast cross-scorer fallback
    scored_candidates = []
    for cand in candidates:
        text = (cand.get("parent_text") or cand.get("chunk_text") or "")
        cross_score = _fast_cross_score(query, text)
        cand_copy = dict(cand)
        cand_copy["rerank_score"] = cross_score
        cand_copy["score"] = cross_score
        scored_candidates.append(cand_copy)

    scored_candidates.sort(key=lambda x: x["rerank_score"], reverse=True)
    filtered = [c for c in scored_candidates if c["rerank_score"] >= threshold]
    return filtered[:top_k] if filtered else scored_candidates[:top_k]
