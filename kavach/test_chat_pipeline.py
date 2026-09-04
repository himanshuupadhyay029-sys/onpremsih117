import uuid
from fastapi.testclient import TestClient
from backend.main import app
from backend.db.session import SessionLocal
from backend.db.models import User, Chat, Message

client = TestClient(app)

def test_pipeline():
    print("=== Testing Chat Persistence & Multi-turn Pipeline via TestClient ===")

    # 1. Register & Login
    email = f"operator_{uuid.uuid4().hex[:6]}@kavach.local"
    reg_res = client.post("/auth/register", json={
        "name": "Test Operator",
        "email": email,
        "password": "SecretPassword123!"
    })
    assert reg_res.status_code == 201, f"Register failed: {reg_res.text}"
    user_id = reg_res.json()["id"]

    login_res = client.post("/auth/login", json={
        "email": email,
        "password": "SecretPassword123!"
    })
    assert login_res.status_code == 200, f"Login failed: {login_res.text}"
    print(f"[PASS] User registered and logged in: {email}")

    # 2. First run without chat_id -> Auto-create chat
    task1 = "Calculate 15 * 60 and state the result clearly"
    run1 = client.post("/run", json={"task": task1})
    assert run1.status_code == 200, f"Run 1 failed: {run1.text}"
    data1 = run1.json()

    chat_id = data1.get("chat_id")
    chat_title = data1.get("chat_title")
    print(f"[PASS] Auto-created chat_id: {chat_id}, title: {chat_title}")
    assert chat_id is not None, "chat_id must not be None"
    assert "Calculate" in chat_title, f"Unexpected title: {chat_title}"

    # 3. Multi-turn follow-up with the same chat_id
    task2 = "Now multiply that previous result by 2"
    run2 = client.post("/run", json={"task": task2, "chat_id": chat_id})
    assert run2.status_code == 200, f"Run 2 failed: {run2.text}"
    data2 = run2.json()
    assert data2.get("chat_id") == chat_id, f"Expected same chat_id, got {data2.get('chat_id')}"
    print(f"[PASS] Multi-turn run reused chat_id: {chat_id}")

    # 4. Verify messages in database and rich metadata
    msgs_res = client.get(f"/chats/{chat_id}/messages")
    assert msgs_res.status_code == 200, f"Get messages failed: {msgs_res.text}"
    msgs = msgs_res.json()
    print(f"[PASS] Retrieved {len(msgs)} messages from DB for chat {chat_id}")
    assert len(msgs) == 4, f"Expected 4 messages (2 user + 2 assistant), got {len(msgs)}"

    # Verify user message and assistant message structure
    assert msgs[0]["role"] == "user"
    assert msgs[1]["role"] == "assistant"
    assert "steps" in msgs[1]["meta"]
    assert msgs[2]["role"] == "user"
    assert msgs[3]["role"] == "assistant"

    # 5. Check chat list endpoint
    chats_res = client.get("/chats")
    assert chats_res.status_code == 200
    user_chats = chats_res.json()
    assert any(c["id"] == chat_id for c in user_chats), "Chat should appear in user's chat list"
    print(f"[PASS] Chat correctly appears in user's chat list with message_count={user_chats[0]['message_count']}")

    print("\n>>> ALL CHAT PERSISTENCE & MULTI-TURN BACKEND TESTS PASSED! <<<")

if __name__ == "__main__":
    test_pipeline()
