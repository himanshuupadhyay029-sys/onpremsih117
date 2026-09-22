"""retrieve.py — Hybrid multi-stage retrieval pipeline for KAVACH Knowledge Vault.

Implements:
1. Dual Candidate Retrieval: Parallel Dense (FAISS) + Sparse (BM25 Okapi).
2. Reciprocal Rank Fusion (RRF, k=60) for robust multi-modal search ranking.
3. Hierarchical Node & Sibling Window Expansion (parent section consolidation + neighbor chunks).
4. Neural Cross-Encoder Reranking (ms-marco-MiniLM-L-6-v2) with threshold filtering.
5. MMR Diversity Selection & Token Budget Context Packing.
"""

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

import faiss
import numpy as np

import time
from backend.terminal_logger import log_tool
from backend.vault.bm25 import BM25Index
from backend.vault.ingest import BM25_PATH, INDEX_PATH, METADATA_PATH
from backend.vault.rerank import rerank as cross_encoder_rerank

logger = logging.getLogger("kavach.retrieve")

DEFAULT_CANDIDATE_K = 20
DEFAULT_FINAL_K = 5
RRF_K = 60
DENSE_WEIGHT = 1.0
SPARSE_WEIGHT = 0.8
TOKEN_BUDGET_CHARS = 10000  # ~2,500 tokens budget


def _load_all_stores():
    index = None
    metadata: List[Dict] = []
    bm25 = None

    if INDEX_PATH.exists() and METADATA_PATH.exists():
        try:
            raw_bytes = INDEX_PATH.read_bytes()
            if raw_bytes:
                index = faiss.deserialize_index(np.frombuffer(raw_bytes, dtype=np.uint8))
                with open(METADATA_PATH, "r", encoding="utf-8") as f:
                    metadata = json.load(f)
        except Exception:
            index = None
            metadata = []

    if BM25_PATH.exists():
        bm25 = BM25Index.load(BM25_PATH)

    return index, metadata, bm25


def _cosine_sim(a: np.ndarray, b: np.ndarray) -> float:
    denom = float(np.linalg.norm(a) * np.linalg.norm(b))
    return float(np.dot(a, b) / denom) if denom else 0.0


def _reciprocal_rank_fusion(
    dense_ranks: List[int],
    sparse_ranks: List[int],
    k: int = RRF_K,
    w_dense: float = DENSE_WEIGHT,
    w_sparse: float = SPARSE_WEIGHT,
) -> List[Tuple[int, float]]:
    """Merges dense and sparse ranking lists using Reciprocal Rank Fusion."""
    rrf_scores: Dict[int, float] = {}

    for rank, doc_idx in enumerate(dense_ranks):
        rrf_scores[doc_idx] = rrf_scores.get(doc_idx, 0.0) + (w_dense / (k + rank + 1))

    for rank, doc_idx in enumerate(sparse_ranks):
        rrf_scores[doc_idx] = rrf_scores.get(doc_idx, 0.0) + (w_sparse / (k + rank + 1))

    sorted_candidates = sorted(rrf_scores.items(), key=lambda kv: kv[1], reverse=True)
    return sorted_candidates


def _expand_hierarchical_context(
    candidate_indices: List[int],
    metadata: List[Dict],
    top_n: int = 15,
) -> List[Dict]:
    """Expands candidate child chunks into Parent Sections or Sibling Windows.

    1. If >= 2 retrieved child chunks belong to the same parent_id, consolidate
       them into the full parent section to preserve coherent tables/context.
    2. For single child hits, pull adjacent sibling chunks (+-1) if available.
    """
    selected_meta = [metadata[idx] for idx in candidate_indices[:top_n] if idx < len(metadata)]
    if not selected_meta:
        return []

    # Count hits per parent_id
    parent_hit_counts: Dict[str, int] = {}
    for entry in selected_meta:
        pid = entry.get("parent_id")
        if pid:
            parent_hit_counts[pid] = parent_hit_counts.get(pid, 0) + 1

    expanded_candidates: List[Dict] = []
    seen_parent_ids: Set[str] = set()
    seen_chunk_ids: Set[str] = set()

    for entry in selected_meta:
        pid = entry.get("parent_id")
        cid = entry.get("chunk_id")

        # 1. Multi-hit consolidation to Parent Section
        if pid and parent_hit_counts.get(pid, 0) >= 2:
            if pid in seen_parent_ids:
                continue
            seen_parent_ids.add(pid)
            parent_text = entry.get("parent_text") or entry.get("chunk_text", "")
            expanded_candidates.append(
                {
                    "source_filename": entry.get("source_filename", ""),
                    "breadcrumb": entry.get("breadcrumb", ""),
                    "chunk_text": parent_text,
                    "parent_text": parent_text,
                    "parent_id": pid,
                    "chunk_id": cid,
                    "is_parent_expanded": True,
                }
            )
        else:
            # 2. Standalone child chunk with sibling window expansion
            if cid in seen_chunk_ids:
                continue
            seen_chunk_ids.add(cid)

            chunk_idx = entry.get("chunk_index", 0)
            src_file = entry.get("source_filename", "")
            child_text = entry.get("chunk_text", "")

            # Look for adjacent sibling chunks in metadata
            prev_chunk = ""
            next_chunk = ""
            for other in metadata:
                if other.get("source_filename") == src_file:
                    if other.get("chunk_index") == chunk_idx - 1:
                        prev_chunk = other.get("chunk_text", "")
                    elif other.get("chunk_index") == chunk_idx + 1:
                        next_chunk = other.get("chunk_text", "")

            # Combine window context cleanly
            window_parts = []
            if prev_chunk and len(prev_chunk) < 300:
                window_parts.append(prev_chunk)
            window_parts.append(child_text)
            if next_chunk and len(next_chunk) < 300:
                window_parts.append(next_chunk)

            full_window_text = "\n...\n".join(window_parts)

            expanded_candidates.append(
                {
                    "source_filename": src_file,
                    "breadcrumb": entry.get("breadcrumb", ""),
                    "chunk_text": child_text,
                    "parent_text": full_window_text,
                    "parent_id": pid,
                    "chunk_id": cid,
                    "is_parent_expanded": False,
                }
            )

    return expanded_candidates


def _pack_token_budget(
    candidates: List[Dict],
    max_chars: int = TOKEN_BUDGET_CHARS,
    final_k: int = DEFAULT_FINAL_K,
) -> List[Dict]:
    """Packs the top candidates into a bounded token budget while preserving source metadata."""
    packed: List[Dict] = []
    total_len = 0

    for cand in candidates:
        text = (cand.get("parent_text") or cand.get("chunk_text") or "").strip()
        text_len = len(text)

        if total_len + text_len > max_chars and packed:
            # If exceeding budget, trim candidate text to remaining budget if substantial
            rem_budget = max_chars - total_len
            if rem_budget >= 300:
                trimmed_cand = dict(cand)
                trimmed_cand["chunk_text"] = text[:rem_budget] + "\n... [truncated for context limit]"
                packed.append(trimmed_cand)
            break

        packed.append(cand)
        total_len += text_len

        if len(packed) >= final_k:
            break

    return packed


def retrieve(
    query: str,
    candidate_k: int = DEFAULT_CANDIDATE_K,
    final_k: int = DEFAULT_FINAL_K,
    rerank_threshold: float = 0.35,
) -> List[Dict]:
    """Executes the full hybrid retrieval pipeline:

    1. Parallel Dense (FAISS) + Sparse (BM25) search.
    2. Reciprocal Rank Fusion (RRF).
    3. Hierarchical Parent & Sibling Window Expansion.
    4. Neural Cross-Encoder Reranking & confidence cutoff.
    5. Token Budget Packing & Citation Metadata enrichment.
    """
    t0 = time.perf_counter()
    index, metadata, bm25 = _load_all_stores()
    if index is None or index.ntotal == 0 or not metadata:
        return []

    # 1. Dense Vector Search (FAISS)
    embed_model = registry.get_model("embedding")
    query_vec = np.array(ollama.embed(embed_model, query), dtype="float32")

    search_k = min(candidate_k, index.ntotal)
    distances, indices = index.search(np.array([query_vec]), search_k)
    dense_ranked_indices = [int(idx) for idx in indices[0] if idx != -1]

    # 2. Sparse Lexical Search (BM25)
    sparse_ranked_indices: List[int] = []
    if bm25 is not None:
        bm25_hits = bm25.score(query, top_k=candidate_k)
        sparse_ranked_indices = [doc_id for doc_id, _ in bm25_hits]

    # 3. Reciprocal Rank Fusion
    fused_candidates = _reciprocal_rank_fusion(
        dense_ranked_indices,
        sparse_ranked_indices,
        k=RRF_K,
    )
    fused_indices = [doc_idx for doc_idx, score in fused_candidates]

    # 4. Contextual Hierarchy & Window Expansion
    expanded_candidates = _expand_hierarchical_context(
        fused_indices,
        metadata,
        top_n=candidate_k,
    )

    # 5. Neural Cross-Encoder Reranking
    reranked_candidates = cross_encoder_rerank(
        query=query,
        candidates=expanded_candidates,
        threshold=rerank_threshold,
        top_k=candidate_k,
    )

    # If cross-encoder filtered out everything due to strict threshold, fallback gracefully to top fused
    final_candidates = reranked_candidates if reranked_candidates else expanded_candidates[:final_k]

    # 6. Token Budget Packing & Final Metadata Assembly
    packed_results = _pack_token_budget(final_candidates, max_chars=TOKEN_BUDGET_CHARS, final_k=final_k)

    # Standardize output structure for synthesizer
    formatted_chunks: List[Dict] = []
    for rank, item in enumerate(packed_results):
        formatted_chunks.append(
            {
                "source_filename": item.get("source_filename", "Knowledge Vault"),
                "breadcrumb": item.get("breadcrumb", ""),
                "chunk_text": item.get("parent_text") or item.get("chunk_text", ""),
                "chunk_index": rank,
                "score": item.get("rerank_score", 1.0),
                "is_parent_expanded": item.get("is_parent_expanded", False),
            }
        )

    log_tool(
        "vault",
        "HYBRID",
        f"Searched {index.ntotal} vectors + BM25 -> {len(packed_results)} chunks selected (fused={len(fused_candidates)})",
        elapsed_s=time.perf_counter() - t0,
    )
    return formatted_chunks
