"""test_rbac_approval_audit.py — Tests for KAVACH RBAC, approval routing, and audit chain.

Test (a): A user from department X cannot retrieve a document tagged department Y.
Test (b): A non-approver cannot decide an approval. (Part B)
Test (c): Editing one historical audit log line breaks the verify endpoint. (Part C)
"""

import json
import os
import sys
import uuid
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

# Ensure project root is on sys.path for imports
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Set test database URL if not already set
os.environ.setdefault("DATABASE_URL", "postgresql://kavach:kavach_secret@127.0.0.1:5434/kavach_db")


# ============================================================================
# Part A Tests — RBAC & Department-Scoped Retrieval
# ============================================================================

class TestPartA_RBAC:
    """Tests for role-based access control and department-scoped document retrieval."""

    def test_require_role_blocks_unauthorized(self):
        """require_role('admin') dependency should raise 403 for non-admin users."""
        from backend.auth.routes import require_role
        from fastapi import HTTPException

        # Create a mock user with role='engineer'
        mock_user = MagicMock()
        mock_user.role = "engineer"

        dep = require_role("admin")

        with pytest.raises(HTTPException) as exc_info:
            dep(current_user=mock_user)

        assert exc_info.value.status_code == 403
        assert "admin" in exc_info.value.detail.lower()

    def test_require_role_allows_authorized(self):
        """require_role('admin') dependency should return user for admin users."""
        from backend.auth.routes import require_role

        mock_user = MagicMock()
        mock_user.role = "admin"

        dep = require_role("admin")
        result = dep(current_user=mock_user)
        assert result == mock_user

    def test_require_role_multiple_roles(self):
        """require_role('approver', 'admin') should allow either role."""
        from backend.auth.routes import require_role

        mock_approver = MagicMock()
        mock_approver.role = "approver"

        mock_admin = MagicMock()
        mock_admin.role = "admin"

        dep = require_role("approver", "admin")
        assert dep(current_user=mock_approver) == mock_approver
        assert dep(current_user=mock_admin) == mock_admin

    def test_user_response_includes_role_department(self):
        """UserResponse schema must include role and department fields."""
        from backend.auth.routes import UserResponse

        data = UserResponse(
            id="test-id",
            name="Test User",
            email="test@test.com",
            role="approver",
            department="process",
            created_at="2026-01-01T00:00:00",
        )
        assert data.role == "approver"
        assert data.department == "process"

    def test_user_model_has_rbac_columns(self):
        """User model should have role and department columns with correct defaults."""
        from backend.db.models import User

        # Check columns exist and have defaults
        role_col = User.__table__.columns["role"]
        dept_col = User.__table__.columns["department"]

        assert role_col is not None
        assert dept_col is not None
        assert str(role_col.server_default.arg) == "engineer"
        assert str(dept_col.server_default.arg) == "general"

    def test_document_model_exists(self):
        """Document model should exist with required columns."""
        from backend.db.models import Document

        cols = {c.name for c in Document.__table__.columns}
        assert "id" in cols
        assert "owner_user_id" in cols
        assert "filename" in cols
        assert "department" in cols
        assert "classification_level" in cols
        assert "uploaded_at" in cols

    def test_department_filter_blocks_cross_department_retrieval(self):
        """Core RBAC test: a user from department 'process' should NOT see documents
        tagged as department 'maintenance' in retrieval results.

        This test mocks the DB and FAISS layer to isolate the RBAC filtering logic.
        """
        from backend.vault.retrieve import retrieve

        # Mock the entire retrieval pipeline up to RBAC filtering
        mock_index = MagicMock()
        mock_index.ntotal = 1
        mock_index.d = 768
        mock_index.search = MagicMock(return_value=(
            MagicMock(),  # distances
            MagicMock(__getitem__=lambda s, i: [0]),  # indices
        ))

        mock_metadata = [{
            "chunk_id": "test_c0",
            "parent_id": "test_p0",
            "parent_text": "Maintenance procedure text",
            "chunk_text": "Maintenance procedure text",
            "breadcrumb": "Test > Maintenance",
            "source_filename": "maintenance_sop.md",
            "chunk_index": 0,
        }]

        # Create mock Document entry for the maintenance file
        mock_doc = MagicMock()
        mock_doc.filename = "maintenance_sop.md"
        mock_doc.department = "maintenance"
        mock_doc.classification_level = "internal"

        user_id = str(uuid.uuid4())

        with patch("backend.vault.retrieve._load_all_stores") as mock_load, \
             patch("backend.vault.retrieve.ollama.embed") as mock_embed, \
             patch("backend.vault.retrieve.cross_encoder_rerank") as mock_rerank, \
             patch("backend.vault.retrieve.SessionLocal") as mock_session_cls, \
             patch("backend.vault.retrieve.Document") as mock_doc_model, \
             patch("backend.vault.retrieve.log_event") as mock_log_event:

            mock_load.return_value = (mock_index, mock_metadata, None)
            mock_embed.return_value = [0.1] * 768

            # rerank returns the candidate as-is with a score
            mock_rerank.return_value = [{
                **mock_metadata[0],
                "rerank_score": 0.8,
            }]

            # Mock DB session for RBAC filter
            mock_db = MagicMock()
            mock_session_cls.return_value = mock_db
            mock_query = MagicMock()
            mock_db.query.return_value = mock_query
            mock_query.filter.return_value = mock_query
            mock_query.all.return_value = [mock_doc]

            # A 'process' department user should get ZERO results for 'maintenance' docs
            results = retrieve(
                query="maintenance procedure",
                user_id=user_id,
                requester_role="engineer",
                requester_department="process",
            )

            # The RBAC filter should have removed all results
            assert len(results) == 0, (
                f"Expected 0 results for cross-department access, got {len(results)}"
            )

            # Verify that an access_denied event was logged
            mock_log_event.assert_called()
            call_kwargs = mock_log_event.call_args
            assert call_kwargs is not None

    def test_admin_bypasses_department_filter(self):
        """Admin users should see documents from any department."""
        from backend.vault.retrieve import retrieve

        mock_index = MagicMock()
        mock_index.ntotal = 1
        mock_index.d = 768
        mock_index.search = MagicMock(return_value=(
            MagicMock(),
            MagicMock(__getitem__=lambda s, i: [0]),
        ))

        mock_metadata = [{
            "chunk_id": "test_c0",
            "parent_id": "test_p0",
            "parent_text": "Restricted content",
            "chunk_text": "Restricted content",
            "breadcrumb": "Test > Restricted",
            "source_filename": "restricted_doc.md",
            "chunk_index": 0,
        }]

        mock_doc = MagicMock()
        mock_doc.filename = "restricted_doc.md"
        mock_doc.department = "finance"
        mock_doc.classification_level = "internal"

        user_id = str(uuid.uuid4())

        with patch("backend.vault.retrieve._load_all_stores") as mock_load, \
             patch("backend.vault.retrieve.ollama.embed") as mock_embed, \
             patch("backend.vault.retrieve.cross_encoder_rerank") as mock_rerank, \
             patch("backend.vault.retrieve.SessionLocal") as mock_session_cls, \
             patch("backend.vault.retrieve.Document") as mock_doc_model:

            mock_load.return_value = (mock_index, mock_metadata, None)
            mock_embed.return_value = [0.1] * 768
            mock_rerank.return_value = [{
                **mock_metadata[0],
                "rerank_score": 0.8,
            }]

            mock_db = MagicMock()
            mock_session_cls.return_value = mock_db
            mock_query = MagicMock()
            mock_db.query.return_value = mock_query
            mock_query.filter.return_value = mock_query
            mock_query.all.return_value = [mock_doc]

            # Admin from 'process' should still see 'finance' docs
            results = retrieve(
                query="restricted content",
                user_id=user_id,
                requester_role="admin",
                requester_department="process",
            )

            assert len(results) > 0, (
                "Admin should bypass department filter and see cross-department docs"
            )

    def test_restricted_classification_blocked_for_engineer(self):
        """Engineer should NOT see restricted-classification documents."""
        from backend.vault.retrieve import retrieve

        mock_index = MagicMock()
        mock_index.ntotal = 1
        mock_index.d = 768
        mock_index.search = MagicMock(return_value=(
            MagicMock(),
            MagicMock(__getitem__=lambda s, i: [0]),
        ))

        mock_metadata = [{
            "chunk_id": "test_c0",
            "parent_id": "test_p0",
            "parent_text": "Top secret data",
            "chunk_text": "Top secret data",
            "breadcrumb": "Test > Secret",
            "source_filename": "secret.md",
            "chunk_index": 0,
        }]

        mock_doc = MagicMock()
        mock_doc.filename = "secret.md"
        mock_doc.department = "process"  # Same department as requester
        mock_doc.classification_level = "restricted"

        user_id = str(uuid.uuid4())

        with patch("backend.vault.retrieve._load_all_stores") as mock_load, \
             patch("backend.vault.retrieve.ollama.embed") as mock_embed, \
             patch("backend.vault.retrieve.cross_encoder_rerank") as mock_rerank, \
             patch("backend.vault.retrieve.SessionLocal") as mock_session_cls, \
             patch("backend.vault.retrieve.Document") as mock_doc_model, \
             patch("backend.vault.retrieve.log_event"):

            mock_load.return_value = (mock_index, mock_metadata, None)
            mock_embed.return_value = [0.1] * 768
            mock_rerank.return_value = [{
                **mock_metadata[0],
                "rerank_score": 0.8,
            }]

            mock_db = MagicMock()
            mock_session_cls.return_value = mock_db
            mock_query = MagicMock()
            mock_db.query.return_value = mock_query
            mock_query.filter.return_value = mock_query
            mock_query.all.return_value = [mock_doc]

            # Engineer from 'process' should NOT see restricted docs even in own dept
            results = retrieve(
                query="top secret",
                user_id=user_id,
                requester_role="engineer",
                requester_department="process",
            )

            assert len(results) == 0, (
                "Engineer should not see restricted-classification documents"
            )

    def test_ingest_document_accepts_department_classification(self):
        """ingest_document should accept department and classification_level params."""
        import inspect
        from backend.vault.ingest import ingest_document

        sig = inspect.signature(ingest_document)
        params = list(sig.parameters.keys())
        assert "department" in params, "ingest_document must accept 'department' param"
        assert "classification_level" in params, "ingest_document must accept 'classification_level' param"

    def test_valid_roles_and_departments_defined(self):
        """Auth module should define valid role and department constants."""
        from backend.auth.routes import VALID_ROLES, VALID_DEPARTMENTS

        assert "engineer" in VALID_ROLES
        assert "approver" in VALID_ROLES
        assert "admin" in VALID_ROLES
        assert "auditor" in VALID_ROLES

        assert "process" in VALID_DEPARTMENTS
        assert "maintenance" in VALID_DEPARTMENTS
        assert "hse" in VALID_DEPARTMENTS
        assert "general" in VALID_DEPARTMENTS


# ============================================================================
# Part B Tests — Approval Routing & Safety Backstops
# ============================================================================

class TestPartB_ApprovalRouting:
    """Tests for authorized human approval routing, safety backstops, and diff tracking."""

    def test_non_approver_cannot_decide_approval(self):
        """Test (b): A non-approver (role='engineer') cannot decide an approval."""
        from backend.guard.approve import request_approval, resolve_approval

        task_id = f"test-task-b1-{uuid.uuid4()}"
        request_approval(
            task_id=task_id,
            document_content={"title": "Plant SOP", "sections": []},
            risk_assessment={"risk": "high", "department": "process"},
            department="process",
        )

        mock_engineer = MagicMock()
        mock_engineer.id = str(uuid.uuid4())
        mock_engineer.role = "engineer"
        mock_engineer.department = "process"
        mock_engineer.email = "eng@kavach.org"

        with pytest.raises(PermissionError) as exc_info:
            resolve_approval(
                task_id=task_id,
                decision="approve",
                approver_user=mock_engineer,
            )

        assert "not authorized" in str(exc_info.value).lower()
        assert "approver or admin" in str(exc_info.value).lower()

    def test_approver_cross_department_rejected(self):
        """An approver from department 'maintenance' cannot approve a 'process' task."""
        from backend.guard.approve import request_approval, resolve_approval

        task_id = f"test-task-b2-{uuid.uuid4()}"
        request_approval(
            task_id=task_id,
            document_content={"title": "Process SOP", "sections": []},
            risk_assessment={"risk": "high", "department": "process"},
            department="process",
        )

        mock_maint_approver = MagicMock()
        mock_maint_approver.id = str(uuid.uuid4())
        mock_maint_approver.role = "approver"
        mock_maint_approver.department = "maintenance"
        mock_maint_approver.email = "maint_lead@kavach.org"

        with pytest.raises(PermissionError) as exc_info:
            resolve_approval(
                task_id=task_id,
                decision="approve",
                approver_user=mock_maint_approver,
            )

        assert "maintenance" in str(exc_info.value).lower()
        assert "process" in str(exc_info.value).lower()

    def test_approver_matching_department_allowed(self):
        """An approver from department 'process' CAN approve a 'process' task."""
        from backend.guard.approve import request_approval, resolve_approval

        task_id = f"test-task-b3-{uuid.uuid4()}"
        request_approval(
            task_id=task_id,
            document_content={"title": "Process SOP", "sections": []},
            risk_assessment={"risk": "high", "department": "process"},
            department="process",
        )

        mock_proc_approver = MagicMock()
        mock_proc_approver.id = str(uuid.uuid4())
        mock_proc_approver.role = "approver"
        mock_proc_approver.department = "process"
        mock_proc_approver.email = "proc_lead@kavach.org"

        resolved = resolve_approval(
            task_id=task_id,
            decision="approve",
            approver_user=mock_proc_approver,
        )

        assert resolved["status"] == "approved"
        assert resolved["decision"] == "approve"

    def test_admin_bypasses_department_check_for_approval(self):
        """An admin can approve tasks across any department."""
        from backend.guard.approve import request_approval, resolve_approval

        task_id = f"test-task-b4-{uuid.uuid4()}"
        request_approval(
            task_id=task_id,
            document_content={"title": "HSE Protocol", "sections": []},
            risk_assessment={"risk": "high", "department": "hse"},
            department="hse",
        )

        mock_admin = MagicMock()
        mock_admin.id = str(uuid.uuid4())
        mock_admin.role = "admin"
        mock_admin.department = "general"
        mock_admin.email = "admin@kavach.org"

        resolved = resolve_approval(
            task_id=task_id,
            decision="approve",
            approver_user=mock_admin,
        )

        assert resolved["status"] == "approved"

    def test_edit_decision_tracks_unified_diff(self):
        """When an approval is resolved with 'edit', a unified diff is computed and stored."""
        from backend.guard.approve import request_approval, resolve_approval

        task_id = f"test-task-b5-{uuid.uuid4()}"
        orig_content = {
            "title": "Initial Safety Draft",
            "sections": [{"heading": "Pressure Limit", "body": "Set to 100 psi"}],
        }
        request_approval(
            task_id=task_id,
            document_content=orig_content,
            risk_assessment={"risk": "high", "department": "process"},
            department="process",
        )

        edited_content = {
            "title": "Initial Safety Draft",
            "sections": [{"heading": "Pressure Limit", "body": "Set to 75 psi (Safety Margin)"}],
        }

        mock_approver = MagicMock()
        mock_approver.id = str(uuid.uuid4())
        mock_approver.role = "approver"
        mock_proc_approver = mock_approver
        mock_proc_approver.department = "process"
        mock_proc_approver.email = "proc_lead@kavach.org"

        resolved = resolve_approval(
            task_id=task_id,
            decision="edit",
            approver_user=mock_proc_approver,
            edited_content=edited_content,
        )

        assert resolved["status"] == "edited"
        assert resolved["diff"] is not None
        assert "75 psi" in resolved["diff"]
        assert "100 psi" in resolved["diff"]

    def test_deterministic_hazardous_keyword_backstop(self):
        """Hazardous operational terms trigger HIGH risk automatically even for non-document tasks."""
        from backend.guard.approve import assess_risk

        assessment = assess_risk(
            task_type="search",
            document_content="Emergency shutdown procedure for high pressure toxic gas pipeline",
        )
        assert assessment["risk"] == "high"
        assert "backstop" in assessment["reasoning"].lower() or "safety" in assessment["reasoning"].lower()

    def test_restricted_classification_triggers_high_risk(self):
        """Restricted classification triggers HIGH risk regardless of task type."""
        from backend.guard.approve import assess_risk

        assessment = assess_risk(
            task_type="document",
            document_content="Standard plant summary report",
            source_classification="restricted",
        )
        assert assessment["risk"] == "high"
        assert "restricted" in assessment["reasoning"].lower()

    def test_low_retrieval_confidence_triggers_high_risk(self):
        """Retrieval confidence below 0.60 triggers HIGH risk."""
        from backend.guard.approve import assess_risk

        assessment = assess_risk(
            task_type="document",
            document_content="Standard plant report with unconfirmed details",
            retrieval_confidence=0.45,
        )
        assert assessment["risk"] == "high"
        assert "confidence" in assessment["reasoning"].lower()


# ============================================================================
# Part C Tests — Tamper-Evident Audit Chain
# ============================================================================

class TestPartC_AuditChain:
    """Tests for cryptographic SHA-256 hash-chaining and tamper detection."""

    def test_hash_chain_computes_cryptographic_links(self, tmp_path):
        """Audit entries are hash-chained: entry N has prev_hash == entry N-1's entry_hash."""
        from backend.audit.logbook import log_event, verify_chain, GENESIS_HASH
        from backend import config

        test_user_id = str(uuid.uuid4())
        test_log_file = tmp_path / f"test_audit_{test_user_id}.jsonl"

        with patch("backend.config.get_user_audit_log_path", return_value=test_log_file):
            t1 = log_event(event_type="plan", actor="planner", summary="Created step 1", user_id=test_user_id)
            t2 = log_event(event_type="step", actor="code_tool", summary="Executed sandbox", user_id=test_user_id)
            t3 = log_event(event_type="complete", actor="agent", summary="Finished task", user_id=test_user_id)

            report = verify_chain(user_id=test_user_id)
            assert report["valid"] is True
            assert report["total_entries"] == 3
            assert report["verified_count"] == 3
            assert report["broken_at_index"] is None

            # Read raw file to verify chain structure
            with open(test_log_file, "r", encoding="utf-8") as f:
                entries = [json.loads(line) for line in f if line.strip()]

            assert len(entries) == 3
            assert entries[0]["prev_hash"] == GENESIS_HASH
            assert entries[1]["prev_hash"] == entries[0]["entry_hash"]
            assert entries[2]["prev_hash"] == entries[1]["entry_hash"]

    def test_tampered_audit_line_detected(self, tmp_path):
        """Test (c): Editing one historical audit log line breaks the verify endpoint."""
        from backend.audit.logbook import log_event, verify_chain

        test_user_id = str(uuid.uuid4())
        test_log_file = tmp_path / f"test_audit_{test_user_id}.jsonl"

        with patch("backend.config.get_user_audit_log_path", return_value=test_log_file):
            # 1. Log three events
            log_event(event_type="plan", actor="planner", summary="Initial plan", user_id=test_user_id)
            log_event(event_type="step", actor="writer", summary="Drafted confidential SOP", user_id=test_user_id)
            log_event(event_type="approval", actor="approver", summary="Approved by lead", user_id=test_user_id)

            # Verification passes initially
            assert verify_chain(user_id=test_user_id)["valid"] is True

            # 2. Tamper with entry #1 (modify summary maliciously)
            with open(test_log_file, "r", encoding="utf-8") as f:
                lines = [l.strip() for l in f if l.strip()]

            tampered_record = json.loads(lines[1])
            tampered_record["summary"] = "MALICIOUSLY_ALTERED_CONTENT"
            lines[1] = json.dumps(tampered_record)

            with open(test_log_file, "w", encoding="utf-8") as f:
                for line in lines:
                    f.write(line + "\n")

            # 3. Verification must fail and identify the exact tampered index
            report = verify_chain(user_id=test_user_id)
            assert report["valid"] is False, "verify_chain must detect tampered historical content"
            assert report["broken_at_index"] == 1, "verify_chain must identify entry #1 as broken"
            assert "tamper" in report["message"].lower() or "broken" in report["message"].lower()

    def test_deleted_audit_line_breaks_hash_chain(self, tmp_path):
        """Deleting an entry in the middle breaks the prev_hash link of subsequent entries."""
        from backend.audit.logbook import log_event, verify_chain

        test_user_id = str(uuid.uuid4())
        test_log_file = tmp_path / f"test_audit_{test_user_id}.jsonl"

        with patch("backend.config.get_user_audit_log_path", return_value=test_log_file):
            log_event(event_type="plan", actor="planner", summary="Step 1", user_id=test_user_id)
            log_event(event_type="step", actor="writer", summary="Step 2 (to delete)", user_id=test_user_id)
            log_event(event_type="complete", actor="agent", summary="Step 3", user_id=test_user_id)

            # Delete the second line
            with open(test_log_file, "r", encoding="utf-8") as f:
                lines = [l.strip() for l in f if l.strip()]

            # Keep only line 0 and line 2
            with open(test_log_file, "w", encoding="utf-8") as f:
                f.write(lines[0] + "\n")
                f.write(lines[2] + "\n")

            # Verification must fail because line 2's prev_hash points to deleted line 1
            report = verify_chain(user_id=test_user_id)
            assert report["valid"] is False
            assert report["broken_at_index"] == 1
            assert "prev_hash" in report["reason"] or "link" in report["message"].lower()

    def test_empty_audit_log_reports_valid(self, tmp_path):
        """Empty audit log reports valid with total_entries=0."""
        from backend.audit.logbook import verify_chain

        test_user_id = str(uuid.uuid4())
        empty_log = tmp_path / "empty_audit.jsonl"

        with patch("backend.config.get_user_audit_log_path", return_value=empty_log):
            report = verify_chain(user_id=test_user_id)
            assert report["valid"] is True
            assert report["total_entries"] == 0
            assert report["verified_count"] == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
