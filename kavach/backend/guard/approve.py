import difflib
import json
import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Union

from backend.audit.logbook import log_event
from backend.terminal_logger import log_guard

logger = logging.getLogger("kavach.approve")

# In-memory store of approval records, keyed by task_id
_APPROVAL_RECORDS: Dict[str, Dict[str, Any]] = {}

HAZARDOUS_KEYWORDS = [
    "hazardous", "hazard", "override", "emergency", "lockdown",
    "shutdown", "bypass", "high pressure", "toxic", "flammable",
    "corrosive", "explosive", "radioactive", "spill", "containment",
    "critical", "danger", "evacuation", "catastrophic", "lethal",
]


def assess_risk(
    task_type: str,
    document_content: Union[str, Dict[str, Any]],
    sources_used: Optional[List[Union[str, Dict[str, Any]]]] = None,
    retrieval_confidence: Optional[float] = None,
    source_classification: Optional[str] = None,
    department: Optional[str] = None,
) -> Dict[str, Any]:
    """Simple, explainable risk heuristic for tasks and generated documents.

    Heuristic rules:
    - Non-document tasks (search, calc, code): Low risk (informational only), unless hazardous.
    - Restricted document classification: High risk (mandatory human sign-off).
    - Low retrieval confidence (< 0.60): High risk.
    - Hazardous operational keywords: High risk (deterministic safety backstop).
    - Document tasks with 0 or 1 source, or ungrounded notices: High risk.
    - Document tasks with 2+ supporting sources: Medium risk (formal document, requires sign-off).
    """
    sources = sources_used or []
    source_count = len(sources)
    dept = department or "general"

    # Extract text representation
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

    # Rule 1: Restricted classification backstop
    if source_classification == "restricted":
        res = {
            "risk": "high",
            "confidence": 0.40,
            "reasoning": "High risk: Content is sourced from restricted-classification documents and requires formal sign-off.",
            "department": dept,
        }
        log_guard("risk", "ASSESS", f"Document (Restricted classification) -> Risk: HIGH")
        return res

    # Rule 2: Low retrieval confidence backstop
    if retrieval_confidence is not None and retrieval_confidence < 0.60:
        res = {
            "risk": "high",
            "confidence": round(retrieval_confidence, 2),
            "reasoning": f"High risk: Low retrieval confidence ({retrieval_confidence:.2f} < 0.60) — factual grounding may be unreliable.",
            "department": dept,
        }
        log_guard("risk", "ASSESS", f"Document (Low confidence: {retrieval_confidence:.2f}) -> Risk: HIGH")
        return res

    # Rule 3: Deterministic hazardous keyword backstop
    matched_hazards = [kw for kw in HAZARDOUS_KEYWORDS if kw in full_lower]
    if matched_hazards:
        res = {
            "risk": "high",
            "confidence": 0.50,
            "reasoning": f"High risk (Safety Backstop): Content references hazardous/safety-critical operations ({', '.join(matched_hazards[:3])}).",
            "department": dept,
        }
        log_guard("risk", "ASSESS", f"Document (Hazardous: {matched_hazards[:2]}) -> Risk: HIGH")
        return res

    # Rule 4: Non-document tasks are routine / low risk
    if task_type != "document":
        res = {
            "risk": "low",
            "confidence": 0.95,
            "reasoning": f"Task type '{task_type}' is informational (search/calc/code) and does not produce a formal delivered report.",
            "department": dept,
        }
        log_guard("risk", "ASSESS", f"Task '{task_type}' -> Risk: LOW (conf: 0.95)")
        return res

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

    # Rule 5: Honest "not found" notice
    if is_missing_notice:
        return {
            "risk": "high",
            "confidence": 0.40,
            "reasoning": "High risk (Honest Notice): document honestly states that the requested procedure or documentation does not exist in the Knowledge Vault.",
            "department": dept,
        }

    # Rule 6: Fabricated or ungrounded claims with ZERO sources
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
            "department": dept,
        }

    # Rule 7: Thin sourcing (only 1 source)
    if source_count < 2:
        return {
            "risk": "high",
            "confidence": 0.55,
            "reasoning": f"High risk: thin sourcing. Only {source_count} source excerpt was retrieved for this formal document.",
            "department": dept,
        }

    # Rule 8: Document tasks with 2+ sources
    res = {
        "risk": "medium",
        "confidence": 0.85,
        "reasoning": f"Medium risk: document is grounded in {source_count} source(s), but requires human verification before final distribution.",
        "department": dept,
    }
    log_guard("risk", "ASSESS", f"Document ({source_count} sources) -> Risk: MEDIUM (conf: 0.85)")
    return res


def request_approval(
    task_id: str,
    document_content: Union[str, Dict[str, Any]],
    risk_assessment: Dict[str, Any],
    sources: Optional[List[Union[str, Dict[str, Any]]]] = None,
    department: Optional[str] = None,
    user_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Stores a pending approval record in-memory and in the database for human review."""
    target_dept = department or risk_assessment.get("department") or "general"
    risk_level = risk_assessment.get("risk", "medium")

    record = {
        "task_id": task_id,
        "status": "pending",
        "risk": risk_level,
        "confidence": risk_assessment.get("confidence", 0.5),
        "reasoning": risk_assessment.get("reasoning", "Awaiting human review."),
        "department": target_dept,
        "document_content": document_content,
        "sources": sources or [],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "resolved_at": None,
        "decision": None,
        "filename": None,
        "file_path": None,
        "approver_id": None,
        "diff": None,
    }
    _APPROVAL_RECORDS[task_id] = record

    # Persist to database
    try:
        from backend.db.session import SessionLocal
        from backend.db.models import Approval

        db = SessionLocal()
        try:
            draft_str = json.dumps(document_content) if isinstance(document_content, (dict, list)) else str(document_content)
            existing = db.query(Approval).filter(Approval.task_id == task_id).first()
            if not existing:
                appr_row = Approval(
                    task_id=task_id,
                    department=target_dept,
                    risk_level=risk_level,
                    status="pending",
                    original_draft=draft_str,
                )
                db.add(appr_row)
                db.commit()
        finally:
            db.close()
    except Exception as exc:
        logger.warning(f"Failed to persist approval record to DB: {exc}")

    log_guard("approve", "GATE_PAUSED", f"Task {task_id[:8]} paused for Human Approval Gate (Risk: {record['risk'].upper()}, Dept: {target_dept})")
    return record


def get_approval(task_id: str) -> Optional[Dict[str, Any]]:
    """Retrieves an approval record by task_id from memory or database fallback."""
    if task_id in _APPROVAL_RECORDS:
        return _APPROVAL_RECORDS[task_id]

    try:
        from backend.db.session import SessionLocal
        from backend.db.models import Approval

        db = SessionLocal()
        try:
            row = db.query(Approval).filter(Approval.task_id == task_id).first()
            if row:
                doc_content = {}
                if row.original_draft:
                    try:
                        doc_content = json.loads(row.original_draft)
                    except Exception:
                        doc_content = row.original_draft

                record = {
                    "task_id": row.task_id,
                    "status": row.status,
                    "risk": row.risk_level or "medium",
                    "confidence": 0.5,
                    "reasoning": "Retrieved from persistent approvals store.",
                    "department": row.department or "general",
                    "document_content": doc_content,
                    "sources": [],
                    "created_at": row.requested_at.isoformat() if row.requested_at else None,
                    "resolved_at": row.decided_at.isoformat() if row.decided_at else None,
                    "decision": row.status if row.status in ("approved", "rejected", "edited") else None,
                    "filename": None,
                    "file_path": None,
                    "approver_id": str(row.approver_user_id) if row.approver_user_id else None,
                    "diff": row.diff,
                }
                _APPROVAL_RECORDS[task_id] = record
                return record
        finally:
            db.close()
    except Exception:
        pass

    return None


def list_approvals() -> List[Dict[str, Any]]:
    """Lists all stored approval records."""
    return list(_APPROVAL_RECORDS.values())


def resolve_approval(
    task_id: str,
    decision: str,
    approver_user: Optional[Any] = None,
    edited_content: Optional[Union[str, Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Resolves an approval record with 'approve', 'reject', or 'edit', with authorization and diff tracking."""
    record = get_approval(task_id)
    if not record:
        record = {
            "task_id": task_id,
            "status": "pending",
            "risk": "medium",
            "confidence": 0.5,
            "reasoning": "Ad-hoc approval record created upon resolution.",
            "department": "general",
            "document_content": edited_content or {},
            "sources": [],
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        _APPROVAL_RECORDS[task_id] = record

    decision_clean = decision.strip().lower()
    if decision_clean not in {"approve", "reject", "edit"}:
        raise ValueError(f"Invalid decision '{decision}'. Must be 'approve', 'reject', or 'edit'.")

    # Approver Authorization Check (Part B)
    if approver_user is not None:
        user_role = getattr(approver_user, "role", None) or (approver_user.get("role") if isinstance(approver_user, dict) else None)
        user_dept = getattr(approver_user, "department", None) or (approver_user.get("department") if isinstance(approver_user, dict) else None)

        if user_role not in ("approver", "admin"):
            raise PermissionError(f"User with role '{user_role}' is not authorized to decide approvals. Required: approver or admin.")

        record_dept = record.get("department", "general")
        if user_role == "approver" and record_dept and record_dept != "general" and user_dept != record_dept:
            raise PermissionError(f"Approver from department '{user_dept}' cannot decide approvals for department '{record_dept}'.")

    record["resolved_at"] = datetime.now(timezone.utc).isoformat()
    record["decision"] = decision_clean

    diff_text = None
    if decision_clean == "approve":
        record["status"] = "approved"
    elif decision_clean == "reject":
        record["status"] = "rejected"
    elif decision_clean == "edit":
        record["status"] = "edited"
        if edited_content is not None:
            # Diff tracking: compare original draft with edited content
            orig_doc = record.get("document_content", "")
            orig_str = json.dumps(orig_doc, indent=2) if isinstance(orig_doc, (dict, list)) else str(orig_doc)
            edit_str = json.dumps(edited_content, indent=2) if isinstance(edited_content, (dict, list)) else str(edited_content)
            diff_lines = list(difflib.unified_diff(
                orig_str.splitlines(keepends=True),
                edit_str.splitlines(keepends=True),
                fromfile="original_draft",
                tofile="edited_draft",
            ))
            diff_text = "".join(diff_lines)
            record["diff"] = diff_text
            record["document_content"] = edited_content

    approver_id = None
    approver_email = None
    if approver_user is not None:
        approver_id = getattr(approver_user, "id", None) or (approver_user.get("id") if isinstance(approver_user, dict) else None)
        approver_email = getattr(approver_user, "email", None) or (approver_user.get("email") if isinstance(approver_user, dict) else None)
        record["approver_id"] = str(approver_id) if approver_id else None

    # Update database record
    try:
        from backend.db.session import SessionLocal
        from backend.db.models import Approval
        import uuid as _uuid

        db = SessionLocal()
        try:
            row = db.query(Approval).filter(Approval.task_id == task_id).first()
            if row:
                row.status = record["status"]
                row.decided_at = datetime.now(timezone.utc)
                if approver_id:
                    try:
                        row.approver_user_id = _uuid.UUID(str(approver_id))
                    except Exception:
                        pass
                if decision_clean == "edit" and edited_content is not None:
                    row.final_draft = json.dumps(edited_content) if isinstance(edited_content, (dict, list)) else str(edited_content)
                    row.diff = diff_text
                db.commit()
        finally:
            db.close()
    except Exception as exc:
        logger.warning(f"Failed to update approval record in DB: {exc}")

    # Append-only audit event for human oversight action
    actor = f"approver:{approver_email}" if approver_email else "human_supervisor"
    log_guard("approve", "DECISION", f"Task {task_id[:8]} -> Decision: '{decision_clean.upper()}' (Risk: {record['risk'].upper()}, Actor: {actor})")
    log_event(
        task_id=task_id,
        event_type="approval",
        actor=actor,
        summary=f"Approval gate: {decision_clean.upper()} by {actor} (Risk: {record['risk']}, Dept: {record.get('department')})",
        metadata={
            "task_id": task_id,
            "decision": decision_clean,
            "risk": record["risk"],
            "confidence": record.get("confidence", 0.5),
            "reasoning": record.get("reasoning", ""),
            "department": record.get("department"),
            "approver_id": str(approver_id) if approver_id else None,
            "has_edits": decision_clean == "edit",
            "diff": diff_text,
        },
        external_calls=0,
        user_id=str(approver_id) if approver_id else None,
    )

    return record


def get_pending_approvals_count(current_user: Any, db: Any) -> int:
    """Returns the count of pending approvals for the current user's role and department."""
    from backend.db.models import Approval
    from sqlalchemy import or_

    query = db.query(Approval).filter(Approval.status == "pending")
    user_role = getattr(current_user, "role", "engineer")
    user_dept = getattr(current_user, "department", "general")

    if user_role not in ("approver", "admin"):
        return 0

    if user_role == "approver" and user_dept != "general":
        query = query.filter(or_(Approval.department == user_dept, Approval.department == "general", Approval.department.is_(None)))

    return query.count()


def list_pending_approvals_db(current_user: Any, db: Any) -> List[Dict[str, Any]]:
    """Lists pending approvals scoped to the user's role and department."""
    from backend.db.models import Approval, AgentRun, Chat, Message, User
    from sqlalchemy import or_

    user_role = getattr(current_user, "role", "engineer")
    user_dept = getattr(current_user, "department", "general")

    if user_role not in ("approver", "admin"):
        return []

    query = db.query(Approval).filter(Approval.status == "pending")
    if user_role == "approver" and user_dept != "general":
        query = query.filter(or_(Approval.department == user_dept, Approval.department == "general", Approval.department.is_(None)))

    rows = query.order_by(Approval.requested_at.desc()).all()
    results = []

    for r in rows:
        in_mem = _APPROVAL_RECORDS.get(r.task_id, {})
        doc_content = in_mem.get("document_content")
        if not doc_content and r.original_draft:
            try:
                doc_content = json.loads(r.original_draft)
            except Exception:
                doc_content = r.original_draft

        requester_name = "Unknown Engineer"
        requester_email = None
        requester_dept = r.department or "general"
        task_prompt = "Industrial SOP / Deliverable Drafting"

        agent_run = db.query(AgentRun).filter(AgentRun.task_id == r.task_id).first()
        if agent_run:
            if agent_run.state_snapshot and isinstance(agent_run.state_snapshot, dict):
                orig = agent_run.state_snapshot.get("original_task")
                if orig:
                    task_prompt = orig
            if agent_run.chat_id:
                chat = db.query(Chat).filter(Chat.id == agent_run.chat_id).first()
                if chat and chat.user_id:
                    req_user = db.query(User).filter(User.id == chat.user_id).first()
                    if req_user:
                        requester_name = req_user.name
                        requester_email = req_user.email
                        requester_dept = req_user.department or requester_dept
                first_msg = db.query(Message).filter(Message.chat_id == agent_run.chat_id, Message.role == "user").order_by(Message.created_at.asc()).first()
                if first_msg and first_msg.content:
                    task_prompt = first_msg.content

        results.append({
            "task_id": r.task_id,
            "department": r.department or "general",
            "risk_level": r.risk_level or in_mem.get("risk", "medium"),
            "confidence": in_mem.get("confidence", 0.5),
            "reasoning": in_mem.get("reasoning", "Document contains hazardous keywords or ungrounded claims requiring supervisory sign-off."),
            "status": "pending",
            "requested_at": r.requested_at.isoformat() if r.requested_at else None,
            "document_content": doc_content,
            "sources": in_mem.get("sources", []),
            "requester_name": requester_name,
            "requester_email": requester_email,
            "requester_department": requester_dept,
            "task_prompt": task_prompt,
        })

    return results


def list_approval_history_db(current_user: Any, db: Any) -> List[Dict[str, Any]]:
    """Lists past resolved approvals (approved, edited, rejected) scoped by department."""
    from backend.db.models import Approval, AgentRun, Chat, Message, User
    from sqlalchemy import or_

    user_role = getattr(current_user, "role", "engineer")
    user_dept = getattr(current_user, "department", "general")

    if user_role not in ("approver", "admin", "auditor"):
        return []

    query = db.query(Approval).filter(Approval.status.in_(["approved", "rejected", "edited"]))
    if user_role == "approver" and user_dept != "general":
        query = query.filter(or_(Approval.department == user_dept, Approval.department == "general", Approval.department.is_(None)))

    rows = query.order_by(Approval.decided_at.desc(), Approval.requested_at.desc()).all()
    results = []

    for r in rows:
        in_mem = _APPROVAL_RECORDS.get(r.task_id, {})
        doc_content = in_mem.get("document_content")
        if not doc_content and r.final_draft:
            try:
                doc_content = json.loads(r.final_draft)
            except Exception:
                doc_content = r.final_draft
        elif not doc_content and r.original_draft:
            try:
                doc_content = json.loads(r.original_draft)
            except Exception:
                doc_content = r.original_draft

        requester_name = "Unknown Engineer"
        requester_email = None
        requester_dept = r.department or "general"
        task_prompt = "Industrial SOP / Deliverable Drafting"

        agent_run = db.query(AgentRun).filter(AgentRun.task_id == r.task_id).first()
        if agent_run:
            if agent_run.state_snapshot and isinstance(agent_run.state_snapshot, dict):
                orig = agent_run.state_snapshot.get("original_task")
                if orig:
                    task_prompt = orig
            if agent_run.chat_id:
                chat = db.query(Chat).filter(Chat.id == agent_run.chat_id).first()
                if chat and chat.user_id:
                    req_user = db.query(User).filter(User.id == chat.user_id).first()
                    if req_user:
                        requester_name = req_user.name
                        requester_email = req_user.email
                        requester_dept = req_user.department or requester_dept
                first_msg = db.query(Message).filter(Message.chat_id == agent_run.chat_id, Message.role == "user").order_by(Message.created_at.asc()).first()
                if first_msg and first_msg.content:
                    task_prompt = first_msg.content

        approver_name = "Supervisor"
        approver_email = None
        if r.approver_user_id:
            app_u = db.query(User).filter(User.id == r.approver_user_id).first()
            if app_u:
                approver_name = app_u.name
                approver_email = app_u.email

        filename = in_mem.get("filename")
        if not filename:
            asst_msgs = db.query(Message).filter(Message.role == "assistant").order_by(Message.created_at.desc()).limit(30).all()
            for m in asst_msgs:
                if m.meta and m.meta.get("task_id") == r.task_id and m.meta.get("approval_outcome"):
                    filename = m.meta["approval_outcome"].get("filename")
                    if filename:
                        break

        results.append({
            "task_id": r.task_id,
            "department": r.department or "general",
            "risk_level": r.risk_level or in_mem.get("risk", "medium"),
            "status": r.status,
            "decision": r.status,
            "diff": r.diff,
            "requested_at": r.requested_at.isoformat() if r.requested_at else None,
            "decided_at": r.decided_at.isoformat() if r.decided_at else None,
            "document_content": doc_content,
            "filename": filename,
            "download_url": f"/download/{filename}" if filename else None,
            "requester_name": requester_name,
            "requester_email": requester_email,
            "requester_department": requester_dept,
            "approver_name": approver_name,
            "approver_email": approver_email,
            "task_prompt": task_prompt,
        })

    return results
