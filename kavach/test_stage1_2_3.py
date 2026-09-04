"""test_stage1_2_3.py — Comprehensive end-to-end verification for Stages 1, 2, and 3."""

from pathlib import Path
import sys
import uuid

import requests

ROOT_DIR = Path(__file__).resolve().parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backend.tools.sandbox import run_code

BASE_URL = "http://127.0.0.1:8000"


def test_sandbox_multi_language():
    print("\n==================================================")
    print("1. TESTING MULTI-LANGUAGE ISOLATED SANDBOX")
    print("==================================================")

    # 1. Python test
    print("\n--- 1.1 Python Sandbox Test ---")
    py_code = """
# Corrosion rate calculation: CR = (W_initial - W_final) / (Area * Time * Density)
initial_w = 120.5
final_w = 118.2
area_cm2 = 25.0
time_hours = 720.0
density = 7.85
cr_mpy = ((initial_w - final_w) * 534) / (area_cm2 * time_hours * density)
print(f"Calculated Corrosion Rate: {cr_mpy:.4f} mpy")
"""
    res_py = run_code(py_code, language="python")
    print(f"Python success: {res_py['success']}, exit_code={res_py['exit_code']}, stdout:\n{res_py['stdout'].strip()}")
    assert res_py["success"], f"Python run failed: {res_py['stderr']}"

    # 2. JavaScript test
    print("\n--- 1.2 JavaScript Sandbox Test ---")
    js_code = """
const sampleData = [
  { id: 1, valve: "V-101", pressure_psi: 145 },
  { id: 2, valve: "V-102", pressure_psi: 152 },
  { id: 3, valve: "V-103", pressure_psi: 139 }
];
const avg = sampleData.reduce((acc, v) => acc + v.pressure_psi, 0) / sampleData.length;
console.log(`Average Line Pressure: ${avg.toFixed(2)} PSI`);
"""
    res_js = run_code(js_code, language="javascript")
    print(f"JavaScript success: {res_js['success']}, exit_code={res_js['exit_code']}, stdout:\n{res_js['stdout'].strip()}")
    assert res_js["success"], f"JavaScript run failed: {res_js['stderr']}"

    # 3. C valid execution test (single container compile + run)
    print("\n--- 1.3 C Valid Single-Container Compile & Run Test ---")
    c_code = """
#include <stdio.h>
#include <math.h>

int main() {
    double base_thick = 12.5;
    double measured_thick = 9.8;
    double loss = base_thick - measured_thick;
    printf("Wall Thickness Loss: %.2f mm (Remaining: %.1f%%)\\n", loss, (measured_thick/base_thick)*100.0);
    return 0;
}
"""
    res_c = run_code(c_code, language="c")
    print(f"C success: {res_c['success']}, stage={res_c.get('stage')}, compile_output={res_c.get('compile_output')}, stdout:\n{res_c['stdout'].strip()}")
    assert res_c["success"], f"C run failed: {res_c['stderr']}"

    # 4. C syntax error test (verifying stage="compile" isolation)
    print("\n--- 1.4 C Compile Error Detection Test ---")
    c_bad_code = """
#include <stdio.h>
int main() {
    SYNTAX_ERROR_HERE_WITHOUT_SEMICOLON
    return 0;
}
"""
    res_bad_c = run_code(c_bad_code, language="c")
    print(f"C Bad Code -> success: {res_bad_c['success']}, stage={res_bad_c.get('stage')}, compile_output:\n{res_bad_c.get('compile_output')[:200]}")
    assert not res_bad_c["success"], "Expected compilation to fail"
    assert res_bad_c.get("stage") == "compile", f"Expected stage='compile', got {res_bad_c.get('stage')}"


def test_auth_and_chats():
    print("\n==================================================")
    print("2. TESTING AUTHENTICATION & PERSISTENT CHATS")
    print("==================================================")

    session = requests.Session()
    test_email = f"operator_{uuid.uuid4().hex[:6]}@mrpl.co.in"
    test_password = "SecurePassword123!"

    # 1. Register user
    print(f"\n--- 2.1 Registering User: {test_email} ---")
    reg_resp = session.post(
        f"{BASE_URL}/auth/register",
        json={"name": "Operator Lead", "email": test_email, "password": test_password},
    )
    print(f"Register status: {reg_resp.status_code}, data: {reg_resp.json()}")
    assert reg_resp.status_code == 201, f"Registration failed: {reg_resp.text}"

    # 2. Duplicate registration test (expect 409)
    print("\n--- 2.2 Testing Duplicate Registration Conflict (409) ---")
    dup_resp = session.post(
        f"{BASE_URL}/auth/register",
        json={"name": "Duplicate", "email": test_email, "password": test_password},
    )
    print(f"Duplicate status: {dup_resp.status_code}, detail: {dup_resp.json()}")
    assert dup_resp.status_code == 409, f"Expected 409 Conflict, got {dup_resp.status_code}"

    # 3. Login user & verify JWT cookie
    print("\n--- 2.3 Logging in User ---")
    login_resp = session.post(
        f"{BASE_URL}/auth/login",
        json={"email": test_email, "password": test_password},
    )
    print(f"Login status: {login_resp.status_code}, cookies: {session.cookies.get_dict()}")
    assert login_resp.status_code == 200, f"Login failed: {login_resp.text}"
    assert "access_token" in session.cookies, "Missing access_token httpOnly cookie"

    # 4. Get authenticated profile
    print("\n--- 2.4 Testing GET /auth/me ---")
    me_resp = session.get(f"{BASE_URL}/auth/me")
    print(f"Me status: {me_resp.status_code}, profile: {me_resp.json()}")
    assert me_resp.status_code == 200, f"/auth/me failed: {me_resp.text}"
    user_id = me_resp.json()["id"]

    # 5. Create new chat
    print("\n--- 2.5 Testing POST /chats ---")
    chat_resp = session.post(f"{BASE_URL}/chats", json={"title": "New Chat"})
    print(f"Create chat status: {chat_resp.status_code}, data: {chat_resp.json()}")
    assert chat_resp.status_code == 201, f"Create chat failed: {chat_resp.text}"
    chat_id = chat_resp.json()["id"]

    # 6. List user chats
    print("\n--- 2.6 Testing GET /chats ---")
    list_resp = session.get(f"{BASE_URL}/chats")
    print(f"List chats count: {len(list_resp.json())}, first: {list_resp.json()[0]}")
    assert len(list_resp.json()) >= 1

    # 7. Run query with chat_id and verify 2-message persistence
    print("\n--- 2.7 Testing POST /run with chat_id ---")
    run_resp = session.post(
        f"{BASE_URL}/run",
        json={"task": "Calculate the wall loss for 15mm initial and 12mm measured", "chat_id": chat_id},
    )
    print(f"Run status: {run_resp.status_code}, status_field: {run_resp.json().get('status')}")
    assert run_resp.status_code == 200

    # 8. Check message history for chat
    print("\n--- 2.8 Testing GET /chats/{id}/messages (Hydration) ---")
    msgs_resp = session.get(f"{BASE_URL}/chats/{chat_id}/messages")
    msgs = msgs_resp.json()
    print(f"Retrieved {len(msgs)} message rows:")
    for i, m in enumerate(msgs, 1):
        print(f"  [{i}] Role: {m['role']} | Content: {m['content'][:70]}... | Has Meta: {bool(m['meta'])}")
    assert len(msgs) == 2, f"Expected exactly 2 turn messages (user & assistant), found {len(msgs)}"

    # 9. Verify Auto-Titling
    print("\n--- 2.9 Verifying Auto-Titling ---")
    updated_chat = session.get(f"{BASE_URL}/chats/{chat_id}").json()
    print(f"Updated Chat Title: '{updated_chat['title']}'")
    assert updated_chat["title"] != "New Chat", "Expected auto-title to be generated"

    print("\n==================================================")
    print("ALL VERIFICATIONS PASSED SUCCESSFULLY!")
    print("==================================================")


if __name__ == "__main__":
    test_sandbox_multi_language()
    test_auth_and_chats()
