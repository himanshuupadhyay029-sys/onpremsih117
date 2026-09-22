"""rerank.py — Local Neural Reranker for KAVACH Knowledge Vault via Ollama.

Scores candidate passages against user queries using local Ollama neural models
(configurable in models.json under 'rerank', e.g. gemma3:4b, granite4.1:3b, etc.)
with zero-dependency fallback to fast cross-token semantic scoring.
"""

import json
import logging
import re
from typing import Dict, List, Optional

from backend.engine import active_llm as ollama, registry

logger = logging.getLogger("kavach.rerank")
DEFAULT_THRESHOLD = 0.25


def preload_reranker(model_name: Optional[str] = None) -> bool:
    """Pre-verification hook for the active Ollama reranker model."""
    try:
        model = model_name or registry.get_model("rerank")
        logger.info(f"Ollama Neural Reranker configured with model '{model}'.")
        return True
    except Exception as exc:
        logger.warning(f"Ollama reranker check note: {exc}")
        return False


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

    combined = 0.7 * token_recall + 0.3 * bigram_score
    return round(combined, 4)


def _ollama_score_candidates(query: str, candidates: List[Dict], model: str) -> Optional[List[Dict]]:
    """Evaluates candidate passages using Ollama with a structured JSON scoring prompt."""
    if not candidates:
        return []

    passages_text = []
    for idx, c in enumerate(candidates):
        raw_text = (c.get("parent_text") or c.get("chunk_text") or "").strip()
        breadcrumb = c.get("breadcrumb") or ""
        if breadcrumb and not raw_text.startswith(breadcrumb):
            raw_text = f"[{breadcrumb}] {raw_text}"
        # Truncate passage to avoid token context overflow
        snippet = raw_text[:400].replace("\n", " ")
        passages_text.append(f"[{idx}] {snippet}")

    passages_block = "\n".join(passages_text)

    prompt = (
        f"You are an accurate passage relevance reranking assistant.\n"
        f"Evaluate how relevant each candidate passage is for answering the user's query.\n"
        f"Assign a relevance score from 0.0 to 1.0 (where 1.0 means highly relevant and directly answers the query, "
        f"and 0.0 means completely irrelevant).\n\n"
        f"Query: \"{query}\"\n\n"
        f"Candidate Passages:\n{passages_block}\n\n"
        f"Respond ONLY with a JSON array of objects mapping each id to its score, formatted exactly as:\n"
        f"[" + ", ".join(f'{{"id": {i}, "score": 0.X}}' for i in range(min(3, len(candidates)))) + "...]\n"
        f"Do not include any explanation or extra text."
    )

    system_prompt = "You are a JSON-only relevance scoring engine. You output valid JSON arrays and nothing else."

    try:
        raw_output = ollama.generate(model=model, prompt=prompt, system=system_prompt)
        
        # Extract JSON array from output (handling code fences if present)
        json_match = re.search(r"\[\s*\{.*?\}\s*\]", raw_output, re.DOTALL)
        if json_match:
            scores_data = json.loads(json_match.group(0))
        else:
            cleaned = raw_output.strip().strip("`").strip()
            if cleaned.startswith("json"):
                cleaned = cleaned[4:].strip()
            scores_data = json.loads(cleaned)

        scores_by_id = {}
        for item in scores_data:
            if isinstance(item, dict) and "id" in item and "score" in item:
                try:
                    c_id = int(item["id"])
                    c_score = float(item["score"])
                    # Clamp between 0.0 and 1.0
                    scores_by_id[c_id] = max(0.0, min(1.0, c_score))
                except (ValueError, TypeError):
                    continue

        scored_candidates = []
        for idx, cand in enumerate(candidates):
            cand_copy = dict(cand)
            score = scores_by_id.get(idx, None)
            if score is None:
                # Fallback to token score for this specific candidate if omitted by LLM
                text = cand.get("parent_text") or cand.get("chunk_text") or ""
                score = _fast_cross_score(query, text)
            cand_copy["rerank_score"] = round(score, 4)
            cand_copy["score"] = cand_copy["rerank_score"]
            scored_candidates.append(cand_copy)

        return scored_candidates
    except Exception as exc:
        logger.warning(f"Ollama reranker scoring error ({exc}). Falling back to fast cross-scorer.")
        return None


def rerank(
    query: str,
    candidates: List[Dict],
    threshold: float = DEFAULT_THRESHOLD,
    top_k: int = 5,
) -> List[Dict]:
    """Scores candidate passages against query using local Ollama neural model.
    Falls back gracefully to native fast cross-scorer if Ollama is unavailable.
    """
    if not candidates:
        return []

    try:
        model = registry.get_model("rerank")
    except Exception:
        model = "gemma3:4b"

    # 1. Try Ollama neural reranker
    scored_candidates = _ollama_score_candidates(query, candidates, model=model)

    # 2. Graceful fallback to fast cross-scorer if Ollama call failed or returned None
    if scored_candidates is None:
        scored_candidates = []
        for cand in candidates:
            text = cand.get("parent_text") or cand.get("chunk_text") or ""
            cross_score = _fast_cross_score(query, text)
            cand_copy = dict(cand)
            cand_copy["rerank_score"] = cross_score
            cand_copy["score"] = cross_score
            scored_candidates.append(cand_copy)

    scored_candidates.sort(key=lambda x: x["rerank_score"], reverse=True)
    filtered = [c for c in scored_candidates if c["rerank_score"] >= threshold]
    return filtered[:top_k] if filtered else scored_candidates[:top_k]
