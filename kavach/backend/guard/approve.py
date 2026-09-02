"""approve.py — Human approval gate for high-stakes document outputs (Phase 11).

Provides an explainable, honest risk assessment heuristic and manages pending/resolved
approval state. For high/medium risk documents, generation pauses until an operator
Approves, Edits, or Rejects the draft.
"""

from datetime import datetime, timezone
import re
from typing import Any, Dict, List, Optional, Union

from backend.audit.logbook import log_event

# In-memory store of approval records, keyed by task_id
_APPROVAL_RECORDS: Dict[str, Dict[str, Any]] = {}


def assess_risk(
    task_type: str,
    document_content: Union[str, Dict[str, Any]],
    sources_used: Optional[List[Union[str, Dict[str, Any]]]] = None,
) -> Dict[str, Any]:
    """Simple, explainable risk heuristic for tasks and generated documents.

    Heuristic rules:
    - Non-document tasks (search, calc, code): Low risk (informational only).
    - Document tasks with 0 or 1 source, or ungrounded notices: High risk.
    - Document tasks with 2+ supporting sources: Medium risk (formal document, requires sign-off).
    - If document content explicitly contains ungrounded/missing markers: High risk.
    """
    sources = sources_used or []
    source_count = len(sources)

    # 1. Non-document tasks are routine / low risk
    if task_type != "document":
        return {
            "risk": "low",
            "confidence": 0.95,
            "reasoning": f"Task type '{task_type}' is informational (search/calc/code) and does not produce a formal delivered report.",
        }

    # Extract text representation to check for missing documentation notices and specific claims
    if isinstance(document_content, dict):
        title = document_content.get("title", "")
        sections = document_content.get("sections", [])
        body_parts = []
        for s in sections:
            if isinstance(s, dict):
                body_parts.append(f"{s.get('heading', '')}: {s.get('body', '')}")
            else:
                body_parts.append(str(s))
        body_text = " ".join(body_parts)
        full_text = f"{title} {body_text}".strip()
    else:
        full_text = str(document_content).strip()

    full_lower = full_text.lower()

    is_missing_notice = any(
        phrase in full_lower
        for phrase in [
            "notice of missing documentation",
            "information not documented",
            "not found in the organization's knowledge vault",
            "no procedure or documentation exists",
            "unrecorded/missing",
            "grounded in sops: false",
            "no sop exists",
            "no documentation exists",
            "not documented",
        ]
    )

    # Check for specific claims (numbers, procedures, named entities, or substantial length)
    has_specifics = bool(
        re.search(r"\b\d+(?:\.\d+)?\b", full_text)
        or len(full_text) > 120
        or any(w in full_lower for w in ["procedure", "protocol", "step", "checklist", "valve", "psi", "stage", "schedule"])
    )

    # 2. Honest "not found" notice
    if is_missing_notice:
        return {
            "risk": "high",
            "confidence": 0.40,
            "reasoning": "High risk (Honest Notice): document honestly states that the requested procedure or documentation does not exist in the Knowledge Vault.",
        }

    # 3. Fabricated or ungrounded claims with ZERO sources
    if source_count == 0:
        if has_specifics:
            reasoning = (
                "High risk: zero supporting sources found in the Knowledge Vault. "
                "WARNING: content may be fabricated - no supporting sources found for specific claims made."
            )
            confidence = 0.20
        else:
            reasoning = "High risk: document lacks grounded SOP references in the Knowledge Vault."
            confidence = 0.35
        return {
            "risk": "high",
            "confidence": confidence,
            "reasoning": reasoning,
        }

    # 4. Thin sourcing (only 1 source)
    if source_count < 2:
        return {
            "risk": "high",
            "confidence": 0.55,
            "reasoning": f"High risk: thin sourcing. Only {source_count} source excerpt was retrieved for this formal document.",
        }

    # 5. Document tasks with 2+ sources
    return {
        "risk": "medium",
        "confidence": 0.85,
        "reasoning": f"Medium risk: document is grounded in {source_count} source(s), but requires human verification before final distribution.",
    }


def request_approval(
    task_id: str,
    document_content: Union[str, Dict[str, Any]],
    risk_assessment: Dict[str, Any],
    sources: Optional[List[Union[str, Dict[str, Any]]]] = None,
) -> Dict[str, Any]:
    """Stores a pending approval record for human review."""
    record = {
        "task_id": task_id,
        "status": "pending",
        "risk": risk_assessment.get("risk", "medium"),
        "confidence": risk_assessment.get("confidence", 0.5),
        "reasoning": risk_assessment.get("reasoning", "Awaiting human review."),
        "document_content": document_content,
        "sources": sources or [],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "resolved_at": None,
        "decision": None,
        "filename": None,
        "file_path": None,
    }
    _APPROVAL_RECORDS[task_id] = record
    return record


def get_approval(task_id: str) -> Optional[Dict[str, Any]]:
    """Retrieves an approval record by task_id."""
    return _APPROVAL_RECORDS.get(task_id)


def list_approvals() -> List[Dict[str, Any]]:
    """Lists all stored approval records."""
    return list(_APPROVAL_RECORDS.values())


def resolve_approval(
    task_id: str,
    decision: str,
    edited_content: Optional[Union[str, Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Resolves an approval record with 'approve', 'reject', or 'edit', and logs an audit event."""
    record = _APPROVAL_RECORDS.get(task_id)
    if not record:
        record = {
            "task_id": task_id,
            "status": "pending",
            "risk": "medium",
            "confidence": 0.5,
            "reasoning": "Ad-hoc approval record created upon resolution.",
            "document_content": edited_content or {},
            "sources": [],
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        _APPROVAL_RECORDS[task_id] = record

    decision_clean = decision.strip().lower()
    if decision_clean not in {"approve", "reject", "edit"}:
        raise ValueError(f"Invalid decision '{decision}'. Must be 'approve', 'reject', or 'edit'.")

    record["resolved_at"] = datetime.now(timezone.utc).isoformat()
    record["decision"] = decision_clean

    if decision_clean == "approve":
        record["status"] = "approved"
    elif decision_clean == "reject":
        record["status"] = "rejected"
    elif decision_clean == "edit":
        record["status"] = "edited"
        if edited_content is not None:
            record["document_content"] = edited_content

    # Append-only audit event for human oversight action
    log_event(
        task_id=task_id,
        event_type="approval",
        actor="human_supervisor",
        summary=f"Approval gate: {decision_clean.upper()} (Risk: {record['risk']}, Confidence: {record['confidence']:.2f})",
        metadata={
            "task_id": task_id,
            "decision": decision_clean,
            "risk": record["risk"],
            "confidence": record["confidence"],
            "reasoning": record["reasoning"],
            "has_edits": decision_clean == "edit",
        },
        external_calls=0,
    )

    return record
