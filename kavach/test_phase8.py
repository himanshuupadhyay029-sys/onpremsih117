"""test_phase8.py — Verification script for Phase 8: Math Calculator & Claim Verifier."""

import json
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parent
KAVACH_DIR = ROOT_DIR / "kavach" if (ROOT_DIR / "kavach").exists() else ROOT_DIR

for p in [str(ROOT_DIR), str(KAVACH_DIR)]:
    if p not in sys.path:
        sys.path.insert(0, p)

from backend import config
from backend.audit.logbook import read_events
from backend.guard.verify import verify_claims
from backend.tools.calc import calculate


def print_audit_trail(task_id: str, title: str):
    print(f"\n==================================================")
    print(f"AUDIT TRAIL: {title} (Task ID: {task_id})")
    print(f"==================================================")
    events = read_events(task_id=task_id)
    for i, ev in enumerate(events, 1):
        print(f"[{i}] {ev.get('timestamp')} | Event: {ev.get('event_type').upper()} | Actor: {ev.get('actor')} | External: {ev.get('external_calls')}")
        print(f"    Summary: {ev.get('summary')}")


def main():
    print("=== KAVACH Phase 8: Calculator & Verifier Verification ===")

    # ----------------------------------------------------
    # Test 1: Complete Calculation (Pipe Remaining Life)
    # ----------------------------------------------------
    print("\n--- 1. Deterministic Calculation with Real Numbers ---")
    task_complete = (
        "A pipe wall was 12.5mm thick when new, minimum allowed thickness is 8mm, "
        "and it's corroding at 0.4mm/year - calculate the remaining life in years."
    )
    task_id_1 = "phase8-calc-complete-001"
    res_1 = calculate(task_complete, task_id=task_id_1)
    print(f"Formula Name    : {res_1.get('formula_name')}")
    print(f"Formula Expr    : {res_1.get('formula_expression')}")
    print(f"Extracted Inputs: {res_1.get('inputs')}")
    print("Deterministic Step-by-Step Resolution:")
    for step in res_1.get("steps", []):
        print(f"  > {step}")
    print(f"Result Value    : {res_1.get('result')} {res_1.get('unit')}")
    assert res_1.get("success") is True, "Calculation failed!"
    assert res_1.get("result") == 11.25, f"Expected 11.25, got {res_1.get('result')}"

    # ----------------------------------------------------
    # Test 2: Incomplete Calculation (Missing Corrosion Rate)
    # ----------------------------------------------------
    print("\n--- 2. Incomplete Calculation with Missing Parameter ---")
    task_incomplete = (
        "A pipe wall was 12.5mm thick when new, minimum allowed thickness is 8mm - calculate the remaining life in years."
    )
    task_id_2 = "phase8-calc-missing-002"
    res_2 = calculate(task_incomplete, task_id=task_id_2)
    print(f"Calculation Success : {res_2.get('success')}")
    print(f"Missing Inputs Flag : {res_2.get('missing_inputs')}")
    print(f"Reported Message    : {res_2.get('error')}")
    assert res_2.get("success") is False, "Should have failed due to missing inputs!"
    assert len(res_2.get("missing_inputs", [])) > 0, "Missing inputs must be reported!"

    # ----------------------------------------------------
    # Test 3: Claim Verification Pass on Document
    # ----------------------------------------------------
    print("\n--- 3. Citation & Claim Grounding Verification Pass ---")
    sample_doc_text = """
    Inspection and Incident Response Summary:
    1. During inspection on 2026-08-24, VALVE-402-ALPHA showed an operating pressure reading of 142.5 PSI.
    2. Under standard incident response procedures, Severity 1 critical incidents must be acknowledged within 15 minutes.
    3. Emergency response teams are allowed to bypass password authentication without supervisor consent.
    """

    sources_used = [
        {
            "filename": "inspection_note_clean.png",
            "excerpt": "Equipment Tag: VALVE-402-ALPHA. Operating Pressure Reading: 142.5 PSI (Safe Limit: 160.0 PSI). Status: NORMAL OPERATION.",
        },
        {
            "filename": "incident_response_sop.md",
            "excerpt": "Incident Severity Classification:\n- Severity 1 (Critical): must be acknowledged within 15 minutes, initial status update within 30 minutes.",
        },
        {
            "filename": "access_control_sop.md",
            "excerpt": "Emergency override access requires dual supervisor authorization and audit logging. Direct bypass is prohibited under all circumstances.",
        },
    ]

    task_id_3 = "phase8-verify-claims-003"
    verify_res = verify_claims(sample_doc_text, sources_used=sources_used, task_id=task_id_3)

    print(f"Total Claims Evaluated : {verify_res['total_claims']}")
    print(f"Verified / Supported   : {verify_res['verified_claims']}/{verify_res['total_claims']}")
    print(f"Overall Verified       : {verify_res['overall_verified']}")
    print("\nClaim-by-Claim Breakdown:")
    for i, c in enumerate(verify_res["claims"], 1):
        status_icon = "SUPPORTED" if c.get("supported") else "UNSUPPORTED/FLAGGED"
        print(f"  [{i}] Status: {status_icon}")
        print(f"      Claim : {c.get('claim')}")
        print(f"      Source: {c.get('source')}")
        print(f"      Reason: {c.get('reason')}")

    # ----------------------------------------------------
    # Test 4: Audit Trail Verification
    # ----------------------------------------------------
    print_audit_trail(task_id_1, "Calculation Task")
    print_audit_trail(task_id_3, "Claim Verification Task")

    print("\n=== Phase 8 Verification Complete! ===")


if __name__ == "__main__":
    main()
