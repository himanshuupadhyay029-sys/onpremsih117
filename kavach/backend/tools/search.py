"""search.py — Grounded Knowledge Vault search tool with inline citations for KAVACH.

Retrieves grounded context via hybrid multi-stage retrieval (backend/vault/retrieve.py)
and synthesizes answers with strict anti-hallucination framing and inline [1], [2]
source citations. Every call is audit-logged with external_calls=0 (strictly local).
"""

from typing import Dict, List, Optional
import time

from backend.audit.logbook import log_event
from backend.engine import ollama, registry
from backend.terminal_logger import log_tool, _truncate
from backend.vault.retrieve import retrieve

SEARCH_SYSTEM_PROMPT = """You are KAVACH's sovereign on-premises Knowledge Vault specialist.
Your mission is to synthesize comprehensive, clear, and technically precise answers to the user's question using ONLY the provided verified source excerpts.

Rules:
1. Base all statements strictly on the provided excerpts.
2. For every factual claim, include inline citations using bracketed numbers like [1], [2], or [1, 2] corresponding to the source entries.
3. If the excerpts do not contain enough facts to answer a part of the question, clearly state what information is missing.
4. Structure your response with clean markdown headings, bold terms, and bullet points.
"""

GROUNDING_PROMPT_TEMPLATE = """Source Excerpts from Knowledge Vault:

{sources_block}

User Question:
{query}

Please provide a detailed, well-structured answer with inline source citations [1], [2]:"""

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
    """Returns False if the model admitted the question is completely uncovered by the excerpts."""
    ans_lower = answer.lower().strip()
    if any(ans_lower.startswith(prefix) for prefix in [
        "i don't have enough information",
        "i do not have enough information",
        "no information provided",
        "cannot find information",
        "not enough information",
    ]):
        return False
    if any(marker in ans_lower for marker in ["[1]", "[2]", "[3]", ".md", ".docx", ".pdf", ".txt", ".png", "source:"]):
        return True
    return not any(indicator in ans_lower for indicator in UNGROUNDED_INDICATORS)


def search(
    query: str,
    task_id: Optional[str] = None,
    user_id: Optional[str] = None,
    target_files: Optional[List[str]] = None,
) -> Dict:
    t0 = time.perf_counter()
    log_tool("vault", "SEARCH", f"Query: '{_truncate(query, 70)}'")
    results = retrieve(query, user_id=user_id, target_files=target_files)

    if not results:
        answer = "I don't have enough information in the knowledge vault to answer this."
        log_tool("vault", "NO_MATCH", "No matching documents found in Knowledge Vault", is_error=True)
        log_event(
            task_id=task_id,
            event_type="search",
            actor="vault",
            summary=f"Search for '{query}': no vault documents matched (grounded=False)",
            metadata={"query": query, "sources_used": [], "grounded": False},
            external_calls=0,
            user_id=user_id,
        )
        return {"answer": answer, "sources": [], "grounded": False}


    # Format structured evidence blocks with explicit source IDs [1], [2]
    source_blocks = []
    sources: List[Dict] = []
    for rank, r in enumerate(results, start=1):
        breadcrumb = r.get("breadcrumb") or r.get("source_filename", "Knowledge Vault")
        source_blocks.append(
            f"--- SOURCE [{rank}] ---\n"
            f"Document: {r['source_filename']}\n"
            f"Section: {breadcrumb}\n"
            f"Content:\n{r['chunk_text']}\n"
            f"------------------------"
        )
        sources.append(
            {
                "id": rank,
                "filename": r["source_filename"],
                "breadcrumb": breadcrumb,
                "excerpt": r["chunk_text"],
                "score": r.get("score", 1.0),
                "chunk_id": r.get("chunk_id"),
                "parent_id": r.get("parent_id"),
            }
        )

    sources_block = "\n\n".join(source_blocks)
    messages = [
        {"role": "system", "content": SEARCH_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": f"Verified Source Excerpts from Knowledge Vault:\n\n{sources_block}\n\nUser Question:\n{query}\n\nPlease synthesize a clear, comprehensive answer using inline citations [1], [2]:",
        },
    ]

    reasoning_model = registry.get_model("reasoning")
    try:
        answer = ollama.chat(reasoning_model, messages)
    except Exception:
        try:
            prompt = GROUNDING_PROMPT_TEMPLATE.format(sources_block=sources_block, query=query)
            answer = ollama.generate(reasoning_model, prompt, system=SEARCH_SYSTEM_PROMPT)
        except Exception as exc:
            answer = f"[error] Reasoning model failed to synthesize answer: {exc}"

    grounded = _check_is_grounded(answer)
    files_cited = list({s['filename'] for s in sources})
    elapsed = time.perf_counter() - t0
    log_tool("vault", "ANSWER", f"{len(results)} chunk(s) from {files_cited} (grounded={grounded})", elapsed_s=elapsed)

    log_event(
        task_id=task_id,
        event_type="search",
        actor=reasoning_model,
        summary=f"Search for '{query}': answered (grounded={grounded}) using {[s['filename'] for s in sources]}",
        metadata={
            "query": query,
            "sources_used": [f"[{s['id']}] {s['filename']} ({s['breadcrumb']})" for s in sources] if grounded else [],
            "grounded": grounded,
        },
        external_calls=0,
    )

    return {"answer": answer, "sources": sources if grounded else [], "grounded": grounded}
