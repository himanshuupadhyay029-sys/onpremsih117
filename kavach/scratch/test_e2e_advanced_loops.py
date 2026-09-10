import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from starlette.testclient import TestClient
from backend.main import app
from backend.db.session import get_db, SessionLocal
from backend.db.models import Message, AgentRun, Chat

client = TestClient(app)

def test_clarification_and_resume():
    print("\n--- Testing Clarification Flow & Resume ---")
    # Missing variable should trigger clarification
    res = client.post("/run", json={"task": "Calculate remaining pipe life with current thickness 12.5 and minimum thickness 8.0"})
    assert res.status_code == 200, res.text
    data = res.json()
    print(f"Initial status: {data.get('status')}")
    print(f"Clarify question: {data.get('clarify_question')}")
    task_id = data.get("task_id")
    assert data.get("status") in ("clarifying", "paused_clarification"), f"Expected clarifying, got {data.get('status')}"
    assert data.get("clarify_question") is not None, "Expected clarify_question"

    # Now reply with the missing parameter
    res2 = client.post(f"/run/{task_id}/reply", json={"reply": "The corrosion rate is 0.4 mm/year"})
    assert res2.status_code == 200, res2.text
    data2 = res2.json()
    print(f"Resumed status: {data2.get('status')}")
    print(f"Result: {data2.get('result')}")
    assert data2.get("status") == "complete", f"Expected complete, got {data2.get('status')}"
    assert "11.25" in str(data2.get("result")), f"Expected 11.25 in result, got {data2.get('result')}"
    print("[PASS] Clarification Flow & Resume verified!")

def test_approval_persistence():
    print("\n--- Testing Approval Persistence in DB ---")
    db = SessionLocal()
    import uuid
    from backend.db.models import User

    # Get or create a user for chat ownership
    user = db.query(User).first()
    if not user:
        user = User(id=uuid.uuid4(), name="Test Operator", email=f"test_{uuid.uuid4().hex[:6]}@kavach.local", password_hash="dummy")
        db.add(user)
        db.commit()

    chat_id = uuid.uuid4()
    chat = Chat(id=chat_id, user_id=user.id, title="Test Approval Chat")
    db.add(chat)
    db.commit()

    task_id = f"test-task-{uuid.uuid4().hex[:8]}"
    msg = Message(
        id=uuid.uuid4(),
        chat_id=chat_id,
        role="assistant",
        content="Document generated and awaiting approval",
        meta={
            "task_id": task_id,
            "status": "paused_approval",
            "approval": {
                "risk_score": "high",
                "draft_path": "mock.docx"
            }
        }
    )
    db.add(msg)
    run = AgentRun(
        id=uuid.uuid4(),
        chat_id=chat_id,
        task_id=task_id,
        status="paused_approval",
        state_snapshot={"draft_content": {"title": "Safety Guide", "sections": [{"heading": "Intro", "body": "Be safe."}]}}
    )
    db.add(run)
    db.commit()

    # Register pending approval record
    from backend.guard.approve import request_approval
    request_approval(
        task_id=task_id,
        document_content={"title": "Safety Guide", "sections": [{"heading": "Intro", "body": "Be safe."}]},
        risk_assessment={"risk": "high", "confidence": 0.5, "reasoning": "Awaiting approval test."},
        sources=["sop.md"]
    )

    # Now post approval
    res = client.post(f"/approval/{task_id}", json={"decision": "approve"})
    assert res.status_code == 200, res.text
    appr_data = res.json()
    print(f"Approval response: {appr_data}")
    assert appr_data.get("status") == "approved"

    # Verify DB persistence
    db.expire_all()
    updated_msg = db.query(Message).filter(Message.chat_id == chat_id, Message.role == "assistant").first()
    assert updated_msg is not None
    assert "approval_outcome" in updated_msg.meta, f"approval_outcome missing from meta: {updated_msg.meta}"
    assert updated_msg.meta["approval_outcome"]["approved"] is True
    print(f"Persisted message meta approval_outcome: {updated_msg.meta['approval_outcome']}")

    updated_run = db.query(AgentRun).filter(AgentRun.task_id == task_id).first()
    assert updated_run is not None, f"AgentRun not found for task_id {task_id}"
    assert updated_run.status == "complete", f"AgentRun status should be complete, got {updated_run.status}"
    print("[PASS] Approval Persistence in DB verified!")

if __name__ == "__main__":
    test_clarification_and_resume()
    test_approval_persistence()
    print("\n==========================================")
    print("ALL ADVANCED ARCHITECTURE TESTS PASSED!")
    print("==========================================")
