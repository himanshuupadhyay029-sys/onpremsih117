"""retrieve.py — embeds a query, runs a FAISS top-k search over the Knowledge
Vault, then applies a light MMR (Maximal Marginal Relevance) re-selection to
cut redundancy before handing chunks to the search tool.

No reranker model call: MMR here is pure vector math (cosine similarity) over
vectors FAISS already returned/reconstructed — deliberately cheap, per the
Phase 4 scope decision (no second model competing for VRAM).
"""

import json
from typing import Dict, List

import faiss
import numpy as np

from backend.vault.ingest import INDEX_PATH, METADATA_PATH
from backend.engine import ollama, registry

DEFAULT_TOP_K = 6
DEFAULT_FINAL_K = 4
MMR_LAMBDA = 0.6  # weight on relevance vs. (1 - lambda) weight on redundancy penalty


def _load_index_and_metadata():
    if not (INDEX_PATH.exists() and METADATA_PATH.exists()):
        return None, []
    index = faiss.read_index(str(INDEX_PATH))
    with open(METADATA_PATH, "r", encoding="utf-8") as f:
        metadata = json.load(f)
    return index, metadata


def _cosine_sim(a: np.ndarray, b: np.ndarray) -> float:
    denom = float(np.linalg.norm(a) * np.linalg.norm(b))
    return float(np.dot(a, b) / denom) if denom else 0.0


def _mmr_select(
    query_vec: np.ndarray,
    candidate_vecs: List[np.ndarray],
    candidates: List[Dict],
    k: int,
    lambda_mult: float = MMR_LAMBDA,
) -> List[Dict]:
    """Greedily picks up to k candidates balancing relevance to the query
    against redundancy with chunks already selected."""
    if not candidates:
        return []

    selected_idx: List[int] = []
    remaining_idx = list(range(len(candidates)))

    while remaining_idx and len(selected_idx) < k:
        best_idx = None
        best_score = float("-inf")
        for i in remaining_idx:
            relevance = _cosine_sim(query_vec, candidate_vecs[i])
            redundancy = max(
                (_cosine_sim(candidate_vecs[i], candidate_vecs[j]) for j in selected_idx),
                default=0.0,
            )
            mmr_score = lambda_mult * relevance - (1 - lambda_mult) * redundancy
            if mmr_score > best_score:
                best_score = mmr_score
                best_idx = i
        selected_idx.append(best_idx)
        remaining_idx.remove(best_idx)

    return [candidates[i] for i in selected_idx]


def retrieve(query: str, top_k: int = DEFAULT_TOP_K, final_k: int = DEFAULT_FINAL_K) -> List[Dict]:
    """Returns up to final_k chunks as {source_filename, chunk_text, chunk_index, score}.

    score is the raw FAISS L2 distance for that candidate (lower = closer/more
    relevant) — not a normalized similarity.
    """
    index, metadata = _load_index_and_metadata()
    if index is None or index.ntotal == 0:
        return []

    embed_model = registry.get_model("embedding")
    query_vec = np.array(ollama.embed(embed_model, query), dtype="float32")

    search_k = min(top_k, index.ntotal)
    distances, indices = index.search(np.array([query_vec]), search_k)

    candidates: List[Dict] = []
    candidate_vecs: List[np.ndarray] = []
    for rank, idx in enumerate(indices[0]):
        if idx == -1:
            continue
        meta = metadata[idx]
        candidates.append(
            {
                "source_filename": meta["source_filename"],
                "chunk_text": meta["chunk_text"],
                "chunk_index": meta["chunk_index"],
                "score": float(distances[0][rank]),
            }
        )
        candidate_vecs.append(index.reconstruct(int(idx)))

    final_count = min(final_k, len(candidates))
    return _mmr_select(query_vec, candidate_vecs, candidates, k=final_count)
