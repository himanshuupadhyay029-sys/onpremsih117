"""test_master_planner.py — Verification of Master Planner Layer, Dynamic Routing, and Agentic Sub-task Loop."""

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backend.brain.router import route
from backend.brain.agent import _parse_master_plan, run_agent


def test_master_planner_parsing():
    print("\n--- 1. Testing Master Planner Parsing & Rule-based Fallback ---")
    
    # 1.1 Single-intent calculation prompt
    raw_calc = '[{"step_num": 1, "tool": "calc", "input": "Calculate 15 * 60"}]'
    steps_calc = _parse_master_plan(raw_calc, "Calculate 15 * 60")
    assert len(steps_calc) == 1
    assert steps_calc[0]["tool"] == "calc"
    print("  [PASS] Single calc parsed correctly.")

    # 1.2 Compound prompt (Search + Calc + Document)
    raw_compound = """```json
    [
      {"step_num": 1, "tool": "search", "input": "Look up pipeline corrosion tolerance SOP"},
      {"step_num": 2, "tool": "calc", "input": "Compute remaining life with 10mm wall thickness"},
      {"step_num": 3, "tool": "document", "input": "Draft formal inspection report"}
    ]
    ```"""
    steps_compound = _parse_master_plan(raw_compound, "Compound request")
    assert len(steps_compound) == 3
    assert [s["tool"] for s in steps_compound] == ["search", "calc", "document"]
    print("  [PASS] Multi-step compound plan parsed correctly.")

    # 1.3 Fallback parsing on invalid JSON
    raw_invalid = "Sorry, I am not able to generate a JSON plan right now."
    steps_fallback = _parse_master_plan(raw_invalid, "Calculate remaining pipe life")
    assert len(steps_fallback) == 1
    assert steps_fallback[0]["tool"] == "calc"
    print("  [PASS] Fallback handler intelligently deduced 'calc' from query keywords.")


def test_subtask_intent_routing():
    print("\n--- 2. Testing Per-Subtask Intent Routing ---")
    
    # Search subtask
    dec_search = route("Search the Knowledge Vault for emergency shutdown procedure", hint="search")
    assert dec_search.task_type == "search"
    assert dec_search.model_role == "reasoning"
    print(f"  [PASS] Sub-task 1 routed to: {dec_search.task_type} ({dec_search.model_role})")

    # Calc subtask
    dec_calc = route("Calculate remaining wall thickness after 5 years", hint="calc")
    assert dec_calc.task_type == "calc"
    assert dec_calc.model_role == "reasoning"
    print(f"  [PASS] Sub-task 2 routed to: {dec_calc.task_type} ({dec_calc.model_role})")

    # Code subtask
    dec_code = route("Write and run a python script to simulate pressure", hint="code")
    assert dec_code.task_type == "code"
    assert dec_code.model_role == "code"
    print(f"  [PASS] Sub-task 3 routed to: {dec_code.task_type} ({dec_code.model_role})")

    # OCR subtask
    dec_ocr = route("Read text from scanned inspection sheet", hint="ocr")
    assert dec_ocr.task_type == "ocr"
    print(f"  [PASS] Sub-task 4 routed to: {dec_ocr.task_type}")


def test_e2e_run_agent():
    print("\n--- 3. Testing End-to-End run_agent with Master Planner ---")
    res = run_agent("Calculate 25 * 4 and explain what 100 psi means")
    assert res.get("status") == "complete"
    assert "plan" in res
    assert len(res["plan"]) >= 1
    assert "result" in res and res["result"]
    print(f"  [PASS] Agent ran successfully. Plan steps: {len(res['plan'])}")
    print(f"  Result preview: {res['result'][:120]}...")


if __name__ == "__main__":
    test_master_planner_parsing()
    test_subtask_intent_routing()
    test_e2e_run_agent()
    print("\n=======================================================")
    print("ALL MASTER PLANNER & SUBTASK ROUTING TESTS PASSED!")
    print("=======================================================")
