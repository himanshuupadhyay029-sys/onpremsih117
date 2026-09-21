"""test_math_calc_pipeline.py — Verification of calculator robustness and routing accuracy."""

import pytest
from backend.brain.router import route
from backend.tools.calc import calculate, compute, _sanitize_expression


def test_sanitize_expression():
    # 1. Assignment stripping
    assert _sanitize_expression("Distance = speed * time") == "speed * time"
    assert _sanitize_expression("Distance = 60 * (45/60)") == "60 * (45/60)"
    assert _sanitize_expression("d = 60 * 0.75") == "60 * 0.75"
    
    # 2. Result equality stripping
    assert _sanitize_expression("45 miles + 20 miles = 65 miles") == "45 + 20"
    assert _sanitize_expression("60 * 0.75 = 45") == "60 * 0.75"
    
    # 3. Unit stripping
    assert _sanitize_expression("60 mph * 0.75 hours") == "60 * 0.75"
    assert _sanitize_expression("40 mph * (30/60) hrs") == "40 * (30/60)"
    
    # 4. Symbol replacement
    assert _sanitize_expression("5 ^ 2") == "5 ** 2"
    assert _sanitize_expression("5 × 4") == "5 * 4"
    assert _sanitize_expression("10 ÷ 2") == "10 / 2"


def test_compute_direct():
    # Direct formula computation
    res1 = compute({
        "formula_name": "Leg 1 Distance",
        "formula_expression": "Distance = 60 * (45/60)",
        "inputs": {},
        "unit": "miles",
    })
    assert res1["success"] is True
    assert res1["result"] == 45

    res2 = compute({
        "formula_name": "Leg 2 Distance",
        "formula_expression": "40 * (30/60) = 20",
        "inputs": {},
        "unit": "miles",
    })
    assert res2["success"] is True
    assert res2["result"] == 20

    res3 = compute({
        "formula_name": "Total Distance",
        "formula_expression": "45 miles + 20 miles = 65 miles",
        "inputs": {},
        "unit": "miles",
    })
    assert res3["success"] is True
    assert res3["result"] == 65


def test_router_calc_vs_code():
    # Math problem should route to calc
    task_math = "A car travels at 60 mph for 45 minutes and then 40 mph for 30 minutes. The total distance covered is 65 miles. Verify if this is correct step-by-step and create a summary."
    decision_math = route(task_math)
    assert decision_math.task_type == "calc", f"Expected 'calc', got '{decision_math.task_type}'"

    # Explicit coding task should route to code
    task_code = "Write a python script to compute fibonacci numbers"
    decision_code = route(task_code)
    assert decision_code.task_type == "code", f"Expected 'code', got '{decision_code.task_type}'"


def test_calculate_end_to_end_subtasks():
    # Test calculate tool with realistic subtasks
    res = calculate(
        "Calculate distance traveled: speed is 60 mph and time is 45 minutes (0.75 hours)",
        task_id="test-calc-leg1",
    )
    assert res["success"] is True
    assert res["result"] == 45 or res["result"] == 45.0
    print(f"\nCalculated Leg 1 Result: {res['result']} {res.get('unit')} (Steps: {res.get('steps')})")

    res_total = calculate(
        "Calculate total distance: 45 miles + 20 miles",
        task_id="test-calc-total",
    )
    assert res_total["success"] is True
    assert res_total["result"] == 65 or res_total["result"] == 65.0
    print(f"Calculated Total Result: {res_total['result']} {res_total.get('unit')} (Steps: {res_total.get('steps')})")


if __name__ == "__main__":
    test_sanitize_expression()
    test_compute_direct()
    test_router_calc_vs_code()
    test_calculate_end_to_end_subtasks()
    print("\nALL MATH CALC PIPELINE UNIT TESTS PASSED!")
