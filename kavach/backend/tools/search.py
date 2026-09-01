"""search.py — the agent's real 'search' tool (Phase 4 & 5).

Retrieves grounded context from the Knowledge Vault (backend/vault/retrieve.py)
and answers using a strict grounding prompt: the reasoning model is told to
answer ONLY from the provided excerpts, or admit it doesn't know, rather than
guessing. Every call is audit-logged with external_calls=0 (FAISS + local
Ollama only, no network calls).

Phase 5 fix: returns structured {answer, sources, grounded: bool} flag
indicating whether the knowledge base actually supported the answer.
"""

from typing import Dict, List, Optional

from backend.audit.logbook import log_event
from backend.engine import ollama, registry
from backend.vault.retrieve import retrieve

GROUNDING_PROMPT_TEMPLATE = """Answer the question using ONLY the source excerpts provided below. \
If the answer is not present in these excerpts, say plainly that you don't have enough \
information to answer — do not guess, and do not use any outside knowledge.

{sources_block}

Question: {query}

Answer clearly and concisely, and state which source(s) (by filename) you used.
"""

UNGROUNDED_INDICATORS = [
    "don't have enough information",
    "do not have enough information",
    "not enough information",
    "cannot find information",
    "is not present in these excerpts",
    "are not present in these excerpts",
    "not mentioned in the provided",
    "not found in the provided",
    "no information provided",
    "no mention of",
    "does not contain information",
    "do not contain information",
    "not covered in the provided",
]


def _check_is_grounded(answer: str) -> bool:
    """Returns False if the model admitted the question is not covered by the excerpts."""
    ans_lower = answer.lower()
    return not any(indicator in ans_lower for indicator in UNGROUNDED_INDICATORS)


def search(query: str, task_id: Optional[str] = None) -> Dict:
    results = retrieve(query)

    if not results:
        answer = "I don't have enough information in the knowledge vault to answer this."
        log_event(
            task_id=task_id,
            event_type="search",
            actor="vault",
            summary=f"Search for '{query}': no vault documents matched (grounded=False)",
            metadata={"query": query, "sources_used": [], "grounded": False},
            external_calls=0,
        )
        return {"answer": answer, "sources": [], "grounded": False}

    sources_block = "\n\n".join(f"[Source: {r['source_filename']}]\n{r['chunk_text']}" for r in results)
    prompt = GROUNDING_PROMPT_TEMPLATE.format(sources_block=sources_block, query=query)

    reasoning_model = registry.get_model("reasoning")
    answer = ollama.generate(reasoning_model, prompt)

    grounded = _check_is_grounded(answer)
    sources: List[Dict] = [{"filename": r["source_filename"], "excerpt": r["chunk_text"]} for r in results]

    log_event(
        task_id=task_id,
        event_type="search",
        actor=reasoning_model,
        summary=f"Search for '{query}': answered (grounded={grounded}) using {[s['filename'] for s in sources]}",
        metadata={
            "query": query,
            "sources_used": [s["filename"] for s in sources] if grounded else [],
            "grounded": grounded,
        },
        external_calls=0,
    )

    # Only pass forward sources if the search was actually grounded in them
    return {"answer": answer, "sources": sources if grounded else [], "grounded": grounded}
